# Decision log — confirmed product decisions

Status: **APPROVED** unless marked `PROPOSED` / `OPEN`.

| ID | Decision | Status |
|---|---|---|
| D001 | Internal universal CRM for one company; UX inspired by YouGile, minimal buttons/transitions | APPROVED |
| D002 | Departments and roles are separate; admins create departments and configurable permission roles; user can have multiple roles and memberships | APPROVED |
| D003 | Employee only sees tasks as assignee; manager tasks of managed departments; superuser all company tasks; project membership does not bypass task ACL | APPROVED |
| D004 | Departments + projects; personal staff Kanban; home = My Tasks; task opens modal with collapsible extras and separate edit mode | APPROVED |
| D005 | Admin-managed statuses/columns and legal drag-drop; compact card fields title, priority, due, checkpoint progress, project/dept, assignee | APPROVED |
| D006 | Request is type of task, creator selects eligible specific assignee, immediate assignment; comments/files; checkpoint template and manual additions | APPROVED |
| D007 | Only manager/superuser may change assignee; creator, assignee, manager may edit content subject to read/access scope | APPROVED |
| D008 | One responsible department per task; multi-dept employees' task manager visibility determined by task responsible department | APPROVED |
| D009 | Admin creates versioned visual request templates with 8 field types; historical requests keep published version | APPROVED |
| D010 | Telegram bot + Mini App and bot wizard create requests for authorized employees; no CRM Telegram chat sync/viewer or chat attachment to task | APPROVED |
| D011 | Telegram username/password with bot approval; email recovery contact; Telegram user ID verified; loss of Telegram handled through administrator | APPROVED |
| D012 | In-app + Telegram notifications: assignments, due/overdue, comments/mentions, status, checkpoints, project invitations/approvals, scheduled digests | APPROVED |
| D013 | Employee own analytics, manager managed dept, superuser company; 5 KPIs; visual dashboard builder; Excel/CSV; extensible filters | APPROVED |
| D014 | Admin-only automation configuration; reminders, overdue escalation, reassign on deactivation, scheduled digests | APPROVED |
| D015 | All checkpoints completed do NOT change status automatically; supersedes earlier optional checkpoint-triggered status automation | APPROVED |
| D041 | **A completed task stays in its column for a month, then goes to the archive automatically; "return to work" stays.** Replaces the "immediate automatic archive" part of D016 | APPROVED (2026-11-27) |
| D016 | ~~Enter completed status -> immediate automatic archive~~ (**superseded by D041 on 2026-11-27**); manager/superuser authorized manual archive action; distinct soft-delete Trash and restore | APPROVED |
| D017 | Assignee can change deadline; audit and notify manager | APPROVED |
| D018 | Admin and managers of own dept can create staff; own-dept project invites direct; other-dept requires approval by target-dept manager or privileged superuser | APPROVED |
| D019 | Deactivation reassigns open tasks to manager of employee's primary dept; if none active, authorized superuser fallback | APPROVED |
| D020 | Permissions changes effective immediately including existing sessions; audit significant changes tasks, grants, users, templates, settings | APPROVED |
| D021 | Search global+local; filters by status, priority, due, project/dept, assignee, type, author; personal and shared views | APPROVED |
| D022 | Default Russian + expandable internationalization; light and dark themes | APPROVED |
| D023 | Own VPS + Docker; initial <=20 users; dev/staging/prod; automated test-gated CI/CD; Telegram+dashboard monitoring | APPROVED |
| D024 | Max attachment 100 MB, total volume/storage provider undecided; backup retention 30 days and backup frequency selected after RPO/risk review | APPROVED |
| D025 | Accepted stack (**revised 2026-11-19**, see change log): frontend Next.js + React + TypeScript, Tailwind/shadcn; backend Python with Django + Django REST Framework; Django ORM; PostgreSQL; background workers Celery + Redis; Telegram via aiogram + Telegram Mini App; Docker Compose on VPS; GitHub Actions. NestJS, Prisma and BullMQ are no longer part of the stack | APPROVED |
| D026 | Modular monolith rather than microservices for first release, with the backend implemented on Django/DRF (**approved 2026-11-19**). Repository keeps `apps/web`, `apps/api`, `apps/worker` in S0 | APPROVED |
| D027 | Archive on canonical task using `archived_at` (not copied table); status categories `completed` and `cancelled` distinct | APPROVED |
| D028 | Object storage adapter Local/S3 provider to postpone storage provider decision | PROPOSED |
| D029 | Tooling: pnpm for JS/TS dependencies; Turborepo for monorepo orchestration of build and tests; uv for Python dependencies; Vitest + React Testing Library for frontend unit/component tests; pytest + pytest-django for Django backend, business logic and permissions; Playwright for browser E2E. Vitest is not used for Python packages. CI/CD runs the matching test suites automatically | APPROVED (2026-11-19) |
| D030 | Version policy: use the latest stable release of every program and library, pinned exactly in lockfiles. Supersedes the earlier "do not uncritically choose latest" wording | APPROVED (2026-11-19) |
| D031 | Exceptions to D030: **TypeScript 6.0.3** (latest is 7.0.x) and **ESLint 9.39.5** (latest is 10.x), used after their compatibility with every tool in the repository is verified; **7-day quarantine** for newly published dependencies, with documented exceptions for urgent security fixes. Evidence and the exception procedure in `ARCHITECTURE.md` | APPROVED WITH CONDITIONS (2026-11-19) |
| D032 | Django specifics: **A1** own user model from the first identity migration; **B1** the built-in Django admin site is neither installed nor used and `/admin` is not reachable — all administration goes through the CRM's own Next.js interface over the DRF API; **C1** own scoped RBAC (scopes `OWN`, `MANAGED_DEPARTMENTS`, `COMPANY`) on Django ORM + PostgreSQL, Django Groups and model permissions are not a source of truth for CRM business rights. Mandatory requirements in the section "D032" below | APPROVED (2026-11-20) |
| D040 | **Requests by template are submitted by managers** (not by every employee). Refines D006 and Q21 in line with D037 | APPROVED (2026-11-26) |
| D039 | Task attachments are stored in **object storage** (S3-compatible), not on the VPS disk. Supersedes the storage location of Q16; the other parts of Q16 (allowed formats, 100 MB per file, no mandatory antivirus) stand. The provider, its jurisdiction and backup arrangements are OPEN | APPROVED (2026-11-26) |
| D038 | **Comments can be deleted, by the manager** of the task's responsible department. The author alone cannot delete. **No time limit** for editing one's own comment | APPROVED (2026-11-26) |
| D037 | **A manager creates tasks; the assignee may be a manager or an employee.** Replaces the provisional rule "any employee creates a task for any department" | APPROVED (2026-11-26) |
| D036 | A newly provisioned employee **chooses their own password on a one-time CRM page after binding Telegram**. The administrator never knows or sets an employee's password. Details and safeguards below | APPROVED (2026-11-25) |
| D033 | **Python 3.14.10** is the primary version for development, staging and production. **Python 3.15.2** is used only for an additional compatibility run in CI. A move to 3.15 may be proposed after the critical dependencies (Celery, kombu, billiard, redis-py, pytest-django, drf-spectacular) officially declare support | APPROVED (2026-11-19) |
| D034 | Source control: private GitHub repository `kev1e/CRM_Judio`; development is local and synchronised through Git. No secrets or real credentials in the repository | APPROVED (2026-11-19) |
| D035 | S0 plan approved: Django + DRF backend, pnpm, Turborepo, Vitest, Playwright, uv, pytest, pytest-django, Celery + Redis. Functional sprints do not start until S0 is finished and its baseline checks pass | APPROVED (2026-11-19) |

## D032 — Django specifics (APPROVED 2026-11-20: A1 + B1 + C1)

### A1 — own user model
The CRM user is an own Django model (`AUTH_USER_MODEL`), created by the first identity migration. Django's built-in `auth.User` is not used.

### B1 — no Django admin site
Do not install or use the built-in Django administration panel. Every administrative function is implemented in the CRM's own Next.js interface on top of the Django REST Framework API. Mandatory:

1. One server-side system that checks roles, permissions and access to records.
2. Every change of users, rights, tasks, departments and configuration goes through the corresponding business-logic service.
3. Mandatory audit log of administrative actions.
4. Administrators and managers see only the functions they are allowed to use.
5. Protected CLI commands for emergency restoration of administrative access, with mandatory audit. (The emergency procedure itself is REC-02 and its details are OPEN.)
6. The standard `/admin` route must not be available.

### C1 — own scoped RBAC
Own RBAC implemented with Django ORM and PostgreSQL. Django Groups and standard model permissions are not the source of truth for CRM business rights. Mandatory:

1. Several roles and several departments per employee.
2. Access scopes `OWN`, `MANAGED_DEPARTMENTS`, `COMPANY`.
3. An ordinary employee sees only tasks where they are the assignee.
4. A manager sees tasks of managed departments, determined by the task's responsible department.
5. A superuser sees tasks of the whole company.
6. Changing the assignee is available only to a manager or superuser within their authority.
7. All permissions are checked centrally on the backend.
8. Changes of rights take effect immediately, including for active sessions.
9. All changes of roles and permissions are written to the audit log.
10. Automated access-separation tests.

One authorization service is shared by the REST API, Celery tasks and the Telegram integration.

Consequences fixed in code: `django.contrib.auth`, `admin`, `sessions` and `contenttypes` are not in `INSTALLED_APPS` (guarded by a test); sessions, roles and grants are own tables. The alternatives that were considered (built-in `auth.User`, restricted or primary Django admin, Django groups/permissions, hybrids) are recorded in the Git history of this file.

## Reconciliation notes

- D016 resolves apparent conflict of #81 automatic archive and #82 “manager/superuser archives”: system auto-archive on completion, human-triggered archive/unarchive remains permissioned. Q07 now confirms that privileged manual archival also applies before completion.
- D015 supersedes originally selected potential automation “change status from checkpoints”; user later explicitly chose no status change after completing checkpoints.
- D003 + D007: an author may edit only if task remains visible under assignee/manager/superuser scope; creator status alone does not grant read rights. This exposes a user-experience decision in `OPEN_QUESTIONS.md`.
- Primary department has been resolved under Q01; only admin may change it with audit.

## Change control

Document new approved decisions with date, old behavior, new behavior and affected tests. Claude Code must not silently override a row above.

## Q05–Q09 implementation interpretation and safeguards

- Q05: re-opening is an explicit privileged operation, not simply unsetting `archived_at`. Preserve status history and restore to the last valid non-completed status. If that status has been retired, require an explicit mapped valid non-completed status; do not silently choose. Determine if an earlier manual archive with active status is simply unarchived or treated as reopen; model these operations distinctly.
- Q06: manual purge is not an automatic TTL. Restrict purge to administrator and evaluate legal retention / backups before irreversible removal. Re-check record ACL on Trash and on file restore; purge must not silently destroy required audit evidence. Duration of audit retention remains Q14.
- Q07: manual archive before completion leaves task incomplete, preserves status and completion date as-is, and removes it from active board; track archive reason and actor. It must not inflate completed KPIs.
- Q08: `designated` manager/superuser IDs must be unique per effective scope by validated configuration. Transfer open assigned tasks atomically with deactivation and access revocation; concurrent operations must not leave orphan tasks. If target unavailable, block operation and notify admin.
- Q09: disable/remove status only after an explicit mapping, authorized bulk migration, audit and safe rollback plan; status changes follow role and workflow transition policy. Keep prior status IDs/labels in event history.
- Distinguish `archived_at`, `completed_at`, `deleted_at`; archive, completion and Trash are separate axes. `cancelled` must not be counted as completed.

## Approved Q13–Q14 (2026-11-19)

| ID | Decision | Status |
|---|---|---|
| Q13 | Passwords: minimum 12 characters; reject common/known-compromised passwords; no mandatory periodic rotation. Use progressively increasing rate limiting without permanent account lockout. Telegram login approval challenge expires after 3 minutes and is single-use, bound to the exact login attempt. Web session maximum lifetime is 12 hours, and privilege revocation takes effect immediately. | **APPROVED** |
| Q14 | Audit access: administrator has company-wide audit visibility; department manager may view events within their managed department scope; superuser may view audit events only if separately granted audit-read permission, within its granted scope. Audit retained indefinitely until deliberate authorized manual cleanup. | **APPROVED** |

### Q13–Q14 interpretation and safeguards

- Password breach checks must avoid transmitting raw passwords to untrusted services; require safe local datasets or an anonymity-preserving lookup with robust fallback handling. Hash credentials securely, never log them.
- Progressive throttling should consider account and source/IP signals, avoid permanent lockout, and resist username enumeration and abuse of another user's account. Specific rate-limit thresholds remain an implementation proposal requiring security review.
- Session lifetime: cap authenticated web sessions at 12 hours from issuance; new authentication is required after expiry. MFA challenge must expire within 180 seconds and be single-use. Existing sessions cannot ignore permission revocation.
- Audit viewing and export require scoped query enforcement; event visibility must not reveal confidential records from other departments. Cross-department events require record-scoped rules or redaction, not unconditional disclosure.
- Audit cleanup is **manual only**, requires an explicitly authorized, logged administrative action and applicable legal/retention review. Do not run automatic TTL deletion. Retention includes archived/soft-deleted entities and relevant security events; redact sensitive values.


## Approved Q15–Q16 (2026-11-19)

| ID | Approved decision | Status |
|---|---|---|
| Q15 | Disaster recovery objectives: **RPO ≤ 1 hour**, **RTO ≤ 4 hours**, backups retained **30 days**. Implementation must be designed and tested to achieve these targets; no claim of compliance without a successful recovery exercise. | **APPROVED** |
| Q16 | Store task attachments on **local persistent storage on own VPS** for initial production. Total attachment volume unknown. Allow only document files (PDF, Word, Excel), images and ZIP archives, subject to explicitly maintained allowlists. Maximum upload **100 MB per file**. Antivirus scanning is **not required** in the initial version; security validation and quarantine/restrictions still required. | **APPROVED** |

**Implementation consequences (not separately approved products or settings):**
- Design backup architecture for RPO ≤ 1h and RTO ≤ 4h, with off-VPS encrypted DB and file backups, coherent recovery of DB records and files, periodic restoration drills, alerts and a recovery runbook. PostgreSQL PITR/base backups + WAL archival are the recommended approach; choose exact schedules and tools based on a tested design.
- Local file storage MUST use a persistent mounted volume (not an ephemeral container filesystem), private file authorization, streaming 100MB uploads, MIME/content checks, filename/path safety, archive bomb guards, size/quota monitoring, and independent offsite backups.
- No mandatory malware scanner was approved. This does not authorize indiscriminate downloading/executing uploaded files or bypassing file validation. Document the residual malware risk and revisit scanning before accepting untrusted uploads.
- Unknown total volume leaves VPS disk size, thresholds, quotas, backup-provider choice, encryption key custody, data jurisdiction and restore-tested performance OPEN. Avoid selecting a cloud primary file storage provider without new approval.

## Approved Q17–Q18 — Analytics definitions (2026-11-19)

| ID | Approved decision | Status |
|---|---|---|
| Q17 | On-time completion must report **two distinct indicators** for completed tasks with a deadline: one against the **original due date**, another against the **current due date in force at completion**. Preserve all deadline revisions and their audit history. | **APPROVED** |
| Q18 | Measure task completion duration starting at **assignment to the executor**, not at task creation. Reopened tasks must retain **separate execution cycles** as well as the **overall task completion duration**; do not erase previous cycles or reset the overall history. | **APPROVED** |

### Implementation guardrails

- Never overwrite the original due-date baseline or rewrite historic completion events when a due date changes. Time comparisons must use timezone-aware instants and the same inclusion policy for both Q17 indicators.
- Keep cancelled tasks outside completed-task KPI numerators. Checkpoint completion does not complete a task. A manually archived unfinished task is not completed.
- Record enough immutable assignment, completion and reopening events to compute cycle and overall duration accurately. The current stored `completed_at` and archive flags are not sufficient to retain all prior cycles.
- **Still open (no implicit approval):** handling a task created with no deadline or a deadline assigned only later; treatment of deadline-less tasks in denominators; whether reopened tasks count once or per completion cycle in KPI charts; start timestamp after reassignment; whether cycle duration includes waiting while a task is reopened; business-hours vs elapsed-time metric. These require explicit agreed definitions before final analytics release.

## Q19 — Field-level task permissions (APPROVED, 2026-11-19)

- **Status**: task assignee, manager of task's responsible department, or explicitly authorized superuser may change status, only if record ACL, action permission, and administrator-configured transition rules all permit it.
- **Priority**: only manager of responsible department or explicitly authorized superuser with corresponding action permission. Being creator/assignee alone never authorizes priority changes.
- **Checkpoints**: assignee may add checkpoints and mark checkpoints complete/incomplete; authorized manager may also modify checkpoints. Permission to add/check does not confer permission to complete the whole task or change assignee.
- **Comments/files**: authorized assignee and manager can add comments and permitted file attachments to accessible task. The author of a comment can edit *their own comment* while retaining immutable edit history. Comment author rights must not bypass task read ACL.
- **Completion**: task assignee or authorized manager may transition into an administrator-configured `completed` status if the transition is allowed. A superuser may do this only with a separately granted status-transition permission. Completing a task must atomically auto-archive it (Q04); completing all checkpoints alone must never change status.
- **Task content**: author/assignee/manager may edit only fields their explicit action permissions allow and only for a task visible under existing record ACL (Q02). In particular, creator does not receive persistent read/edit access from authorship alone.
- **Deadline**: assignee remains allowed to change due date, with old/new history and manager notification; prior Q17 original/current deadline KPIs remain intact.
- **Assignee change**: manager or specifically authorized superuser only, within approved scope; unchanged.
- **UI**: task remains in read mode until separate edit mode is activated. Backend restrictions apply even if a client bypasses UI; do not silently change approved minimal UX.
- **Auditing**: status/priority/checkpoint/content/due date/attachments and comment edits produce appropriately scoped audit/history events. No secret or private attachment content in audit log.

These decisions supersede any earlier ambiguous wording about who may complete tasks or edit task priority. They do not approve any changes to project/department scopes.

## Q20–Q21 — Views and request templates (APPROVED, 2026-11-20)

| ID | Decision | Status |
|---|---|---|
| **Q20** | Employees create **personal saved views**; managers publish **department-shared saved views** only for their managed departments; administrators publish **company-shared saved views**. Any saved view is only a query/filter preset and **never expands the viewer's underlying record ACL**. | **APPROVED** |
| **Q21** | **Only administrators** may create, modify or publish request templates, including new immutable published versions. A published request template is available **only to explicitly designated departments**; users and the Telegram bot must meet the same eligibility checks. | **APPROVED** |

**Implementation requirements:**
- Shared-view publication has a mandatory explicit scope (`personal`, `department`, `company`), publisher and audit trail. A department view can cover only departments the publishing manager currently manages. Administrative `company` publishing permission does *not* grant the administrator additional task-read permissions.
- Saved view sharing may not grant access to task details, aggregates, exports or records the viewer would not otherwise be allowed to access; evaluate ACL at execution time, including after department/role changes. View owners/publishers may modify and withdraw their own views only within continuing authorized scope; exact transfer-of-ownership policy on deactivation remains open.
- Templates have administrator-controlled allowed-department membership; default deny if a department is not listed. Versioned template submissions must be rechecked for the caller's eligibility and the task's responsible department. Published versions remain immutable and historical submissions keep their original version; publication/deprecation is audited. Department managers and ordinary employees cannot create, edit, publish or change template eligibility.
- **Open (not implicitly approved):** whether a user eligible through several departments must explicitly pick one when creating a request; effects of changing allowed departments on existing draft requests and historic submissions; employee usability of template listing if manager views differ. Do not invent approval paths.

## Q22–Q23 — Telegram group privacy and scheduled digests (APPROVED, 2026-11-20)

| ID | Decision | Status |
|---|---|---|
| **Q22** | The bot may operate **only in Telegram groups explicitly approved by an administrator**. Group interactions are limited to invoking a command and receiving a safe link to a **private** bot conversation or authenticated Telegram Mini App form. **Never post sensitive form fields, task details or confidential values in group messages.** | **APPROVED** |
| **Q23** | Employees receive **personal** scheduled digests; managers receive digests limited to departments they currently manage. Use each recipient's **individual configured IANA timezone**. Failed sends receive **bounded automatic retries** and **notification of terminal failure**. **Exact times and frequency are configurable by an administrator and are NOT approved defaults.** | **APPROVED** |

### Mandatory interpretation and implementation
- Store and check Telegram group IDs against an administrator-maintained allowlist on every incoming group operation. Deny all other groups and group-originated sensitive submission, regardless of membership or guessed URLs. Administrator changes to the allowlist must be audited and take effect promptly.
- Safe group response contains no private task info, unredacted template metadata or reusable authentication secrets. Private deep links must use non-sensitive, short-lived, one-use context references when they carry context. Server must authenticate the employee by verified numeric Telegram user ID and CRM account, and re-check template department ACL before offering or submitting any form.
- Group entry does not sync chats/transcripts into CRM or connect a group thread to a task; respect earlier Q11/Q21 decisions.
- Scheduled digests and instant notifications are distinct. All digest queries must run with the recipient's **current** per-record ACL at execution/send time; departmental reporting must never leak another department's data. Use user timezones, handle DST deliberately, and ensure idempotency under queued retries.
- Retry policy has finite maximum attempts/backoff and Telegram rate-limit handling; terminal failure is recorded and reported to authorized operators, without leaking confidential content. Preserve in-CRM visibility of failures where relevant. Specific retry numbers, digest clock times and cadence stay **OPEN** until separately agreed/configured; no invented fixed schedule.

## Q24–Q25 — APPROVED (2026-11-20)

| ID | Decision | Status |
|---|---|---|
| **Q24** | Employees may open a dedicated **Archive** view but see only tasks authorized by the same record-level ACL as elsewhere. Archived tasks are excluded from active boards and ordinary/default search results. Search provides an explicit `include_archived` filter. Completed archived tasks count in historical completed-task KPIs; manually archived **unfinished** tasks never count as completed. Existing permissioned archive/reopen actions Q04–Q07 remain unchanged. | **APPROVED** |
| **Q25** | Initial production **VPS and primary CRM data storage are located in Russia**. CRM employees may connect from **multiple countries**. These are geographical/product requirements only; no legal compliance, international transfer, backup location, Telegram data-flow or regulatory basis has been approved. | **APPROVED** |

### Boundaries and follow-up required
- Q24 does not grant the task's creator automatic visibility. Archived task comments/files and direct URLs retain the same scoped ACL; permission changes and deactivation apply immediately.
- Historical KPI access is ACL-scoped, and unfinished manual archives must not inflate completed-task numerators. Archive and Trash remain separate.
- Q25's Russian VPS choice is **not approval** to send backups, telemetry, attachments, employee personal data or Telegram-derived data to providers in unreviewed jurisdictions.
- Before production, document data categories and subjects, actual VPS provider/data-center and backup location, employee countries, controller/operator responsibilities, data-flow map (including Telegram and administrators), applicable Russian requirements and other jurisdictions' laws where relevant, cross-border transfer basis, retention and deletion/legal-hold obligations, encryption and access controls. Obtain qualified legal/security review; leave compliance explicitly **OPEN**.

## Q26–Q27 — APPROVED (2026-11-20)

| ID | Approved decision | Status |
|---|---|---|
| **Q26** | Initial target load: **up to 20 simultaneously active users** (concurrent active sessions/real use; do not confuse with total registered accounts). Target monthly availability: **99.5%**. Promote each production release **only after successful required automated tests AND explicit manual administrator approval**. | **APPROVED** |
| **Q27** | Initial functional scope includes **tasks, projects, departments, request-as-task workflows, reporting/analytics and only the references needed to link external CRM entities**. Full internal CRM modules for contacts, companies, deals and products are **deferred**. Do not implement or imply their full CRUD/domain behavior in v1. | **APPROVED** |

### Explicit boundaries; no implied approvals
- 99.5% is a **target**, not a demonstrated SLA or an infrastructure guarantee. Exact uptime probe, evaluation windows, planned-maintenance treatment and exclusions require future sign-off. In a 30-day month, 0.5% corresponds to ~3h36m downtime; an RTO limit of 4h does **not** by itself guarantee this monthly availability target.
- Load test scenarios and acceptance thresholds (throughput, API response p95/p99, file concurrency, number of Celery tasks, realtime updates) are still **OPEN**; do not advertise capacity until measured under representative load on the selected VPS.
- Production deployment requires a protected manual approval gate **after** passing all relevant CI/staging checks. An automated job may execute an approved deployment, but must not self-approve it. Approval actor/identity, audit record, artifact digest, migration handling, rollback and smoke checks are required. Do not equate administrator approval of a release with permission to read private task data.
- Only store **opaque, permission-controlled external CRM links/references** needed for the initially approved workflows. Their provider identifiers, URL schemes, import/sync, external access rules and exact record types are **OPEN**. Do not create contacts/companies/deals/products internal modules by assumption.
- This changes no Q01–Q25, Q30 or other approved policies; Q25 legal/compliance gate remains OPEN.

## Q28–Q29 — APPROVED (2026-11-20)

| ID | Decision | Status |
|---|---|---|
| **Q28** | **Only the administrator confirms/verifies employees' recovery email addresses. Account recovery is exclusively manual and administrator-mediated.** Email alone never authorizes password reset, Telegram binding reset, MFA bypass or access to an account. | **APPROVED** |
| **Q29** | A **superuser has company-wide read access to tasks**. Editing, reassignment, project-invitation approval, deletion/restoration, status changes, archiving and other mutations/approvals require **separate explicit action-specific permission grants**, and backend must verify those permissions. Company-wide task read is not an implicit write or administrator privilege. | **APPROVED** |

### Scope and non-approvals
- **Q28:** An administrator must manually verify the address and record verification actor/time and audit evidence according to an approved procedure. An employee cannot self-certify an email. A verified email is a recovery *contact*, not standalone proof of identity. Preserve Q12: identity verification and Telegram re-binding controlled by an administrator; revoke old binding and pending MFA challenges. **Still OPEN:** identity proof/evidence, whether a mailbox challenge is required as part of administrator verification, delivery provider, security of offline/manual recovery requests, privileged administrator break-glass, email change/reverification policy, and timing/retention of evidence. Do not silently add self-service email-password recovery.
- **Q29:** Superuser role = company task **read** scope, not automatically task write, administrative configuration, audit access, invitation approval, hard delete, or user recovery. Separate grants for each requested action (and applicable record scope) are mandatory. Rights changes revoke immediately under existing requirements. Deny by default, audit privileged operations. Existing Q05–Q07 and Q19 action rules still apply: where they mention an *authorized* superuser, it means explicitly granted permission.
- Preserve all prior Q01–Q27 and Q30 requirements, including administrator's independent system-configuration responsibilities and non-automatic permission to read task bodies merely by being admin.

## REC-01 / REC-02 — APPROVED (2026-11-20), clarification of Q12 and Q28

| ID | Decision | Status |
|---|---|---|
| **REC-01** | **Simple manual employee identity verification for recovery.** The authenticated CRM administrator compares the employee’s identity against existing internal HR/personnel records and obtains confirmation from the employee’s manager. This two-part check is enough for standard recovery. Do not require video calls, selfies, scans of identity documents, face recognition, external identity-proofing services or multi-stage paperwork as routine mandatory steps. The administrator manually performs/approves recovery, records the manager confirmation and audit outcome, and revokes the old Telegram binding plus active login challenges before new binding. | **APPROVED** |
| **REC-02** | **Dedicated emergency administrator account** for break-glass access, with a separate protected activation and use procedure. It is not an ordinary always-on replacement for normal admin access. Emergency use must be tightly restricted, individually attributable, audited and followed by review and credential/session revocation or rotation as appropriate. | **APPROVED** |

**Scope and boundaries:** These decisions supplement rather than alter Q11/Q12/Q13/Q14/Q28/Q29 and the rest of CRM v2.4. “Simple” means low friction **without** permitting self-service email resets, an email-only MFA bypass, an employee choosing their own approver, or an unauthenticated Telegram identity claim. The manager confirming identity is the manager already established by internal HR/organization records; manager confirmation by itself does not grant administrator recovery rights. Restore access only through authenticated administrator actions and record changes in audit without storing sensitive proof material.

**OPEN (not implicitly approved):** exact personnel attributes compared; manager-confirmation channel and fallback if the named manager is absent or is the recovery requester; specific emergency administrator account custody, separation of duties, activation factor, allowed duration, access/rotation and review procedures; lockout/abuse controls on recovery actions; admin recovery if credentials/MFA and break-glass account both fail. Decide these before production; do not invent an email-only bypass or a production recovery secret in the repository.

## Change log

### 2026-11-19 — technology stack change (D025, D026, D029, D030)

Decided by the product owner before any implementation code existed.

| Area | Old | New |
|---|---|---|
| Backend framework | NestJS + TypeScript | Python, Django + Django REST Framework |
| ORM / migrations | Prisma | Django ORM / Django migrations |
| Background jobs | BullMQ + Redis | Celery + Redis (Celery beat for schedules) |
| Telegram | Bot API (library not chosen) | aiogram + Telegram Mini App |
| Monorepo | TypeScript-only monorepo | Polyglot monorepo: pnpm + Turborepo (JS/TS and orchestration), uv (Python) |
| Tests | Vitest/Jest (undecided) + Playwright | Vitest + React Testing Library (frontend), pytest + pytest-django (backend), Playwright (E2E) |
| Version policy | Stable, "do not uncritically choose latest" | Latest stable of everything (D030); approved exceptions in D031; Python per D033 |
| Architecture status | D026 modular monolith PROPOSED | D026 APPROVED |

Unchanged: frontend (Next.js + React + TypeScript), PostgreSQL, Redis, Docker Compose on VPS, GitHub Actions, the `apps/web` / `apps/api` / `apps/worker` layout, and **every functional requirement of CRM v1.3** (D001–D024).

Affected tests: none existed. `TEST_PLAN.md` now names the tools per layer; the required scenarios are unchanged.

### 2026-11-19 — S0 approvals (D031, D033, D034, D035; D032 pending)

- D031 moved from PROPOSED to APPROVED WITH CONDITIONS: TypeScript 6.0.3 and ESLint 9.39.5 only after a compatibility check with all tools; 7-day quarantine with documented security exceptions.
- D033: primary Python changed from the proposed 3.15.2 to 3.14.10; 3.15.2 kept as a CI compatibility run.
- D032 stays PENDING; S0 was implemented so that it does not prejudge it.

Affected documents: `CLAUDE.md`, `README.md`, `prompts/00-bootstrap.md`, `ARCHITECTURE.md`, `DATABASE.md`, `ROADMAP.md`, `INFRASTRUCTURE.md`, `ANALYTICS_AUTOMATIONS.md`, `TELEGRAM.md`, `TEST_PLAN.md`, `OPEN_QUESTIONS.md`.

### 2026-11-20 — specification v2.5 merged; D032, REC-01, REC-02 approved

- The owner supplied specification bundle v2.5 (approved Q01–Q30, REC-01, REC-02). It was merged three-way with the repository documents: business decisions come from v2.5; the stack change log, pinned versions, D029–D035 and the S0 status come from the repository.
- D027 moved from PROPOSED to APPROVED (with the separate `cancelled` category, per Q04).
- D032 moved from PENDING to APPROVED: A1, B1, C1 with the mandatory requirements listed above.
- REC-01: simple recovery — administrator compares HR data and obtains the recorded manager's confirmation; only the administrator resets access, with audit. REC-02: a dedicated reserve administrator account for emergencies, not for daily use; the details of its guarded procedure stay OPEN.
- S0 was merged into `main` (fast-forward) at the owner's instruction.
- The owner asked to continue development and to settle the remaining questions after the first version of the CRM. Unapproved items therefore stay OPEN in `OPEN_QUESTIONS.md`; where code needs a value that is not approved, it is a clearly labelled provisional setting, never a silent business rule.

### 2026-11-25 — S1.2b and S1.3 implemented (no new product decision)

- The owner asked to go straight to development with the v2.5 bundle; it is the bundle already merged on 2026-11-20, so work continued with the next roadmap slices instead of repeating the S0 readiness review.
- Built: the aiogram bot process (S1.2b) and sign-in with Telegram approval, sessions and throttling (S1.3). Approved rules implemented as written: Q13 (180-second single-use approval bound to the attempt and to the numeric Telegram ID, 12-hour absolute sessions, progressive throttling without permanent lockout, fail-closed during a Telegram outage), Q30, D020, D032.
- Engineering choices that are **not** product decisions and are listed as provisional in `OPEN_QUESTIONS.md`: throttle thresholds; a password change ends the user's sessions; long polling for the bot until an HTTPS ingress exists; cookie-based sessions with an origin check; the web application relays `/api/v1/*` to the API.
- Still needs the owner: a bot token from @BotFather to try the flow against real Telegram; how a newly provisioned employee gets a password (before S1.4).

### 2026-11-25 — D036 approved; S1.4 implemented

- **D036 (owner, 2026-11-25):** "сотрудник сам задаёт пароль на одноразовой странице после привязки Telegram". Implemented as: the account is created without a password; right after the employee binds Telegram with the one-time code, the bot sends a one-time link to that Telegram account; the page sets the password. The link works once, for a limited time, only while the account has no password, and does not sign anybody in. `/password` in the private chat sends a fresh link. Replacing an existing or forgotten password is **not** possible this way — that remains administrator-mediated recovery (Q28, REC-01).
- The owner supplied a bot token; the bot was started against the real Telegram API from the development environment (see `TEST_PLAN.md` for what was observed).
- The owner allowed Claude to open pull requests without asking.
- Built in S1.4: provisioning, a new binding code, deactivation and reactivation of accounts through the API and the Users screen. Engineering choices listed as provisional in `OPEN_QUESTIONS.md`: 30-minute lifetime of the password link; reactivation restores the account with its roles, password and binding but nothing that was revoked; before tasks exist, deactivation has nothing to hand over (D019/Q08 join the same transaction in S3).
- New setting `TELEGRAM_API_BASE_URL` (default: Telegram's own server) for a self-hosted Bot API server or a relay, in case the production network cannot reach Telegram directly. Whether one is needed on the Russian VPS (Q25) is an infrastructure question to check at deployment.

### 2026-11-26 — D037, D038, D039 approved

The owner's words: "1. Руководитель ставит задачи, исполнителем может как руководитель так и сотрудник. 2. Нужно удаление, разрешено руководителю, ограничения времени правки не надо. 3. В объектном хранилище."

- **D037**, implemented as: `task.create` is no longer held by every employee; the department manager holds it for the managed departments, so a manager creates tasks for a department they manage. The assignee is an active employee of that department or an active manager of it (a manager need not be a member). An ordinary employee cannot create a task, not even for themselves.
  - Interpretation by Claude, to confirm: "for a managed department only" (a manager cannot address a task to another department), and "assignee from the same department". A wider reach is possible through a custom role with a company-wide `task.create`.
  - Consequence to resolve before S5: D006 says a request's creator selects the assignee. If ordinary employees are to submit templated requests, that needs its own rule; D037 as implemented does not let them.
- **D038**, implemented as: new permission `task.comment.delete` held by the department manager for managed departments. A deleted comment is hidden from everybody and kept in the database with who deleted it and when; the audit log records the deletion without the text. Restoring a deleted comment is not built.
- **D039**: recorded; file storage is the next slice. Q16 previously said "local persistent storage on own VPS" — D039 replaces that part. OPEN: which provider (and whether it satisfies Q25 data-residency expectations), bucket encryption and key custody, how backups of the bucket meet Q15 (RPO ≤ 1 h, 30-day retention).

### 2026-11-26 — attachments implemented (D039, Q16)

- Built: files on tasks. Storage is behind one interface with two adapters: S3-compatible object storage (`FILE_STORAGE=s3`, D039) and a local directory for development and tests (`FILE_STORAGE=local`, the default of the local Compose stack). Nothing but the API reads the storage: a download is authorized against the task and then streamed through the API; there are no public or pre-signed addresses.
- Q16 as implemented: extensions pdf, doc, docx, xls, xlsx, png, jpg/jpeg, gif, webp, zip; the content must match the extension; 100 MB per file checked from the declared length, while reading and on the stored size; archives are inspected by their table of contents only and refused when they unpack to too much; documents with macros (docm/xlsm, or a `vbaProject.bin` inside docx/xlsx) are refused. No antivirus scan (Q16).
- New dependencies: `boto3` (runtime) and `moto`, `boto3-stubs` (tests and typing).
- Not a product decision, listed as provisional in `OPEN_QUESTIONS.md`: who removes a file (the manager), the archive limits, legacy `.doc`/`.xls` accepted without macro inspection, downloads not written to the audit log.
- The S3 adapter was exercised against the `moto` emulator only. It has **not** been run against a real provider: none is chosen yet.

### 2026-11-26 — projects and invitations implemented (D004, D018, Q10; no new product decision)

- Built: projects owned by one department, participants, and the invitation of another department's employee with approval. Approved rules implemented as written: a manager adds an employee of a department they manage directly; anybody else is invited and gets nothing until a manager of the department of participation approves, or a superuser with the separate `project.invitation.approve` grant (Q29); the requester names the department of participation among the employee's current departments and everything is checked again at the decision (Q10); membership never shows a task (D003).
- The administrator role holds no project permission (capability matrix: "only with explicit permissions").
- Tasks are not linked to projects yet (the "optional project" field of a task): next slice.
- Provisional choices are in `OPEN_QUESTIONS.md`.

### 2026-11-26 — a task's optional project implemented (PRD "optional project"; no new product decision)

- A task may carry one project. The manager of the task's department chooses it at creation or later (`task.project`, a manager's field like priority) among the open projects they can see. The card shows "project · department".
- The project is a label for grouping. It gives nobody access to the task (D003): covered by a test in which fellow participants of the task's project still cannot open it.

### 2026-11-26 — D040 approved; request templates, the administrator's side (S5, first slice)

- **D040 (owner, 2026-11-26):** "Подает заявки по шаблонам руководители". Implemented as: a template is offered to a manager for the departments they manage that are on the template's list (Q21). An ordinary employee, the administrator and the read-only superuser are offered nothing. This closes the conflict between D006 ("creator selects the assignee") and D037 noted earlier, and the open point of Q21 about a user eligible through several departments: the manager names the department explicitly when submitting.
- Built: templates with a draft and immutable published versions (D009), the eight field types of PRD §5 as a validated schema, checkpoints per version, the list of departments, retiring, the administrator's "Шаблоны заявок" screen. Only `template.manage` (administrator, built-in roles only) manages them (Q21).
- A published version is immutable in the database as well: a trigger refuses UPDATE and DELETE on `request_templates_version`.
- **Not built yet:** submitting a request by a template and showing its values in the task — the next slice.

### 2026-11-26 — requests by a template (S5, second slice)

- A manager submits a request by a template for a department they manage, if the template is available there (D040, Q21). The check order is: the right to create tasks for the department first, then the template — somebody without the right learns nothing about templates.
- One service, `crm.request_templates.submissions.submit`, validates and creates; the website calls it and the Telegram form will (PRD §5: no duplicated business logic). Values are validated by `crm.request_templates.values` against the published version; unknown keys are refused, not ignored.
- The request is an ordinary task of type `request` (D006): assigned at once, with the version's checkpoints, in the starting status. The answers live in `request_templates_submission`, pointing at the immutable version (D009).
- The answers are shown by `GET /tasks/{id}/form`, which goes through the task's read check (D003): the creator who cannot read the task (Q02) cannot read its answers either.
- Nothing typed into a form reaches the audit log: the event `request.submitted` carries the template, the version, the source and counts only.
- Task creation, attachments, the submission row and the audit event are one transaction; files stored before a failure are removed from the storage.
- Provisional choices are listed in `OPEN_QUESTIONS.md` (latest version only, files and their limit, numbers, required "yes / no", no editing of answers).

### 2026-11-26 — Telegram notifications, first slice (S6)

- An outbox (`notifications_notification`): the domain service writes a row per recipient inside its own transaction and the delivery job is queued after the commit. A rolled-back change notifies nobody; Telegram or the queue being down never fails the change (Q23).
- The job carries only the row's ID. At send time the recipient must be active, bound to Telegram and able to read the task by the same check as the CRM (`task.read`); otherwise the row is marked skipped with a reason code. The text is composed at that moment and never stored.
- Delivery is idempotent on the row's status under a row lock. A crash between Telegram accepting the message and the commit can still produce one duplicate — the same accepted risk as for the login prompt.
- `TelegramRetryAfter` (flood limit) is treated as temporary, in the login prompt too.
- Recipients, wording, retry numbers and the single time zone are provisional (`OPEN_QUESTIONS.md`). No new permission: being notified follows from being able to read the task and being its assignee or its department's manager.

### 2026-11-26 — the request dialogue in the bot (S6, second slice)

- `/request` is an adapter: it collects answers and calls `submissions.offers`, `tasks.eligible_assignees`, `values.clean_one` and `submissions.submit` — the services of the website (PRD §5: one validation for both). Each answer is checked at once by `clean_one`; `submit` checks the whole form again.
- The sender is identified on every step from the numeric Telegram ID of the update and must be an active bound account (Q30). The conversation state is never a source of identity or rights.
- Buttons carry a per-dialogue nonce; a button of an earlier dialogue, of another step or with an out-of-range choice does nothing.
- A submission carries an idempotency key generated when the dialogue starts (`request_templates_submission.idempotency_key`, unique): a repeated delivery of "Подать заявку" returns the same request. The state is cleared before submitting.
- State storage: aiogram FSM in Redis with a 30-minute limit (TELEGRAM.md). It holds the answers until submit or cancel; nothing typed is logged.
- A file is downloaded and checked when sent, and downloaded again at submit; only Telegram's `file_id` is kept in between.

### 2026-11-26 — `/task` in the bot (owner's request)

- The owner asked (2026-11-26) to add creating tasks for particular employees through the bot ("Задача через бота"). Built as the `/task` dialogue in a private chat. It changes no rule: D037 stands — only who may create tasks for a department (its manager) gets the dialogue, and `tasks.create_task` decides.
- Somebody who creates no tasks — an employee, an unbound sender — gets the same single refusal.
- The dispatcher now handles the updates of one chat one at a time (`SimpleEventIsolation`), so a double tap cannot create two tasks: the second tap finds the dialogue finished.

### 2026-11-26 — more notifications (S6, fourth slice)

- A notification is about a task or about a project invitation — exactly one (database constraint).
- At send time: a request to decide goes only while the invitation is still pending and the recipient may still decide it (`invitations_to_decide`); a decision goes only to a requester who still runs the project; "you joined" only to somebody who is still a participant.
- A completed task's link opens the archive.

### 2026-11-27 — sub-columns by project inside a status (owner's request)

- The owner asked for the board's status columns to be divided: the department's own tasks apart from the tasks of each project, **without** a switch between "by status" and "by project".
- Built in the web interface only: inside a status, tasks without a project are grouped by department and shown first, then one sub-column per project, by name. Sub-columns appear only when the board holds more than one such group, and a status shows only the groups it has tasks in.
- The grouping is computed from the cards the API already returned for the viewer; no project or department is shown that the viewer has no task in (D003, Q02). Dragging between statuses is unchanged and never changes the project.

### 2026-11-27 — the same sub-columns in every status (owner's correction)

- The owner asked for the division to be present "in all columns, both in My tasks and in All tasks". Now every status shows the same sub-columns — every department and project the board's tasks belong to — including empty ones, on both boards, even when there is a single group. An empty board keeps plain columns. Supersedes "a status shows only the groups it has tasks in" of the previous entry.

### 2026-11-27 — work in progress by project, folded (owner's change)

- The owner changed the request: the division by projects applies **only to tasks in work**; the other statuses are one plain list; projects are shown as **expandable lists**, so that one sees which projects are in work and unfolds a project to see its tasks. Supersedes the two previous entries about sub-columns.
- Built: in every status of the category "active" the column lists the department (tasks without a project) and each project that has tasks in that status, folded, with a count; a click unfolds the tasks. Groups are stacked, so the column keeps its ordinary width.
- A card moved into such a status unfolds its group, so it does not seem to vanish. What is unfolded is kept while the page is open, not between visits.
- Interpretation, to be confirmed by the owner: unfolding a project shows its tasks **in that status** (in work), not its tasks from "Нужно сделать".

### 2026-11-27 — per-status project settings (owner's request)

- The owner asked for a checkbox "divide tasks by project" when creating and editing a status, and for a setting "whether there is a project in the status at all".
- Built as two settings of a status, managed with `workflow.manage` (administrator) and audited (`task_status.display_changed`): `show_project` — whether cards in the column name their project; `group_by_project` — whether the column is the folded list by project. Dividing requires showing (service check and database constraint).
- They replace the fixed rule "statuses of the category *active* are divided". The migration keeps today's picture: existing *active* statuses start divided; everything shows the project. A new status is not divided unless asked.
- Presentation only: no rule of access, workflow or notification depends on them. The task window still shows the task's project to whoever may read the task.
- Interpretation, to be confirmed by the owner: "whether there is a project in the status" is taken as "whether cards in this column show the project". It does not forbid a task with a project from being in the status.
- The settings are not offered for a status of the category *completed*: a completed task leaves the board at once.

### 2026-11-27 — Company structure (owner's request)

The owner asked for "a hierarchy tree: who is a manager, who is that manager's employee, who answers for what; editable, and people get into it automatically".

- Built as the screen «Структура»: open departments, their managers (the designated one first) and, under them, the department's employees. It is **derived from the departments**, not stored separately, so an employee appears in it the moment they are put into a department and moves with every change of members or managers. A second, independent "who reports to whom" table was deliberately not introduced: it would diverge from the departments that define access.
- "Who answers for what" is a new free-text note on the account, `identity_user.responsibility` (up to 300 characters), edited in the tree. It is a description only: no right depends on it. Changing it is `user.update` (administrator) and is audited (`user.responsibility_changed`).
- Changing who is in which department and who manages it stays on the «Отделы» screen (`department.manage`); the tree links there.
- Visibility follows the existing `department.read`: the administrator sees the whole company (and the list of people in no department), a manager sees the managed departments, an ordinary employee does not see the screen. No new permission was invented.
- Interpretations to be confirmed by the owner: see `OPEN_QUESTIONS.md` ("Company structure").

### 2026-11-27 — D041: a completed task stays on the board for a month (owner's decision)

- **Owner, 2026-11-27:** "сделать так чтобы задача в готово лежала месяц после чего она улетала в архив, но оставить функцию вернуть в работу". This replaces the part of D016 "enter completed status → immediate automatic archive" and the matching line of `CLAUDE.md` and PRD §Q04. The rest of D016 stands: manual archive by a manager, Trash separate.
- Completing sets `completed_at` and keeps the task in its column on both boards. The database constraint "completed ⇒ archived" is removed.
- The worker's scheduler (new `beat` service) runs `tasks.archive_completed` every hour: tasks completed more than `COMPLETED_TASK_ARCHIVE_AFTER_DAYS` (30) days ago are archived, each with an audit event `task.archived` (`completed: true`, `reason: retention`, no human actor). Tasks in the Trash are left alone.
- "Вернуть в работу" works from the column and from the archive alike, with the same right as before (`task.archive`: the department's manager; Q05, Q24). The task returns to the status it had before completion (Q07 unchanged).
- A manager may also send a completed task to the archive at once.
- Analytics are unaffected: completion time is still `completed_at` (Q17, Q18).

PROVISIONAL (see `OPEN_QUESTIONS.md`): "a month" is 30 days; a completed task is read-only until reopened (no edits, comments, files or checkpoint ticks); the assignee cannot reopen their own completed task.
