# Security specification — mandatory review and test targets

## Main threats

IDOR/record leakage, overbroad multi-department managers, creator bypass to unassigned tasks, manipulated Mini App requests, Telegram username reassignment, stolen Telegram account, brute-force password/MFA, replayed webhook, file URL leakage, CSV formula injection, template schema injection, privilege escalation by managers, stale caches/sessions, misconfigured backup/CI secrets.

## Requirements

- **Least privilege:** task read scope enforce on all endpoints, exports, search, widgets, downloads, websocket channels, worker queries. Existence of hidden records should not be revealed through error details.
- **Session & credentials:** robust password hash (e.g., Argon2id with reviewed parameters), strong reset/rebinding policies, HttpOnly/Secure/SameSite cookies where appropriate, session expiry/revocation, rate limiting, login CSRF/origin controls.
- **Telegram MFA:** exact challenge binding, short TTL, single use, no acceptance from username alone, secret/callback signature validation, replay protection, denial audit, secure account recovery via admin with identity proof.
- **Role changes:** immediate server enforcement, permission-version checks and invalidation of sessions/caches/live channels; test role removal while tab remains open.
- **Data validation:** JSON schema/published template only; field-level ACL; sanitize rich text/markdown, guard XSS/CSRF, prevent mass assignment; safe API query limits.
- **Files:** maximum 100 MB, upload authorization, server-side MIME/content checks, anti-malware strategy, object keys randomized, private buckets/volumes, download after authorization, short-lived signed URLs only when appropriate, retention and deletion lifecycle.
- **Export:** authorize rows and columns, prevent CSV/Excel formula injection, audit export actor/scope; limit report size.
- **Infrastructure:** public access only to proxy/TLS endpoints, DB/Redis private network, non-root containers, env secret protection, security updates, staging/prod separation, encrypted backups off-host, regular restore drills.
- **Logs and audit:** track changes to tasks, users, roles/grants, templates, config and privileged actions, with actor/time/context; redact secrets and sensitive descriptions, restrict audit access and establish retention policy.
- **Workers:** do not grant a worker arbitrary database read independent of application policy. Job payloads carry IDs, not whole sensitive records, and re-authorize on delivery.

## Safety-critical cases to test

1. Staff guessing other employees' task IDs or file URLs cannot retrieve content.
2. Author of a task assigned to someone else cannot bypass `assignee only` rule via author ownership.
3. Manager of department A cannot read B's tasks even when employee belongs to both.
4. Superuser with task-read right but without admin right cannot edit role grants.
5. ~~Admin without superuser read right cannot browse all task bodies.~~ Replaced by D042 (2026-11-27): the administrator role reads and changes every task. An administrator account is therefore the most valuable target in the system: the role must be held by as few people as possible, and its use is audited like anybody else's.
6. Manager cannot create a new admin/superuser role grant.
7. Permission revocation takes effect mid-session for list, detail, search, download, export, live updates.
8. Archived/deleted records obey the same or stricter ACL.
9. Web/Mini App/bot all reject field tampering or unauthorized assignee.
10. Telegram challenge cannot be replayed or approved from another Telegram ID.
11. Concurrent status update and archive cannot leave completed visible on active board without archive.
12. Backup recovery restores both DB and files and does not expose credentials.

## Policies not yet fixed

Password policy, session TTL, MFA challenge TTL, admin identity verification for Telegram recovery, incident response, audit retention, permanent deletion, RPO/RTO, compliance/locality requirements. Do not invent them silently; use interim secure development defaults only if explicitly labelled as provisional and not for production.

## Approved Q10–Q12 controls

- Q10: Cross-department invitation requires explicit department-of-participation from active employee memberships. Approver must be manager of that department or superuser with separate approval permission; validate server-side and audit.
- Q11: Provision account only via admin or authorized manager. First-time Telegram binding uses expiring single-use invitation and private bot interaction. Validate numeric Telegram sender ID, token, replay, uniqueness and race; do not rely on Telegram username.
- Q12: Administrator-controlled recovery requires an identity-verification procedure, revocation of existing binding and pending MFA approvals, new enrollment and full audit. The concrete acceptable evidence and emergency admin procedure remain OPEN; do not automatically accept email alone.

## Approved Q13 — Authentication parameters

- Password length: at least **12 characters**; reject common and known-compromised passwords; no forced calendar-based periodic password change. Require secure hashing (Argon2id or reviewed equivalent), secure password reset and immediate revocation on evidence of compromise.
- Failed authentication: **progressive rate limiting** without a permanent account lockout. Cover both password and MFA attempts; log security-relevant events without leaking secrets. Concrete throttle values are configurable and must pass abuse testing.
- Telegram MFA: one-time challenge bound to user, authenticated login attempt and approved Telegram User ID; expires after **3 minutes (180 seconds)**; once approved, denied or expired, cannot be replayed.
- Web sessions: maximum absolute lifetime **12 hours**, including any refresh flow. Do not prolong indefinitely by idle activity. Re-authentication required after expiry; permission changes/deactivation take effect immediately even before normal expiry.
- No Telegram availability means new actions requiring Telegram (including MFA login) must fail closed. Existing sessions remain subject to their normal expiry and access checks. Telegram account recovery remains admin-mediated under Q12.

## Approved Q14 — Audit visibility and retention

- Administrator: authorized company-wide audit visibility; audit access is a separately protected feature, not a bypass of normal task-content viewing in other endpoints.
- Department manager: audit events only within departments they currently manage, with record-level visibility checked for sensitive event data. Changes to an employee's membership or audit scope must not leave stale access.
- Superuser: audit events **only** with explicit, separately granted `audit.read` permission, restricted to the granted scope. Company-wide task-read permission alone is insufficient.
- Retention: **indefinite until explicit manual cleanup**; no automatic audit-event purges/TTL. Cleanup must require explicit administrative authorization, be itself auditable and respect applicable legal holds and policies.
- Do not store passwords, raw binding tokens, MFA responses, session secrets or unrestricted sensitive old/new payloads in audit. For cross-department records, apply authorization or redaction before delivery or export.


## Q15–Q16 — disaster recovery and file safety (approved)

- Recovery objectives: RPO ≤1h, RTO ≤4h; retain backups 30 days. Encrypt backup copies off the production VPS; protect keys separately; test complete DB + attachment restoration in an isolated environment and track measured outcomes.
- Attachment primary storage: private persistent VPS volume. File allowlist limited to PDF/Word/Excel, image files and ZIP. Max 100MB each. Validate actual content as well as extension and MIME; enforce task-level ACL for both read and write, including archive/trash access rules.
- No mandatory antivirus scanner in initial version. Apply defense-in-depth regardless: safe browser rendering/download headers, no executable upload serving, ZIP bomb checks, path canonicalization, quarantine or rejection for unsafe/unknown content and least-privilege volume mount.
- Do not assume compliant backup cadence or encryption/data region provider has been chosen; record exact product/tool/restore tests as implementation decisions before production.

### Attachments as built (2026-11-26, D039)

- A file is reachable only as `/api/v1/tasks/{task}/attachments/{file}`: the task's read rule is checked on every download, and a file ID is looked up inside that task only. The storage has no public or pre-signed addresses; object keys are opaque and never leave the API.
- A download is always sent as `Content-Disposition: attachment` with `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox` and `Cache-Control: no-store`, so an uploaded file is never rendered inside the CRM's origin. SVG and HTML are not accepted at all.
- The type is decided from the content; the file name is reduced to a display name and never becomes a path or a key.
- **Residual risk (accepted by Q16): there is no malware scan.** A well-formed PDF, Office document or archive may carry malicious content; legacy `.doc`/`.xls` may carry macros. Files are only stored and handed back as downloads.
- S3 credentials come from the environment only and are never logged; storage errors are reported without provider detail.

## Approved Q24 — archive ACL safeguards
- Protect archive listings, counts, details, search filter, exports, analytics, files, direct links and notifications with the same server-enforced record-level permissions as ordinary task access.
- Archive is a read location, not a new permission grant; creator-only authorship never grants archive read.
- Validate permission versions after revocation; never leak archived task titles, totals or attachment metadata in a shared view or Telegram.
- Historical KPI contributions apply to **completed** tasks only, not manually archived incomplete tasks. Trash is separately authorized.

## Q25 — Russia-hosted VPS, international employees; compliance NOT YET APPROVED
- Production VPS and primary databases/attachments must be hosted in Russia. Document and verify actual provider, data-center jurisdiction, operator, subprocessors, and offsite-backup location before go-live.
- Access from other countries is supported, but applicability of Russian personal-data requirements, other jurisdictions' privacy laws (including possible GDPR reach), and any international transfer requirements must be determined through a documented review; Russian hosting by itself is not a compliance guarantee.
- Map flows involving Telegram bot/Mini App, foreign employees, email provider, monitoring, error logs, backups, access from outside Russia, and remote support. Do not assume Telegram data handling remains within Russia.
- Document lawful basis/notice, roles, retention and erasure/legal holds, incident response, technical measures, encryption/key custody and any localization/transfer duties based on verified facts and relevant legal advice.
- Retain Q14 indefinite audit and Q06 indefinite Trash **as approved product defaults**, but flag potential legal retention/deletion conflicts for resolution; do not override user decisions without approval.

## Approved Q28 — Administrator-only email verification and manual account recovery
- A recovery email is marked verified **only via an authenticated administrator action** after that administrator follows the approved verification process; employee input, possession of an email link, or an external provider signal alone must not change CRM verification status.
- Recovery is **manual and administrator-mediated**; disable any self-service password or MFA reset that is automatically completed using email alone. Keep Telegram account loss steps from Q12, including verification of the employee's identity, revocation of the previous Telegram binding/pending challenges, and secure re-enrollment.
- Log verification, changes, invalidation, recovery initiation, identity-check outcome, credential reset/Telegram rebind and relevant session revocation without logging passwords, tokens, recovery secrets or unnecessary personal evidence.
- Store verification state with administrator ID and timestamp. Limit viewing of raw recovery information. Changing the email invalidates its old verified status until an administrator re-verifies it.
- **OPEN, not approved:** accepted identity-verification evidence, mailbox-deliverability/ownership method, email provider, manual recovery transport, admin emergency/break-glass controls and evidence retention.

## Approved Q29 — Read-only superuser base capability
- Superuser can read task records across all company departments subject to the Q29 role's company-wide task-read policy; this is not a blanket Django `is_superuser`/admin bypass of business ACL.
- Each write/approval action additionally requires a distinct explicitly assigned permission (for example, task status/update/assign, project invitation approval, manual archive/reopen, soft delete/restore). Record ACL + action grant apply jointly wherever appropriate. Granting task read must never imply audit read, admin configuration, permanent purge or account recovery.
- Enforce server-side for list/detail/search/export/API, background workers and Telegram; revocation takes immediate effect. Record grants and privileged actions in audit, and test negative permission combinations.

## REC-01 / REC-02 — Approved low-friction recovery policy

### Employee account recovery (REC-01)
1. Employee requests help; no automatic reset is completed by an email link, Telegram message or public API.
2. An **authenticated CRM administrator** compares minimal existing employee/HR record identifiers, then obtains confirmation from that employee's **recorded manager** (via an approved internal channel). No ordinary mandatory video interview, photo ID upload, biometrics or extensive forms.
3. Administrator records a concise result and manager confirmer ID/time, not unnecessary sensitive HR content; the request is permitted or denied with auditable reason.
4. On approval, revoke the previous Telegram binding and outstanding MFA login challenges, invalidate sessions/credentials as appropriate, then issue a fresh, expiring, single-use private enrollment token under approved Q11 controls. Never allow email possession to bypass Telegram-2FA.
5. For HR mismatch, missing/compromised manager, self-approval, disputed request, or competing requests, stop and escalate to a separately approved exception procedure; do not silently waive identity verification.

### Emergency administrator access (REC-02)
- Reserve a dedicated **break-glass administrative account** with separately protected access and strict access to required recovery functions. Do not use this account for routine work or as a business-superuser data-reading bypass.
- Require an explicit emergency-use procedure, strong independently protected credentials/MFA or an approved alternative that remains functional during the incident, independent audit logs/alerts and post-event review. Never hardcode keys, secrets or recovery tokens.
- **OPEN:** exact custody, enrollment, activation, auth factor, duration, independent reviewer, unavailable-manager fallback and end-to-end operational runbook. Production activation is blocked until documented and tested.

## Implementation status (S1.1)

Implemented and covered by automated tests:

- Passwords: Argon2id only; Q13 policy (minimum 12 characters, rejection of common/leaked passwords from a local list, no character-class rules, no forced rotation); inputs over 128 characters are refused before hashing.
- No Django admin site and no `/admin` route; `django.contrib.auth`, `admin`, `sessions`, `contenttypes` are not installed (D032).
- Audit events are written in the same transaction as the change they describe, and the table is append-only at the database level. Metadata whose keys look like secrets (password, token, hash, cookie, ...) is refused by the audit service.
- The first administrator is created only by the CLI command `create_first_administrator`, only while no active administrator exists; the password is never accepted as a command-line argument; the action is audited with the operating-system account as the actor.

- Telegram enrollment (Q11), domain part: the binding code is 256 bits of randomness, stored only as a SHA-256 hash, valid once and for a limited time; issuing a new code revokes the previous one. Binding takes the numeric Telegram ID from the update, never from user text, and never uses the username as identity. Codes sent outside a private chat, replayed, altered, expired, revoked, for a deactivated or already bound account, or from a Telegram account bound elsewhere are refused with one generic answer and audited with the real reason. Re-binding is impossible here: it is a recovery action.
- Binding codes for the first administrator can be issued from the CLI only until an administrator has bound Telegram.

Not implemented yet: user provisioning screens, email verification, the recovery workflow, the emergency administrator account.

## Implementation status (S1.2b, S1.3) — sign-in

Implemented and covered by automated tests:

- **Login (Q13, Q30).** CRM login + password, then approval in Telegram. A wrong password, an unknown login, an account without a password and a deactivated account all get the same `invalid_credentials` answer after the same amount of hashing work; the real reason goes only to the audit log. A login that matches no account is not written to the audit log (people type passwords into the wrong field). "Not bound to Telegram" is told only to somebody who already proved the password.
- **Challenge.** Lives 180 seconds (also a database constraint), one live challenge per account (a new attempt cancels the previous one). It is bound to the account, to the numeric Telegram ID bound at that moment and to the browser that sent the password. A decision counts only from that Telegram ID, only once, only before expiry, and only while the binding and the account are unchanged; everything else is refused with one generic answer and audited with its reason. The callback data of the buttons carries no secret.
- **Collecting the session.** The browser proves it started the attempt with a 256-bit secret kept in an HttpOnly, SameSite=Strict cookie scoped to `/api/v1/auth/` (only its SHA-256 is stored). An approval is exchanged for a session exactly once (state machine under a row lock, plus a one-session-per-challenge unique constraint). Cancelling in the browser disarms the prompt in Telegram.
- **Sessions.** Random 256-bit token in an HttpOnly, Secure, SameSite=Lax cookie with the `__Host-` prefix; only its SHA-256 is stored. Absolute lifetime 12 hours from issuance, never prolonged (also a database constraint). Every request re-reads the session, its expiry, its revocation and the account's active state from PostgreSQL, and permissions are read live, so deactivation, logout and changes of rights apply to open sessions at once. A password change ends all sessions of the user and cancels waiting attempts.
- **Deny by default.** Every API view needs a session unless it declares otherwise (health probes, the two login steps, logout).
- **CSRF / login CSRF.** A state-changing request is accepted only with an `Origin` from `WEB_ORIGINS`, or with no `Origin` and no CRM cookie at all (a script, not a browser session).
- **Throttling (Q13).** Progressive delays, never a permanent lock, counters start over after a quiet period: per login+address, per login, per address, per account for Telegram prompts (a stolen password cannot be used to flood the owner's Telegram), per Telegram account for wrong binding codes. Unknown logins are throttled exactly like real ones. Subjects are stored as keyed hashes. **The thresholds are provisional** (`OPEN_QUESTIONS.md`).
- **Client address.** `X-Forwarded-For` is honoured only for `TRUSTED_PROXY_HOPS` proxies and read from the trusted end; the web application does not forward client-supplied address headers.
- **Telegram outage (Q13).** If the queue or Telegram is unavailable, or Telegram refuses the message, the prompt is marked failed and the login cannot complete; open sessions are unaffected.
- **Bot.** Takes identity only from the update (`from_user.id`), never from text or the username; asks Telegram only for messages addressed to it and button presses; stores nothing from chats; stays silent in groups; deletes the message that contained a binding code.
- **Login form.** Submits by POST even when page scripts fail to load, so the password can never reach the address bar; the password field is cleared after a failed attempt.

Residual risks and limits of this slice:

- Local Docker Compose has no reverse proxy yet, so the API sees every browser at the web container's address: the per-address counters are shared by all users there. The per-login and per-prompt counters still work. The real client address arrives with the HTTPS ingress (S8) and `TRUSTED_PROXY_HOPS`.
- No TLS/HSTS inside the stack yet (S8). The session cookie is nevertheless always `Secure`.
- Expired sessions, challenges and throttle counters are not purged yet; they are inert rows. A cleanup job belongs to S8.
- A prompt may be delivered twice if a worker crashes between sending and recording it; both messages act on the same single-use challenge.

## Implementation status (S1.4) — accounts and the first password

- **Provisioning.** Only a holder of company-wide `user.create` can create an account. The account has no password and no role; the request body cannot set a password, a role, the Telegram ID or the active flag (mass assignment is tested). The binding code is returned once, in a response that is never cached, and is not readable afterwards.
- **First password (D036).** The link is 256 random bits, stored as a SHA-256 hash, single-use, valid 30 minutes (provisional), one live link per account. It is issued only to the numeric Telegram ID bound to an active account that has no password, so it can never replace an existing password. The token travels in the URL fragment (not sent to servers, absent from access logs and Referer), is removed from the address bar when read, and the page sends no Referer. The bot message is protected from forwarding and has no link preview. Setting the password signs nobody in. Weak passwords are refused without burning the link. Wrong links are delayed per address, link requests per Telegram account; every refusal is audited with its reason and answered generically.
- **Trust note.** Whoever holds the binding code and the Telegram account that redeems it chooses the password: the binding code must reach the employee personally. This is inherent in D036 and Q11.
- **Deactivation.** Ends sessions and waiting login attempts, revokes pending binding codes and password links, bumps the permission version, in one transaction; applies to open sessions on their next request. Nobody can deactivate themselves; the last active administrator cannot be deactivated (also against a concurrent role revocation, by locking the administrator role). Reactivation restores nothing that was revoked.
- **Visibility.** The account list needs `user.read`; without it the API answers 403 and the Users page does not exist (404). The list never contains password hashes or Telegram IDs. An unknown account ID is answered only after the caller's right to see accounts is established.
- **Bot API address.** `TELEGRAM_API_BASE_URL` may point to a relay; that host sees the bot token and all messages and must be under the company's control.

Not built: editing accounts, role assignment from the interface, the hand-over of tasks on deactivation (S3), recovery (S1.5).

## Implementation status (S5) — requests by a template

- **Who submits.** `task.create` in the department is checked first, then that the template is active, published and listed for that department (Q21, D040). Every failure of the second check answers the same "not found".
- **Mass assignment.** A submission may carry only the keys of the published version. An unknown key, a value for a file field typed as text, a file for a field that takes none, and any multipart part other than `payload` and `file.<key>` are refused; nothing is silently dropped or stored.
- **Lookups through the form.** An `employee` field accepts only active people of the request's department; everybody else is refused exactly like a made-up identifier, so the form cannot be used to probe who exists.
- **Files.** The same content checks, size limit and storage keys as task attachments (Q16, D039). The whole request body is limited to 100 MB while it is being read.
- **Reading.** The answers are served only through the task's read check; there is no address of a submission that works without it. File answers link to the task's attachment download, which has its own check.
- **Audit and logs.** `request.submitted` records the template, the version, the source and counts. No answer, title or file name is written to the audit log; a refusal names the field key and a reason code, never the value.
- **Atomicity.** A request is created completely or not at all; objects stored before a failure are deleted.

Not built: per-field visibility inside a form (every reader of the task sees all answers), default values, Telegram submissions (S6).

## Implementation status (S6) — Telegram notifications

- **ACL at dispatch (Q23).** A queued notification proves nothing: before sending, the recipient's account state, Telegram binding and `task.read` on the task are read again. A manager removed from the department, a former assignee, a deactivated or unbound account and a deleted task get no message.
- **Data minimization.** A message carries the task's title, department, deadline and the name of who acted. Comment texts, descriptions, form answers and file names are never sent. Messages are sent with `protect_content`, as plain text (no markup interpretation).
- **Storage and logs.** The outbox stores identifiers, a status and a reason code — no text. Telegram's error text is never logged or stored (it may quote the request); only the exception class name.
- **Addressing.** Messages go to the bound numeric Telegram ID in a private chat, never to a group and never by username.
- **Availability.** A send failure is retried a bounded number of times and never blocks or rolls back the CRM operation.

Project invitations follow the same rule: the right to decide, to run the project or the membership is read again when the message is sent; the reason typed for a refusal is never sent.

Not built: operator alert on terminal failure, per-user notification settings.

## Implementation status (S6) — the request dialogue in the bot

- **Identity.** Every step resolves the sender from `from_user.id` to an active bound account; an unbound or deactivated sender gets one fixed refusal. Nothing the user types and no username is used as identity.
- **Authorization.** The dialogue offers only what `offers` returns for that account; the final `submit` enforces `task.create`, the template's availability and every value again. A manager who loses the department or a template retired mid-dialogue ends in a refusal with nothing created.
- **Replay and forgery.** Callback data is `rq:<nonce>:<action>`; the nonce is random per dialogue and checked together with the sender and the current step. Choices are indexes into lists kept on the server side, range-checked. One dialogue can create at most one request (idempotency key + state cleared before submit).
- **Groups.** `/request` and `/cancel` act only in a private chat (Q22 allowlist not built); nothing of a form is ever posted to a group.
- **Data at rest.** Answers wait in Redis for at most 30 minutes; files are not stored between steps. No answer is written to logs or to the audit log.

Not built: Mini App with `initData` validation, webhook secret, update de-duplication by `update_id`.

## Implementation status (S6) — `/task` in the bot

Same safeguards as the request dialogue: identity from the numeric Telegram ID on every step, private chat only, per-dialogue nonce on buttons, range-checked choices, `create_task` as the only authority (D037), one answer for everybody who may not create tasks. One dialogue creates at most one task: the state is cleared before creating and updates of a chat are processed sequentially. Note: this sequencing is per bot process — running several bot processes would need a shared lock.
