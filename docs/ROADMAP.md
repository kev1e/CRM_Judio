# Implementation roadmap — reviewed small increments

**Principle:** These are milestone/sprint groups, not commitments to dates or one gigantic Claude Code generation. Branches and PRs should be narrow and testable. `OPEN_QUESTIONS.md` blockers must be resolved before relevant code.

## S0 — repository + executable foundation

Deliver: polyglot monorepo (pnpm + Turborepo for JS/TS, uv for Python), pinned versions and lockfiles (`pnpm-lock.yaml`, `uv.lock`), Next.js baseline in `apps/web`, Django + DRF baseline in `apps/api`, Celery worker baseline in `apps/worker`, Docker Compose local dev, PostgreSQL + Django migrations baseline (technical table only), lint/typecheck/test for both languages (Vitest + React Testing Library, pytest + pytest-django, Playwright smoke), GitHub Actions CI, environment sample with placeholders, README setup. No real credentials. Review API/OpenAPI style and migrations.

**Exit:** `docker compose` starts; smoke endpoints and placeholder UI work locally, CI passes; no real CRM business logic assumed.

**Status:** done. Merged into `main` on 2026-11-20 with all five CI jobs green. Known S0 limits, intentionally left to later sprints: no TLS/HSTS and no reverse proxy (S8); no shadcn/ui components yet (S3).

## S1 — identity, Telegram enrollment/MFA, users

Q11–Q13, Q28, Q30, REC-01, REC-02 and D032 are approved. Implement verified Telegram binding, login with CRM login + password and per-attempt bot confirmation, progressive rate limits, sessions, admin/manager-managed user creation within allowed scope, revocation, recovery admin workflow. Tests for username change, duplicate binds, replay, rejected challenge, Telegram outage.

**Exit:** real end-to-end authenticated login; Telegram-dependent login blocked when bot offline; safe existing sessions continue; access revokes on deactivation.

Delivery slices (engineering order; the scope above is unchanged):

| Slice | Content | Status |
|---|---|---|
| S1.1 | Audit log (append-only), own user model (Q30 login, Telegram ID, verified-email fields), password policy (Q13), RBAC core of D032-C1 (roles, scoped grants, single authorization service, permission version), CLI that creates the first administrator | Done (2026-11-20) |
| S1.2a | Telegram enrollment, domain part (Q11): one-time binding code stored as a hash, atomic binding of the numeric Telegram ID, refusal and audit of replayed, altered, expired or misdirected codes, binding code for the first administrator from the CLI | Done (2026-11-20) |
| S1.2b | The aiogram bot process (`apps/telegram-bot`, long polling) that receives `/start <code>` in a private chat and calls the binding service | Done (2026-11-25). Webhook mode with the secret-token check waits for the HTTPS ingress (S6/S8) |
| S1.3 | Login (Q13): password check, 3-minute single-use bot approval, 12-hour sessions with immediate revocation, progressive throttling, login screen | Done (2026-11-25). Throttle thresholds are provisional; trying it against real Telegram needs a bot token from the owner |
| S1.4 | User provisioning and deactivation through the API and CRM screens (administrator; managers once S2 departments exist); the employee's own first password (D036) | Done (2026-11-25) for the administrator. Managers' department-scoped part and the hand-over of tasks on deactivation arrive with S2 and S3 |
| S1.5 | Administrator-only email verification (Q28) and the recovery workflow of REC-01 | Planned; the items REC-01 leaves OPEN are not implemented |
| S1.6 | Reserve emergency administrator account (REC-02) and the emergency CLI of D032-B1 | Blocked on the OPEN procedure details; only marking and audit groundwork until they are approved |

The RBAC core is built in S1.1 rather than S2 because user provisioning and every later administrative action need a permission check. Departments, memberships, manager scopes and the `MANAGED_DEPARTMENTS` resolution remain S2.

## S2 — organization & authorization core

Q01–Q03, Q08, Q14 and Q29 are approved. Departments, multi-membership, manager assignments and primary dept, role administration API/UI, resolution of the `MANAGED_DEPARTMENTS` scope in the authorization service (its core arrives in S1.1), scope enforcement hooks/query builder, scoped audit reading. Audit and negative cross-department tests.

**Exit:** employee, manager, superuser, admin privileges distinct and measurable via APIs; access revokes immediately.

**Status (2026-11-25):** departments, memberships with one primary department, managers with one designated manager, the built-in `department_manager` role, resolution of `MANAGED_DEPARTMENTS`, department-scoped account management, and the Departments screen are done. **Not done from the S2 list:** the role administration screen (the service exists; custom roles and role assignment have no API yet), scoped reading of the audit log (Q14; nothing reads the log over the API yet), and the superuser role (it has no meaning before task permissions exist — it arrives with S3).

## S3 — canonical tasks & personal boards

Q01–Q09 and Q30 have been resolved; resolve Q19 (field-level permissions) before implementing edits. Tasks, assignee, single responsible dept, status/transition admin UI, checkpoints, due date, audit, archive/trash, modal details/edit mode, personal Kanban, drag-and-drop, responsive UX, light/dark and i18n structure.

**Exit:** employee cannot enumerate others' tasks; completion auto-archives; checkboxes do not change status; unauthorized transitions denied; history and archive/trash tested.

**Status (2026-11-25):** the core is done — tasks with one department and one assignee, statuses with allowed moves (seeded defaults), checkpoints, deadline with history, field permissions of Q19, automatic archive on completion, manual archive and reopening, trash and restore, hand-over on deactivation, the personal board "Мои задачи" with drag-and-drop, the "Все задачи" board for managers and superusers, Archive, Trash, the task window with a separate edit mode, the common frame with a sidebar. The administrator's Statuses screen (2026-11-25, second slice): create, rename, order, allowed moves, retiring a status with an explicit replacement (Q09) and returning it. **Not done from the S3 list:** permanent purge by an administrator (Q06), the designated-superuser fallback of the hand-over (Q08), live updates of the board, filters and search (S7).

## S4 — projects, invitations, comments and files

Resolve Q10/Q16. Projects and membership, own-dept invites direct, other-dept approval, comments, private upload/download with <=100MB, file storage abstraction. Confirm production storage provider.

**Exit:** cross-dept invitation flow works without granting task read by mere project membership; file IDOR tests pass.

**Status (2026-11-26):** task comments are done — the assignee and the department's manager comment, everybody who sees the task reads, only the author edits and every earlier text is kept, nothing of the text reaches the audit log. Deleting a comment by the manager (D038) and the manager-only creation of tasks (D037) are done. Files on tasks are done (2026-11-26): upload, download and removal under the task's access rules, content checks of Q16, an S3-compatible adapter (D039) and a local one. Projects, participants and cross-department invitations with approval are done (2026-11-26); the exit criterion "membership grants no task read" is covered by tests. A task's optional project is done (2026-11-26). **Not done:** a real object-storage provider and its backups, purge of removed files, mentions and notifications (S6).

## S5 — request templates & web creation

Template builder UI, published immutable versions, all eight field types and validation, eligibility, dynamic fields, task creation with eligible assignee, checkpoint templates, history. Shared service for future Telegram forms.

**Exit:** edit/publish new template does not mutate old request; all field types validated; user cannot submit unsupported/custom values to bypass ACL.

**Status (2026-11-26, second slice):** submitting a request by a template is done — the manager's form on the board, server-side validation of all eight field types, files of the form as task attachments, the version's checkpoints, the answers in the task window for whoever reads the task; one service (`crm.request_templates.submissions.submit`) for the website and the future Telegram form. **Not done:** default values, the Telegram form (S6), filtering by form values (S7).

**Status (2026-11-26, first slice):** the administrator's side is done — templates with a draft and immutable published versions, the eight field types as a validated schema, checkpoints per version, the department list (Q21), retiring, the builder screen. D040: requests are submitted by managers. 

## S6 — Telegram bot/Mini App and notifications

aiogram webhooks, Telegram wizard and Mini App both calling same task creation service, no chat sync, notification service, outbox/retries/idempotency, permissions checked at dispatch.

**Status (2026-11-26, third slice):** `/task` in the bot — a manager gives an ordinary task to a particular employee (owner's request of 2026-11-26): department, assignee, title, optional description and deadline, priority, confirmation; the same `create_task` as the website. Updates of one chat are now handled one at a time.

**Status (2026-11-26, second slice):** the request dialogue in the bot is done — `/request` in a private chat walks a manager through the form of a published template (all eight field types, files up to 20 MB) and calls the same `submit` as the website, with an idempotency key against a double tap; the conversation state lives in Redis for 30 minutes. **Not done:** the Mini App, webhook mode, the group allowlist and hand-off (Q22).

**Status (2026-11-26, first slice):** instant Telegram notifications are done for assignment (new task or request, reassignment, hand-over on deactivation), a changed deadline (D017) and a new comment — through an outbox written in the change's transaction, a Celery delivery with bounded retries, and a re-check of the recipient's read access at send time (Q23). **Not done:** the request wizard and the Mini App, webhook mode, the group allowlist (Q22), notifications about status, checkpoints, mentions and project invitations, deadline reminders, digests, per-user settings and time zones, in-CRM notifications, an operator alert on terminal failure, a sweep that re-queues rows left pending by a broker outage.

**Exit:** authorized employee creates request via either Telegram UI; spoofed/replayed requests rejected; group messages aren't mirrored; task/permission events notify proper recipients.

## S7 — search, saved views, analytics and dashboard builder

Rights-scoped global/local search, all approved task filters, personal/shared views, KPI queries, extensible analytics filter registry, dashboard widget builder, Excel/CSV report export, KPI unit tests.

**Exit:** own/managed/global analytics scopes; no data leaks through aggregates/exports; filters safely extensible without raw query execution.

## S8 — automated schedules, monitoring, operational hardening

Due reminders, overdue escalation, deactivation reassignment, flexible digests (Celery beat; pick an admin-editable schedule store compatible with the pinned Django release), worker reliability, metrics/logs, dashboard+Telegram alerts, staging/prod isolation, CI/CD promotion, external backups and restore drills after RPO/RTO decision.

**Exit:** all test-gated deploys, rollback plan, restore tested, alerts delivered, outbox prevents duplicate actions, production checklist satisfied.

## S9 — UX polish & production readiness

Accessibility, keyboard controls, compact information architecture, user onboarding, translations groundwork, performance/load tests, full traceability matrix, security review and go-live rehearsal.

**Exit:** product owner validates employee/manager/superuser journeys; zero unresolved production blocker; acceptance evidence captured.

## Shared acceptance rule for every sprint

1. Update docs and decision log.
2. Automated tests (unit/integration/e2e as relevant), negative ACL tests and security review.
3. Migration/change safety, realistic seed data without real users.
4. Explain known limitations, remaining tasks and any deviation.
5. No claim of passing a test that has not been run.

**S3 task-lifecycle acceptance supplement:** privileged manual archive of incomplete tasks; manager/superuser scoped restore/reopen; indefinite Trash (manual admin purge only); deterministic deactivation handoff; administrator-approved in-use status mapping; add negative authorization tests.

**S1/S2 prerequisites updated:** implement Q11 enrollment before Telegram-2FA login; model Q12 admin reset and audit without inventing the precise verification procedure; implement Q10 chosen-department approval, membership and server-side scope checks before cross-department invites. Q13/Q14 and Q12 operational recovery detail remain open.

## Q26–Q27 approved scope and delivery gates (applies to S0–S9)
- **S0–S2:** retain auth/role/organization foundations. Initial performance target is **20 concurrently active users**; establish reproducible representative workload and capture capacity baseline.
- **S3–S7:** deliver approved initial features: departments, projects, tasks, templated requests and reports/analytics. Implement only minimal external CRM record references necessary for these workflows; **no internal contacts/companies/deals/products domain modules** in the first release.
- **S8:** make production promotion dependent on automated test results **plus manual administrator approval**, with protected environment, immutable artifact, migration/rollback procedure, audit and staging smoke checks. Validate backup/restore objectives and alerting.
- **S9:** test concurrency (20 simultaneously active users) and the **99.5% monthly availability target** against an explicit measurement definition; document single-VPS risks and measured results, do not claim that a load or SLA test passed unless run.
- Deferred external CRM modules and synchronization require separate design/approval and are not automatically scheduled into initial sprints. Outstanding legal and production-readiness blockers remain.
