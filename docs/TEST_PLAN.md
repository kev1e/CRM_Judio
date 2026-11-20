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
