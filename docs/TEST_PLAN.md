# Testing and acceptance plan

## Layers

1. Unit: permission predicates, workflow transitions, task/checkpoint rules, template schema validators, KPI calculations, reminder schedules.
2. Integration: PostgreSQL test DB and migrations, API authorization, soft-delete/archive behavior, invite approvals, user deactivation/transfer, outbox events.
3. Contract: bot/Mini App/web create the same request via identical schema, errors, idempotency.
4. E2E: keyboard/mouse flows on Kanban, task modal, edit mode, filters/search, archive/trash, dashboards, Telegram form mocks, MFA mocks.
5. Operational: staging deploy, backups/restore, failure injection (Redis unavailable, Telegram timeout, DB reconnect), CI rollback feasibility.

## Tooling per layer (D029, 2026-11-19)

| Layer | Tool | Scope |
|---|---|---|
| Backend unit + integration + permission-negative | pytest + pytest-django | Django apps in `apps/api`, Celery tasks in `apps/worker`, later the aiogram handlers; real PostgreSQL and Redis, no SQLite substitute |
| Frontend unit + component | Vitest + React Testing Library | `apps/web` and TypeScript packages only |
| Contract | pytest (schema validation) + generated TypeScript types checked by `tsc` | OpenAPI schema committed in `packages/contracts`; CI fails on drift |
| E2E | Playwright | Browser flows against the Docker Compose stack |

Vitest is never used for Python packages. Turborepo runs `lint`, `typecheck`, `test` and `build` for every app; the Python apps expose these through `package.json` scripts that call `uv run`. CI runs the frontend, backend and E2E suites automatically on every push and pull request.

## Permission matrix negative tests

- Employee A's GET/list/search/export/archive/file access cannot reveal employee B's task, including when A is task author but not assignee.
- Manager A cannot read B-owned department tasks even with cross-department employees or shared project.
- Superuser without admin privileges cannot edit system roles/settings.
- Admin without superuser/manager task read cannot view unrelated task content.
- Permissions revoked mid-session invalidate queries, stored views, websocket channels and downloads.
- User deactivated during create/upload or download causes action denial and/or safe transaction rollback.
- A shared dashboard never grants broader access to its viewer than viewer's scope.

## Task lifecycle scenarios

- Create request -> immediately assigned to permitted employee; checkpoint template instantiated and additional checkpoints can be added.
- Check all checkpoints -> task status unchanged, no auto-archive unless status was independently completed.
- Move task into completed status -> in one transaction `completed_at` and `archived_at` become set; removed from active board; appears in Archive.
- Attempt illegal drag-drop status -> API denies; UI reverts.
- Manager manually archives/unarchives only within scope; employee cannot manually archive.
- Soft-delete -> appears only in Trash for authorized users; restore preserves history and scope.
- Change deadline by assignee -> audit old/new + manager notification; irrelevant department manager cannot read.
- Deactivate employee with primary-dept manager -> reassign incomplete tasks. Without manager -> authorized superuser fallback. No duplicated assignments, no orphaned tasks.
- Invite staff from another dept -> pending request, authorize deciding manager/superuser, no membership until approved.

## Security testing

Password/MFA rate limits; Telegram auth callback replay and expiry; Mini App forged initData; bot webhook spoofing; username reuse; path traversal or dangerous file MIME; CSV formula injection; untrusted HTML/XSS; query complexity/excessive export; audit redaction; CSRF as appropriate.

## Performance / reliability

Run realistic fixtures (>=20 users, chosen number of tasks, typical file sizes) and record baseline; no fixed p95 target until acceptance threshold approved. Verify 100MB max upload handling, worker retry/idempotency, DB migration/restore.

## Release checklist

- Requirements traceability from PRD to tests and issues.
- CI checks passed; staging smoke + permission negative tests passed.
- DB migrations tested backward/forward as appropriate.
- Telemetry/alerting and backup/restore verified.
- Product owner acceptance for UX and core workflows.
- Remaining production-blocking open questions resolved.

## Approved Q01–Q09 and Q30 — required executable test cases

- **Q01** Creating active employee without primary dept fails; two primary memberships fail; admin can switch primary atomically and produces audit; non-admin cannot.
- **Q02** Creator assigning to someone else receives receipt but GET/list/search/export are denied; authorized manager can read/edit within scope.
- **Q03** Cannot create task without assignee; second concurrent assignee fails v1 invariant; reassignment only manager/superuser with dedicated permission.
- **Q04** Two configured completed statuses both atomically set completed/archived; cancelled never increases completed KPI; checkpoints alone never complete.
- **Q05** Reopen archived completed task as authorized manager/superuser -> previous valid non-completed status with audit and appropriately reset completion/archive flags; employee denied; inactive previous status requires explicit mapping.
- **Q06** Manager/superuser can soft-delete and restore only within scope; employee and cross-dept manager denied; deleted task hidden from active search/exports; Trash remains after 30+ days without auto purge; only admin can initiate explicit purge (retention guard + audit).
- **Q07** Manager manually archives active unfinished task without setting completed_at; employee cannot; archive removed from active board, can be found only via ACL-safe archive views.
- **Q08** With multiple managers, only designated active responsible manager receives tasks; otherwise designated authorized superuser; no target -> deactivation blocked, alert admin; concurrent deactivation/edit preserves assignments and audit exactly once.
- **Q09** In-use status removal without mapping is refused; explicit mapping updates all relevant tasks, preserves historical old status, rejects inaccessible/incompatible targets; failure rolls transaction back.
- **Q30** Unique CRM login enforced; blank/changed Telegram username does not prevent login via CRM login; ID binding cannot be changed by impersonating username.
- Verify behavior through Django/DRF service tests and API integration tests; Playwright tests for archive/Trash modal actions. These are required scenarios, **not implemented tests in this documentation bundle**.

## Approved Q10–Q12 — required executable test scenarios (not yet implemented)

- **Q10:** Multi-department invited employee: chosen participation department must be active membership. Manager of chosen department or separately authorized superuser can approve; manager of unrelated department cannot. Tampered department ID, lost membership before approval, duplicated/conflicting approval and premature project access are denied.
- **Q11:** Admin/authorized manager provisions account. Token expires, is single-use, is only accepted from proper private bot user ID; reuse, altered tokens, username impersonation, Telegram ID collision, concurrent redemption and unauthorized provisioning fail and audit. Enrollment succeeds before first Telegram MFA login.
- **Q12:** After administrator verified recovery, prior Telegram ID cannot approve login and pending challenges are invalid; new binding requires fresh enrollment and is audited. Unauthenticated/email-only self-service rebound is denied. Detailed admin proof/break-glass acceptance tests are blocked pending procedure definition.

## Approved Q13–Q14 — required automated tests (to implement)

**Q13**
- Reject passwords shorter than 12 characters, common passwords and known-compromised passwords; accept non-compromised strong passwords without requiring arbitrary character classes.
- Do not force periodic rotation; force reset where security incident policy requires it.
- Repeated failed password/MFA attempts trigger progressive throttling without permanent account lockout; prevent bypass by trivial change of source identifier; no username enumeration or leakage of credentials.
- Telegram MFA is accepted only for the linked numeric Telegram User ID and exact pending login challenge, before 180-second expiry; deny replay, double confirmation, approval of expired/cancelled challenges and cross-account confirmations.
- Authenticated session expires by absolute 12-hour limit even if used continually; access after expiry denied. Revoked role or deactivated account loses access immediately during otherwise valid session.

**Q14**
- Admin can query approved audit endpoints across company, but admin status alone does not grant read access to task bodies through regular task APIs.
- Department A manager sees A-scoped audit events but not B events or sensitive cross-department fields; changing manager department scope invalidates old access immediately.
- Superuser with no `audit.read` grant receives denial despite company-wide task-read; separately granted superuser can access only the explicitly authorized audit scope.
- Employee cannot search/export audit by guessing IDs, filters or pagination; masked event metadata does not leak secrets.
- Events persist past any default TTL; no background cleanup removes them. Explicit authorized manual cleanup is logged and respects legal hold/retention restrictions.

Tests listed here are acceptance criteria and are **not executed or implemented** by the documentation update.


## Q15–Q16 — required executable acceptance tests (not implemented yet)

**Q15 (disaster recovery)**
- Simulate production-like loss of VPS and restore complete PostgreSQL state and private attachment bytes from off-VPS encrypted backups in isolated staging. Measure actual **data loss ≤1 hour (RPO)** and **service restoration ≤4 hours (RTO)**; record results and repeat periodically.
- Verify at least 30-day backup retention, integrity/checksum verification, restoration of critical configuration and key access, proper alerts for missing/stale/failed backups, and consistency across DB records/files.
- Demonstrate that a daily PostgreSQL dump **alone** cannot be treated as satisfying 1-hour RPO; verify WAL/PITR (or an equally validated alternate design), error handling and rollback on corrupted backups.

**Q16 (file storage)**
- Accept only explicitly allowlisted PDF/Word/Excel, image and ZIP types; reject scripts, unsafe active files, forged MIME/extensions, ZIP bombs, path traversal and uploaded filenames attempting to escape local storage.
- Enforce ≤100MB file limit through reverse proxy, Django API and storage layer (test 100MB boundary and 100MB+1 byte). Stream large files without exhausting RAM.
- Verify persistent mounted storage survives container rebuild/restart, but losing VPS triggers recovery from independent backups; public URLs, direct path guessing and cross-department file downloads fail.
- Verify user ACLs on attachments and permissions for archived/deleted tasks, file export and restore; test safe download headers, checksums, quota warnings and disk-full failures. Malware scanning is **not a launch requirement**, but document residual risk and protective validation.

These are planned test cases, not proof the implementation currently passes.

## Q17–Q18 acceptance tests — approved requirements (not yet implemented)

**Q17:**
- Create task with original deadline Nov 10, change current deadline to Nov 15, complete Nov 14: original deadline indicator = late; current deadline indicator = on time.
- Edit deadline again after completion: historical effective-at-completion deadline and historical KPI classification remain unchanged.
- Confirm two KPIs share a consistently scoped population, never count cancelled/manual-archived unfinished tasks as completed, and do not expose tasks outside the viewer's ACL.
- Verify original deadline and due-date changes persist through archive/reopen and API/export/report flows.

**Q18:**
- Created at T0, assigned at T1, completed at T2: duration measurement starts at T1, not T0.
- Reopen and complete again: preserve the first cycle, create a distinct subsequent cycle, and provide both cycle-level and overall duration without resetting history.
- Verify cycle events survive status changes, archival and authorized recovery, while cancelled or unfinished tasks are not accidentally counted as completed.
- Ensure aggregates and exported results are permission-filtered.

**Await explicit decisions:** no-deadline denominators, reopened-cycle KPI counting, post-reassignment start logic, what duration includes. Don't hardcode a policy before approval.

## Q19 — Field-level permissions acceptance tests (specified, not implemented)

1. Assignee can transition an assigned task through allowed statuses and to a configured `completed` status; completion auto-archives atomically. Invalid transition or wrong task gives 403/validation response, with no unauthorized mutation.
2. Manager of responsible dept can perform authorized status transitions; unrelated manager cannot. Superuser with company-wide read **but no status-change permission** cannot mutate task; explicitly authorized superuser can.
3. Assignee and creator-without-read-scope cannot edit priority; authorized manager/superuser can. Attempted priority edits through PATCH, bulk API, drag-drop, and other endpoints are denied.
4. Assignee can add/check/uncheck checkpoints but cannot change status by completing all of them; manager may edit checkpoint contents. No privilege escalation through checkpoint API.
5. Assignee and manager with task access can add comments and permitted attachments. A comment author can edit only their own comment while preserving revisions; past task access revocation blocks edits; another commenter cannot alter someone else's comment.
6. Assignee deadline edit keeps before/after audit, notifies responsible manager and preserves original/current deadline KPI. Only manager/authorized superuser can reassign executor.
7. Modal is read-only until explicit edit mode for task fields. Server rejects privileged mutations even when client skips edit mode; never rely on the UI to enforce security.
8. Permissions take effect immediately during active sessions. Task creator who assigned another employee cannot read/edit by guessed direct URL or API unless independently authorized.
9. Audit changes with scoped visibility while excluding secret data and full attachment binaries. Permission checks apply to search, export, task detail and realtime data feeds.

## Q20–Q21 acceptance tests — specified, not yet implemented

**Q20 — Saved views**
1. Employee can create/read own personal view; cannot access another employee's private view or publish any shared view.
2. Manager can publish view for a currently managed department; cannot publish it for an unmanaged department by altering API payload/ID.
3. Administrator can publish company-shared view; admin role without task-record access cannot use that view to read unrelated tasks.
4. Company-shared and department-shared views return only records permitted by *viewer's* task ACL, including counts, exports, autocomplete, saved-filter execution, and live updates; unauthorized record ID enumeration returns no content.
5. Role, membership and manager-scope changes immediately affect shared-view visibility; previously shared filters grant no durable rights.

**Q21 — Request template availability**
1. Only administrator can create/edit/publish/deprecate templates or change designated allowed departments, through web API and admin UI.
2. Manager/employee/superuser without administrator grant cannot publish or manipulate template allowlist through direct API.
3. Published template appears only to employees eligible through listed department membership; denial in listing, detail, web form, bot and Mini App for ineligible users.
4. Submission for an unlisted department or with spoofed department ID fails server-side; the same schema/version validation applies to web and Telegram.
5. Publishing new version leaves old published version and existing submissions unchanged; retiring template prevents new unauthorized use without rewriting history.
6. Publication and department allowlist changes recorded in audit; permissions revoked during a session take effect immediately.

## Q22–Q23 acceptance tests (not implemented by document update)

**Q22 group access/privacy**
- Command in approved group returns only a safe private handoff; command in unapproved group is rejected without private data. Disabling a group stops new commands immediately.
- Group response, logs and deep link expose no form answers, task details, assignee lists, private attachments or reusable auth credentials.
- Attempt to replay, swap Telegram user ID, submit from unlinked account, substitute `chat_id`, use expired handoff or alter template department fails closed; Mini App signature/initData and record ACL checks remain mandatory.
- Private submission creates one task via idempotent backend service; no group-chat messages or transcripts are imported into CRM.

**Q23 digest behavior**
- Employee receives only their currently accessible tasks; manager gets only currently managed-department tasks. Role/dept change after scheduling but before dispatch removes stale access. Export/notification payload cannot leak other departments.
- Scheduling uses each configured IANA timezone and works across DST spring-forward/fall-back without duplicate/unintentional sends.
- Retryable send errors are retried finitely; successful sends aren't duplicated; non-retryable errors and exhausted attempts record terminal failure and trigger authorized operator notification without task data leakage.
- Admin can configure digest cadence/time; no magic hard-coded daily time or frequency is assumed. Telegram outage does not break other CRM operations or invalidate unrelated existing sessions.

These are test specifications; actual automated tests and recovery drills must be implemented and executed by the engineering workflow.

## Q24 — Archive acceptance tests (approved policy; not yet implemented)
1. Assigned employee sees own archived tasks via dedicated Archive and `include_archived` filter; another employee (including task creator who is not assignee) cannot read details/list/count/search/export/attachments.
2. Archived task is absent from active Kanban, active My Tasks and ordinary search; appears with explicit archived filtering and valid ACL.
3. Authorized manager's archived tasks are restricted to managed responsible departments; revoked manager permission is effective immediately. Company-wide task-reading superuser sees permitted archived tasks; sensitive actions still need action-specific authorization.
4. Completed-archived tasks contribute to historical completed-task KPIs. Manually archived unfinished tasks do **not** increase completed metrics, including by export or cross-department dashboard.
5. Archive viewing never enables employee manual archival, unarchival, reopening or Trash restore. Direct archived task URL and files always enforce server-side ACL.

## Q25 — Russia VPS and multi-country access tests (policy and readiness checks)
1. Validate selected production provider and physical data-center location in Russia; check DB, persistent file storage, backup and monitoring deployment diagrams against actual configuration.
2. Exercise authenticated CRM access from multiple countries (or safely simulated network locations) without inventing geography-based privilege elevation or blanket country bans. Telegram 2FA and scoped access remain enforced.
3. Inventory and review international flows for Telegram, email recovery, observability, CI, third-party services, backups and remote admins. Block go-live until a documented privacy/legal assessment resolves applicable obligations.
4. Verify off-VPS encrypted backups and DR recovery objectives remain achievable without silently assuming backup jurisdiction. Confirm legal retention/deletion compatibility review covers indefinite audit and Trash.
5. Verify that developer documentation and deploy scripts do not claim **Russian-law/GDPR compliance** merely from Russia-hosted VPS.

## Q26–Q27 acceptance criteria (specifications, not yet executed)

**Q26 — performance, availability and release authorization**
1. Conduct reproducible, realistic **20-concurrent-active-user** load scenarios across personal boards, task detail/save, scoped search, dashboards, notification jobs, and representative uploads. Report error rates, latency percentiles, DB/worker pressure, memory/disk usage; performance thresholds beyond the 20-user capacity target require explicit sign-off.
2. Define and instrument monthly service availability. Verify that reporting distinguishes target **99.5%** from achieved historical availability and identifies outages/maintenance according to an approved measurement policy.
3. Demonstrate that a green test pipeline **cannot** automatically deploy to production without an administrator's separate explicit manual approval; deny unprivileged approvers, replayed approvals and deployments with failed checks. Preserve approval audit, artifact digest and rollback evidence.
4. Validate staging promotion, protected credentials, migrations, backup preconditions and post-deploy smoke checks. Confirm that 4h RTO is treated independently of 99.5% monthly availability.
5. Validate results on an actually selected Russia-hosted VPS, not just a developer laptop; do not claim production acceptance from unrun tests.

**Q27 — v1 feature scope and external references**
1. E2E coverage for tasks, projects, departments, requests/templates and reporting, all under existing ACL and approved Q01–Q25/Q30 rules.
2. Verify that minimal external entity references cannot bypass authorization, inject unsafe URL protocols, or disclose third-party data without independent permission.
3. Confirm v1 API/navigation/migrations do not silently introduce full internal contacts/companies/deals/products modules, import/synchronization or sales pipeline workflows.
4. Check extensibility and modular boundaries allow later modules by separately approved interfaces/migrations; preserve task and analytics contracts.

## Q28–Q29 acceptance tests — approved policy, not yet implemented

**Q28**
1. Employee cannot set `email_verified` by API, account edit, email link or impersonated Telegram callback; only authorized administrator can confirm it using a separately approved manual procedure.
2. Non-admin manager and superuser (without admin identity) cannot confirm recovery email or authorize account recovery. Admin verification/change produces an audit event and verified-by/at metadata.
3. Email change invalidates old verified state; email-only password-reset or MFA-bypass flows cannot grant access. Existing Telegram loss recovery requires administrator mediation, revocation of old binding/challenges and fresh enrollment per Q12.
4. Security event logging does not include raw passwords, binding tokens or unapproved identifying evidence; active session/permission revocation enforced.

**Q29**
1. Base superuser can read tasks across departments (details, search, archive and permission-filtered reports), but all task mutations, status changes, assignment, approvals, archives, Trash and privileged actions return denied without respective action-specific grants.
2. Grant task-update only: can perform specifically allowed updates, but cannot reassign or approve invitations; granting project-invitation approval alone does not allow delete/archive.
3. Independent administrator with no superuser task-read grant cannot automatically browse all task bodies; admin alone can verify employee email, as Q28 specifies.
4. Revoking each permission invalidates subsequent requests during an existing 12-hour session, including any Celery/Telegram related operation. Audit-read remains independent and denied without its separate grant.
5. Confirm that UI disabled controls never replace backend enforcement; direct API calls, bulk operations, search and exports cannot elevate privileges.

**Still OPEN:** identity-verification evidence and emergency recovery, email delivery provider/verification mechanics, exact grant administration / delegation, and other previously logged implementation edge cases.

## REC-01 / REC-02 acceptance tests (requirements, NOT executed)
- An authenticated admin cannot complete employee recovery unless **both** HR record comparison and recorded-manager confirmation succeed. The manager cannot perform the recovery merely because they confirmed identity.
- Standard recovery needs **no** video/photo-ID/biometric scan; no employee self-service email-only reset or Telegram-2FA bypass is available.
- Spoofed manager confirmation, wrong employee/manager, stale/replayed approval, attempts to approve own recovery, and unauthorized superuser/manager recovery are denied and audited.
- Successful approved recovery revokes old Telegram account binding, pending MFA challenges and relevant sessions before allowing enrollment of new Telegram ID with single-use token.
- Sensitive personnel details and tokens never appear in ordinary logs, audit diffs or Telegram group messages; store only minimal status/actor metadata.
- Break-glass administrator cannot be used as ordinary account access, and its access/use is auditable and generates appropriate security alerts. Test recovery in isolated staging after a documented separate emergency procedure is approved.
- **OPEN before production:** exact break-glass factor, custody, activation and rollback; manager confirmation delivery channel and exceptional unavailable-manager cases. Do not claim these have been tested already.

## Implemented automated tests

Which of the scenarios above are executable today. Everything not listed here is still a specification.

### S1.1 (backend: `apps/api/crm/{identity,access,audit}/tests`, run in CI on Python 3.14.10 and 3.15.2)

| Requirement | Covered |
|---|---|
| Q30 | Unique CRM login enforced by service and database; the same Telegram username on two accounts is allowed, the same Telegram numeric ID is not |
| Q13 (password part) | Passwords under 12 characters, common passwords and over-long inputs are refused; strong passwords without character classes are accepted; Argon2id hash stored |
| Q28 (data part) | Verified state cannot be stored without the verifying administrator and an address; uniqueness and normalisation of the recovery email |
| D020 / D032-C1 req. 8 | Revoking a role, changing a role's grants and deactivating a user take effect for an already loaded actor; `permissions_version` is bumped |
| D032-C1 req. 1, 2, 7, 9, 10 | Several roles per user; scope ordering; one central check; every role/grant change audited; negative tests for users without roles, holders of a custom role, system and CLI actors |
| D003 | The administrator role grants no task permission |
| Privilege escalation | Self-assignment of the administrator role is refused; administrator-only permissions cannot be put into a custom role; the last active administrator cannot be removed, also under concurrent requests |
| D032-B1 req. 5, 6 | `/admin` returns 404; first-administrator CLI works once, applies the password policy, never takes the password from the command line, is audited; two simultaneous runs create one administrator |
| Q14 (storage part) | Audit events cannot be updated or deleted through the ORM or raw SQL; deletion is possible only inside a transaction that switched on the cleanup flag |

### S1.2a (backend: `apps/api/crm/identity/tests/test_enrollment.py`, `test_first_administrator.py`)

| Requirement | Covered |
|---|---|
| Q11 issuing | Only a holder of company-wide `user.create` can issue; users without roles, with a department-scoped grant, the account owner, system and CLI actors are refused; the code is stored only as a hash and never appears in audit; a new code revokes the previous one; no code for a bound or deactivated account |
| Q11 redeeming | Binding of the numeric Telegram ID; accounts without a Telegram username; single use; expiry; altered and unknown codes; codes sent outside a private chat (not burned); a Telegram account already bound elsewhere; a deactivated account; username impersonation; two Telegram accounts redeeming one code at the same instant bind exactly one |
| Q11 audit | Every refusal is audited with its reason; the sender always receives the same generic answer |
| First administrator | The CLI prints a binding code once; a new one can be issued from the CLI only for an administrator and only until an administrator has bound Telegram |

### S1.2b and S1.3 — bot and sign-in

Backend: `apps/api/crm/identity/tests/test_auth.py`, `test_auth_api.py`, `test_throttling.py`, `test_tasks.py`, `apps/api/crm/telegram/tests`, `apps/api/crm/common/tests`. Bot: `apps/telegram-bot/tests` (real updates through the aiogram dispatcher, Bot API calls recorded). Web: `apps/web/src/**/*.test.ts(x)`. Browser: `e2e/tests/smoke.spec.ts`.

| Requirement | Covered |
|---|---|
| Q13 challenge | 180-second lifetime (service and database); approval only from the bound numeric Telegram ID; another employee's or an unknown Telegram account refused; no double decision; no decision after expiry, after cancellation, after the binding changed, for a deactivated account; denial ends the attempt |
| Q13 single use | An approval opens exactly one session; a replay, a wrong or missing attempt secret, another browser and an expired approval get nothing; second session for one challenge refused by the database |
| Q13 sessions | 12-hour absolute limit (service and database), not prolonged by use; forged token refused; logout, deactivation and password change end the session at once; another user's sessions are untouched |
| D020 | Rights granted and revoked during an open session show up on the next request without a new login |
| Q13 throttling | Progressive delay after repeated wrong passwords; never permanent; counter starts over after a quiet period and after a successful password; unknown logins throttled like real ones; changing the address does not give unlimited guesses; a stranger's failures elsewhere do not block the owner; one address trying many logins is delayed; Telegram prompts and wrong binding codes are rate-limited |
| No enumeration / no leaks | Wrong password, unknown login, no password, deactivated account answer identically; secrets appear in no response body, `repr` or audit event; the unknown login is not written down |
| Q30 | The Telegram username is not a login; the CRM login is case-insensitive |
| Telegram outage | A queue failure, a temporary Telegram failure (after retries) and a refusal by Telegram all make the login fail closed; an already open session keeps working |
| CSRF | State-changing requests from a foreign origin, and cookie-bearing requests without an origin, are refused, including login and logout |
| Q11 bot transport | `/start <code>` binds the sender's ID; text typed by the user cannot name an account; wrong and used codes get one generic answer; a code in a group is ignored silently and stays valid; ordinary messages are neither handled nor recorded |
| Web | Login form states (errors, waiting, approval, denial, expiry, delivery failure, cancel, temporary server error), POST-only form, relay to the API without client-supplied address headers, outage is not shown as "signed out" |
| Browser (E2E) | Anonymous visitor is redirected to the login page; generic error for wrong credentials; keyboard-only submit; theme; phone width; 401 and origin refusal through the web origin |

Verified by hand on 2026-11-25 in a real browser against a locally started API, worker and web server (Telegram replaced by the recording gateway, the approval given through the domain service): wrong password → approval → session cookie (`__Host-`, HttpOnly, Secure, not visible to page scripts) → reload → logout → denial. **Not automated yet:** this full path in the E2E suite (it needs a way to seed an account and to approve inside the Compose stack), and any run against the real Telegram API.

### S1.4 — accounts and the first password (D036)

Backend: `apps/api/crm/identity/tests/test_users.py`, `test_password_setup.py`. Bot: `apps/telegram-bot/tests/test_password_link.py`. Web: `users-panel.test.tsx`, `set-password-form.test.tsx`, `api-client.test.ts`.

| Requirement | Covered |
|---|---|
| D018 provisioning | Administrator creates a passwordless account with a binding code; duplicate or malformed login, bad email and empty name are refused and create nothing; extra fields in the request (password, roles, Telegram ID, active flag) are ignored |
| Negative authorization | An employee without rights, a system actor and a CLI actor are refused for listing, creating, new code, deactivation and reactivation, in the service and over HTTP (403); anonymous callers get 401; a department-scoped grant is not enough before departments exist; a holder of `user.create` cannot hand out roles |
| D036 | Link issued only for a bound, active account without a password; single use; expiry; a replaced link; a weak password does not burn the link; an existing password can never be replaced; no session is opened; rate limits for requesting and for guessing links; the whole path provision → bind → set password → login → approval ends in a session |
| Deactivation | Session cut on the next request (service and HTTP); login refused; pending codes and links revoked and not restored by reactivation; self-deactivation and deactivation of the last administrator refused; reactivation keeps roles, password and binding |
| Bot | Link sent after binding a passwordless account, not for an account with a password; `/password` sends a fresh link and voids the old one; generic answer to others; ignored in groups |
| Web | Token read from the fragment and removed from the address bar; mismatch caught before any request; server refusals explained; Users screen shows state and only applicable actions, hides what the viewer may not do, confirms deactivation |

Verified by hand on 2026-11-25 in a real browser against a local stack (Telegram replaced by the recording gateway): administrator signs in → creates an employee → code shown once → binding → link → weak password refused → password saved → reused link refused → employee signs in, sees no Users link and gets 404 on `/users` → administrator deactivates → the employee's next page load lands on the login page.

### S2 — organization (`apps/api/crm/organization/tests`, `departments-panel.test.tsx`)

| Requirement | Covered |
|---|---|
| Q01 | First department becomes primary; later ones do not; primary moves only by an explicit audited action; it cannot be left while other memberships exist; one primary per employee enforced by the database |
| Q08 | First manager is designated; designation moves only explicitly; the designated manager cannot be removed while other managers exist; one designated per department enforced by the database |
| Role separation | Only an administrator changes departments, memberships, managers and primary departments — refused for the department's own manager, an ordinary employee, system and CLI actors; belonging gives no rights; the manager role appears and disappears with the fact of managing |
| Scope | A manager's reach is exactly the managed departments: other departments and their people are invisible (404 over HTTP), employees can be created only in a managed department, binding codes only for own people; no deactivation, no role assignment |
| D020 | Removing the manager, closing the department or deactivating the manager removes the reach on the next check and bumps the permission version |
| Web | Departments screen: lists members and managers, read-only without the right, create, add, remove, refusal messages, closed department |

Verified by hand in a browser on 2026-11-25: create a department, add a member and a manager, refusal to close a primary department, new employee placed into a department from the Users screen.

### S3 — tasks (`apps/api/crm/tasks/tests`, `task-board.test.tsx`, `tasks.test.ts`)

| Requirement | Covered |
|---|---|
| D002/D008 visibility | Assignee, manager of the responsible department and superuser see a task; a colleague of the same department, a manager of another department (also through an employee shared between departments), an administrator and non-user actors do not; boards, archive and trash return only what the viewer may see |
| Q02 | The author who is not assignee or manager cannot open or change the task; over HTTP gets a receipt without the task |
| Q19 | For each of eight operations: allowed or refused for the assignee as specified, allowed for the manager, "not found" for four kinds of outsiders, refused for the read-only superuser; interface hints equal what the services allow |
| Q29 | Superuser reads all and acts only with a separately granted permission; an action grant without read access is useless |
| D020 | Removing the manager removes access to the department's tasks on the next call |
| D041 (replaces D016)/Q04/Q05 | A completed task stays on both boards and is not in the archive; it is read-only (five kinds of change refused with `task_completed`); the manager returns it to work from the column, the assignee cannot; tasks completed more than 30 days ago are archived by `archive_completed` — once, with a system audit event, leaving fresh, open and trashed tasks alone — and can still be reopened; the scheduled Celery job is registered and runs it; a manager archives a completed task early; cancelled is neither completed nor archived; manual archive completes nothing; archived tasks are read-only; reopening restores the previous status, is the manager's only, and is refused when that status is gone (Q07) |
| Company structure | The administrator writes what a person answers for (trimmed, ≤300 characters, audited once per real change); a manager and the employee themselves are refused; the note comes back in the department's members and managers; a manager reads only managed departments; an employee gets 403. Web: managers first, employees nested under them, closed departments and deactivated accounts hidden, people without a department listed, read-only without the right |
| D015 | Ticking every checkpoint leaves the status untouched; assignee adds and ticks, only a manager removes |
| D017/Q17/Q18 | Deadline change keeps before/after in history and never rewrites the original deadline; reassignment starts a new assignment time |
| Q06 | Trash hides the task from everybody but those who may restore, removes nothing, restore returns it unchanged; archive and trash are separate |
| D019/Q08 | Open tasks go to the designated manager on deactivation, finished and cancelled ones stay; refusal when nobody can take them |
| Concurrency | A stale edit is refused (409) |
| Web | Columns and the six facts of a card, archive list, read-only window with a separate edit mode, disabled manager-only fields, version sent with an edit, moving by the status list, checkpoint tick, unreadable task, creation receipt |

### Board and statuses: project settings per status (`test_workflow.py`, `workflow-panel.test.tsx`, `task-board.test.tsx`, `tasks.test.ts`)

| Area | Covered |
|---|---|
| Defaults and migration | Existing "in work" statuses stay divided, everything shows the project, a new status is not divided |
| Service | The administrator changes both settings, each change is audited once, an unchanged save writes nothing; dividing without showing is refused on create and on edit; a manager and an employee are refused |
| API | Create and PATCH carry the settings; the refusal has a stable code; the board's status list gives them to every user |
| Statuses screen | A new status sends both settings; dividing is disabled and cleared when the project is hidden; ticking a setting of an existing status sends exactly that; hiding the project also ends the division in one request; a completed status offers no settings |
| Board | A divided status lists the department first and the projects by name, folded with counts, and unfolds one group at a time; an undivided status is a plain list; a status that hides the project shows cards without it; the type of the status does not matter |

Verified by hand in a browser on 2026-11-27 (see the pull request).

### S6 — `/task` in the bot (`apps/telegram-bot/tests/test_task_wizard.py`)

| Area | Covered |
|---|---|
| The whole way | Assignee, title, description, a refused and an accepted deadline, priority, summary; the task is created only after the confirmation, with the right author, assignee, deadline (zone applied) and priority; the assignee gets a notification row |
| Short way | Description and deadline skipped; several departments → the bot asks and offers only that department's people |
| D037 negative | An employee and an unknown sender get the same refusal; a group chat is ignored; a manager removed from the department before the confirmation creates nothing |
| Replay | Double tap creates one task; buttons of an earlier dialogue, of the other dialogue, out-of-range choices and a premature "create" do nothing; `/cancel` ends the dialogue |
| Deadline | `ДД.ММ.ГГГГ ЧЧ:ММ`, date only → end of day, everything else refused |

Not verified: against the real Telegram API.

### S6 — the request dialogue in the bot (`apps/telegram-bot/tests/test_request_wizard.py`, `test_submissions.py`)

| Area | Covered |
|---|---|
| The whole way | A manager answers every kind of question (typed text, money, date, single and multiple choice, employee, file, yes/no), sees the summary, and only then the request is created with `source=telegram`, the checkpoints, the file and the canonical values |
| Skipping and choosing | Optional questions are skipped; with several forms and departments the bot asks for them and offers only people of the chosen department |
| D040 negative | An employee is offered nothing; an unbound sender is refused; an account deactivated mid-dialogue and a template retired before the confirmation create nothing; a group chat is ignored |
| Answers | Wrong numbers and dates are asked again with the reason; typing where a button is expected; file too large, refused content, text instead of a file |
| Replay | A double tap on "Подать заявку" creates one request; buttons of an earlier dialogue, a forged nonce, out-of-range and non-numeric choices and a premature submit do nothing; `/cancel` ends the dialogue |
| Service | A repeated idempotency key returns the same request, somebody else's key is refused; an unknown source is refused; `clean_one` and typed dates follow the form's rules |

Not verified: the dialogue against the real Telegram API and the Redis state storage (tests use the recording session and the in-memory storage).

### S6 — Telegram notifications (`apps/api/crm/notifications/tests`, `crm/telegram/tests/test_gateway.py`)

| Area | Covered |
|---|---|
| Recipients | New task → the assignee only; nobody about their own action; a request by a template is announced as a request; reassignment → the new assignee; deadline moved by the assignee → every manager of the department (D017), by a manager → the assignee; comment → the other side; hand-over on deactivation → the receiving manager; the superuser and the administrator get nothing |
| Content | Exact text of an assignment; the deadline in the configured zone; the link opens the task (own board for the assignee, all tasks for a manager); a comment's text is never in the message |
| Status and invitations | Status moved by the assignee → the managers, by a manager → the assignee, no row for an unchanged status; completion links to the archive; an invitation asks the employee's manager; approval tells the requester and the employee, refusal only the requester and without the reason; an invitation already decided, a requester who no longer runs the project, a removed participant and a manager who lost the department are skipped |
| Q23 re-check at dispatch | A manager removed from the department, a former assignee, a deactivated or unbound recipient and a task in the trash are skipped with a reason code and no message |
| Transactions | A rolled-back change leaves no row; the message goes out after the commit; a refusal by Telegram does not fail the change |
| Delivery | A notification is sent once however often the job runs; a permanent refusal fails at once; a temporary failure is retried and after the last retry marked failed, and is not sent late |
| Storage | The outbox has no text column; nothing is written to the audit log |
| Gateway | No bot token → permanent refusal; a link as a button, or as text for an address Telegram does not accept |

Not verified: delivery of a notification through the real Telegram API (only the fake gateway and the recorded send were exercised).

### S5 — request templates, the administrator's side (`apps/api/crm/request_templates/tests`, `templates-panel.test.tsx`, `form-fields.test.ts`)

| Requirement | Covered |
|---|---|
| Q21 administrator only | `template.manage` belongs to the administrator role and cannot be given through a custom role; a manager, an employee and a superuser are refused for reading, creating, editing, the department list, retiring and publishing — in the service and over HTTP (403) — and change nothing |
| D009 eight types | Every type is stored in canonical form; a ninth type, unknown settings, settings of another type, bad keys, empty labels, inverted limits, bad currency, empty or duplicate options, duplicate keys and oversized forms are refused and leave the draft unchanged |
| D009 immutability | Publishing creates version N+1 from the draft; editing the draft and publishing again leaves earlier versions unchanged; a version cannot be saved or deleted through the model, nor by direct SQL (database trigger); nothing to publish when the draft is unchanged |
| Retiring | A retired template cannot be published and is offered to nobody; its versions stay; it can be brought back |
| Q21 availability, D040 | With no department listed a template is available to nobody; then only to the managers of the listed departments — not to an employee, the administrator or the superuser; unpublished and retired templates are not offered; shortening the list and losing the manager's post take effect on the next call; an unknown or closed department cannot be listed |
| Audit | Creation, edits (which parts, not the contents), department changes, publication, retiring; a field's label does not reach the audit log |
| Web | State of each template, create and open the editor, build a form from several types and save exactly that payload, reorder and remove fields, publish after confirmation only, retire, refusal message keeps the editor open |

Verified by hand in a browser on 2026-11-26: create a template, make it available to a department, add a field of each of the eight types and two checkpoints, save, publish version 1, remove a field, publish version 2, see both versions listed; phone width.

### S5 — requests by a template (`test_submissions.py`, `new-request-dialog.test.tsx`, `task-form-section.test.tsx`, `request-form.test.ts`)

| Area | Covered |
|---|---|
| Submitting | A manager submits a form with every field type and a file: the task is a request, assigned, with the version's checkpoints; values are stored in canonical form; optional fields may stay empty |
| D040 / Q21 negative | An employee, the administrator, the superuser and a manager of another department are refused (403) and are offered no forms; a template not listed for the department, retired, never published or unknown answers "not found" alike; a closed department takes no requests |
| Q02 | Somebody who creates company-wide but cannot read the task gets a receipt and cannot read the answers |
| D009 | After a new version is published an old request still shows its own form and answers; a stale form is refused with 409; new requests use the new version |
| Values | 27 refusals across all types (required, wrong type, length, range, precision, integer, dates, options, duplicates, unknown people, a typed "file", unknown keys) — each names the field and the reason and creates nothing |
| Employee field | Only active employees and managers of the request's department; an outsider and a deactivated colleague are refused like an unknown identifier |
| Files | A required file must arrive; a file for a field that takes none is refused; content rules of Q16 apply; a failure after storing leaves no object in the storage and no rows |
| Reading | Assignee, manager and superuser read the answers; a colleague, another manager and the administrator do not (404); a removed file is shown as gone; a plain task has no form |
| Audit | `request.submitted` carries identifiers and counts; no value, title or file name appears anywhere in the log |
| HTTP | 401 without a session; origin check; error envelope with `details`; malformed payload and stray parts refused |
| Web | Empty state; rendering of a published form and the exact multipart payload; people follow the chosen department; another template starts empty; the refused field is named; a changed template asks to reopen; answers of every type are shown readably |

Verified by hand in a browser on 2026-11-26: a manager opens "Заявка по шаблону", a negative amount is refused by the server with the field named, a full form with a file is submitted, the task window shows the answers, two checkpoints and the file; the assignee sees the answers on a phone-sized screen and has no submit button; a colleague of the same department gets 404 for the answers.

### S4 — projects and invitations (`apps/api/crm/projects/tests`, `projects-panel.test.tsx`)

| Requirement | Covered |
|---|---|
| D018 direct add | A manager adds an employee of a managed department at once; no invitation is created |
| D018 invitation | An employee of another department is only invited: no membership, the project stays invisible to them, the invitation appears for their manager and for nobody else |
| Approval | The manager of the department of participation approves; membership appears only then, with the decision recorded; a second decision is refused |
| Who cannot decide | The requester, the invited employee, a colleague, the administrator and the superuser without the grant get "not found"; a manager who stopped managing the department cannot decide |
| Q29 | A superuser approves only with the separate company-wide grant |
| Q10 | The department of participation must be one of the employee's own (naming the requester's department does not skip the approval); membership and account are checked again at the decision |
| Decline / cancel | Decline grants nothing and keeps the reason out of the audit log; only the requesting side cancels; closing a project cancels waiting invitations |
| **D003 exit criterion** | Fellow participants from the same and from another department, and the other department's manager, see the project and still cannot open or list a task |
| Visibility and control | Participants and the owning department's managers see a project; others, the administrator included, do not; only the owning department's managers change it |
| Roles | The administrator role holds no project permission; the manager role holds both in the database |
| HTTP | The whole flow with four accounts, 403/404 for the wrong people, session required |
| Web | Create, direct add, "only invited" notice, approval inbox, decline, read-only for a participant, refusal message |

Verified by hand in a browser on 2026-11-26 with three accounts: create a project, add an own employee, invite another department's employee (who sees nothing), the other manager approves from the inbox, the employee then sees the project and still no tasks; phone width.

### S4 — a task's project (`apps/api/crm/tasks/tests/test_task_projects.py`, `task-board.test.tsx`)

| Requirement | Covered |
|---|---|
| Optional project | A task is created with or without a project; the manager moves it between projects and out, each change in the history with before and after |
| Manager's field | The assignee and the read-only superuser are refused; people who cannot see the task get "not found"; the lists of projects are refused to an employee, the administrator and the superuser |
| Which projects | Only open projects the manager can see; another department's project becomes selectable once an own employee takes part in it (not while only invited); unknown and closed projects are "not found" |
| **D003** | A task inside a project stays invisible to the project's other participants and to the other department's manager, on boards and by direct ID; the assignee sees it with its project without taking part |
| Read-only states | An archived task's project cannot be changed |
| HTTP / Web | Project on the card and in the detail, change and clear through the edit form, 403 for the assignee, 404 for an unknown project; the new-task form sends the chosen project; card shows "project · department" |

Verified by hand in a browser on 2026-11-26: create a task in a project, see it on the card, clear the project in edit mode.

### S4 — files (`crm/files/tests`, `crm/tasks/tests/test_attachments.py`, `task-board.test.tsx`, `modal.test.tsx`, `api-proxy.test.ts`)

| Requirement | Covered |
|---|---|
| Q16 allowlist | Each accepted type is recognized by content; other extensions (exe, html, svg, js, docm, xlsm, mp4, rar, none) refused; a renamed executable, HTML as PNG, PNG as JPEG, a plain archive as docx, a broken archive refused; empty file refused; document with macros refused |
| Archive bombs | A small archive that unpacks to megabytes and one with too many entries are refused without unpacking |
| File names | Path parts, control characters and over-long names are reduced to a safe display name; the storage key contains nothing of it |
| 100 MB | Exactly the limit accepted, one byte over refused (service); over HTTP refused with 413 both while reading and from the declared length; the web relay refuses an oversized body without reading it |
| Access (Q19, Q02, Q29) | Assignee and manager attach; a colleague, another department's manager and employee and the administrator can neither attach nor download ("not found") and nothing is stored for them; a superuser downloads and cannot attach |
| No way around the task | A file of another task is not reachable through a task the viewer can see; unknown IDs are not found; no session → 401; foreign Origin → 403 |
| Revocation / Q24 | The former assignee loses the files at once; archived tasks keep files downloadable under the same rules and take no new ones |
| Consistency | A refused file leaves no row and no object; if the record cannot be written the stored object is removed; a storage failure is a clean 503-class refusal |
| Removal | Only the manager; the file disappears for every reader, the row and the bytes stay |
| Audit | Upload and removal recorded with ID, size and type; the file name appears in no audit event |
| Download headers | `attachment` with an encoded name, `nosniff`, sandboxing CSP, `no-store`, exact length; the web relay passes them on and nothing else |
| Storage adapters | Local: round trip, never overwrites, unsafe keys refused. S3 (moto emulator): round trip, content type set, no public grant, failures without provider detail, missing settings are a configuration error |
| Web | List with size and author, upload as multipart, refusal message, removal by the manager, no upload form for a reader; the task window no longer closes when a file chooser is dismissed |

Verified by hand in a browser on 2026-11-26 against a local stack (local storage, gunicorn): upload a PDF with a Cyrillic name and download it byte for byte with its name; a renamed executable refused; a 99 MB file uploaded and downloaded byte for byte; a 101 MB file refused; removal. **Not verified:** a real S3 provider; the Docker image and volume (CI builds and starts the stack but uploads nothing there).

### D037 — who creates tasks (`test_tasks.py`, `test_tasks_api.py`, `task-board.test.tsx`)

| Requirement | Covered |
|---|---|
| Manager only | An employee (also for themselves), the administrator and the read-only superuser cannot create a task or ask for the lists of departments and assignees (403 over HTTP); `task.create` is absent from an employee's permissions |
| Managed department only | A manager is refused for another department and is offered only the managed ones |
| Assignee | An employee of the department or a manager of it, including a manager who is not a member and the creator themselves; a manager of another department is refused |
| Revocation | A manager who stops managing the department cannot create tasks on the next call |
| Web | "Новая задача" is offered only with the right; an employee's empty board says who creates tasks |

### S4 — comments (`apps/api/crm/tasks/tests/test_comments.py`, `task-board.test.tsx`)

| Requirement | Covered |
|---|---|
| Q19 who comments | Assignee and manager of the responsible department add comments; a colleague, a manager of another department, an employee of another department and the administrator get "not found" and read nothing |
| Q02 | The task's author without access cannot comment |
| Q29 | A superuser reads comments and cannot write until a separate grant is given |
| Own comment only | The author edits; the manager and the next assignee are refused; a comment addressed through another task is not found |
| Revisions | Every earlier text is kept with its time and editor; author never changes; saving the same text is not an edit; the database refuses an empty body and an inconsistent revision |
| Access revocation | After reassignment the former assignee neither edits nor reads their comment |
| Q24 / read-only | Archived and deleted tasks take no new comments or edits; the archive keeps comments readable under the same rules |
| Audit | Adding and editing are recorded with the comment ID; the text appears in no audit event |
| D038 deletion | The manager deletes anybody's comment: it disappears for every reader, the row stays with who and when, the audit event carries no text; the author, the superuser and everybody who cannot see the task are refused; a deleted comment cannot be edited or deleted again; no deletion in an archived task; delete button only for the manager, with a confirmation |
| HTTP | Round trip, 403 for somebody else's comment, 404 for outsiders and unknown IDs, 400 for an empty text, session required |
| Web | Send and clear the field, edit only one's own, read-only without the right |

Verified by hand in a browser on 2026-11-26: add a two-line comment, edit it, the mark "изменён".

### S3 — status administration (`apps/api/crm/tasks/tests/test_workflow.py`, `workflow-panel.test.tsx`)

| Requirement | Covered |
|---|---|
| D005 role separation | Only `workflow.manage` (administrator) reads or changes the configuration; a department manager and an employee are refused for every operation in the service and over HTTP (403), nothing is audited for them; the board's own list of statuses stays readable |
| D003 | Configuring shows a task count only; the administrator still cannot open a task |
| Q09 retirement | A status in use is not retired without an explicit replacement; tasks move to the chosen status with a version bump and a history entry each; untouched tasks keep their version; earlier events keep the old status ID; the audit event keeps the old name and category |
| Q09 unsafe mapping (provisional rule) | Open → completed, open → cancelled and cancelled → open are refused and change nothing; completed → completed keeps completion time and archive |
| Q05 | A completed task whose previous status was retired reopens into the replacement |
| Guards | Replacement must be another active status; the last "new" status stays; duplicate, empty and over-long names; unknown category; a move to itself, out of a completed status, into or from a retired status; order must list every active status once |
| Rollback | A retired status returns to the board with its moves; tasks are not moved back |
| Web | Type, count and moves per status; no moves out of a completed status; add, rename, reorder, tick a move, retire with a same-kind replacement only, retire unused, return, refusal message |

Verified by hand in a browser on 2026-11-25: add a status, allow moves, move the column (the board shows it in the new place), retire and see it under "Убранные статусы", phone width.

Verified by hand in a browser on 2026-11-25: drag a card to another column, drag to "Готово" (archived, notice shown), open a task by link, tick a checkpoint, edit title and priority, create a task for another employee, "Все задачи", Archive, phone width.

Real Telegram, 2026-11-25, with the owner's bot token and the owner's Telegram account against a throwaway database: the bot connected to the Bot API; `/start <code>` from a deep link bound the account; the login prompt was delivered by the worker; pressing «Подтвердить вход» approved the challenge and the waiting browser session was opened (audit trail: `telegram.bound` → `auth.challenge_created` → `auth.challenge_approved` → `auth.login_succeeded`, 19 seconds end to end). **Not yet observed with a real Telegram account:** the «Отклонить» button and the password link of D036 (the test account already had a password).

Not covered yet from the Q10–Q14, Q28–Q29 and REC lists: audit reading scopes, email verification workflow, recovery workflow, the emergency account, superuser read scope.
