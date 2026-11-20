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
5. Admin without superuser read right cannot browse all task bodies.
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
