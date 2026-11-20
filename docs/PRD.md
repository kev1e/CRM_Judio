# PRD — Product Requirements v1.3

## 1. Vision / scope

One-company universal corporate CRM for internal tasks and standardized requests, reference UX **YouGile**: intuitive Kanban, minimal UI clutter, few clicks. Initial team up to 20. Not a feature/visual clone; no Dynamics-centric workflows. Must scale without rearchitecting core permissions.

### Actors

- Employee — executes assigned tasks, creates requests, sees own board.
- Department manager — manages assigned departments, adds own-department employees to projects, approves cross-department invitations as defined.
- Superuser — company-wide task visibility, with separately grantable approval powers.
- Administrator — system configuration, departments, roles, templates, automations, users (not automatically entitled to view all tasks unless also a superuser).

## 2. Employees / organization

- Users belong to any number of departments (no artificial one-department limit), have any number of roles; membership and *management* scope are distinct.
- Admin creates departments and configurable roles/permission bundles through UI. Admin and managers can create employee accounts, with managers limited to their managed departments; cannot grant elevated roles without appropriate privileges.
- Each task has exactly one responsible department. Employee sees only tasks where assigned (including assigned requests). Manager sees tasks owned by managed departments; superuser sees all company tasks. Access evaluated independently of project membership, saved filters, analytics.
- Manager can directly add employees of own department to project; employees from other departments require approval from invited employee's department manager or explicitly authorized superuser.
- Employee deactivation blocks sessions immediately; reassign open tasks to manager of employee's **primary department**, or authorized superuser if manager missing. Admin designates exactly one primary department per active employee; change is audited.

## 3. Projects / workspaces / boards

- Both departments and projects are organizational concepts. Staff have **personal boards**, home opens **My Tasks**.
- Columns represent administrator-managed statuses/transitions. Drag-and-drop changes status only if ACL and transition rules permit; optimistic UI must roll back on rejection.
- Small task card displays: title, priority, deadline, checkpoint progress, project/department, assignee. No excess buttons.
- Task opens a **modal** (not side panel); main fields visible, supplemental sections collapsible, read-only until user enters a dedicated edit mode. Light and dark themes, i18n-ready, Russian default.
- Global and within-section searches, all rights-filtered. Filters: status, priority, deadline, project/department, assignee, request type, author. Personal and shared saved views.

## 4. Tasks / requests

- Requests are a **type** of task (`task_type=request` or mapped configurable type), not separate lifecycle entities.
- Creator selects a **specific** assignee from employees available under assignment policy; task immediately becomes assigned without acceptance/manager approval.
- Author, assignee and managers can edit task content subject to read rights and edit permissions. **Only** department manager (within scope) or superuser can change assignee.
- Administrator configures status names, board columns and permitted transitions; statuses editable. In-use status deletion requires explicit admin-approved mapping, transactional migration, preserved history; never automatically choose a replacement.
- Task fields include title, description, priority, deadline, author, single required assignee initially (future multi-assignee extension only), responsible department, optional project, type, status, file attachments, comments, checkpoints, extensible form values, audit history.
- Checkpoints can be pre-provisioned by template and added ad hoc. Completing all **never auto-transitions** the task status. Earlier suggested automation to change status from checkpoints is explicitly superseded.
- Assignee can change deadline; retain before/after history and notify the department manager.
- **Completion / archival:** task explicitly moved to completed status => archive automatically immediately. Keep original status, plus `archived_at`; archived tasks appear in dedicated Archive (accessible according to ACL). Manager within managed scope or authorized superuser may manually archive **even incomplete tasks**. A manual archive does not mark a task completed. Reopen to previous non-completed status is privileged and audited. Completion auto-archival remains atomic.
- Soft-delete is different from archival: deleted_at, Deleted by, trash listing, restore under policy. Never hard-delete attachments/history by simple button; Trash retained without automatic expiry; managers/superusers may soft-delete or restore within scope; only admins may permanently purge, subject to retention and audit safeguards.

## 5. Request template builder

- Admin creates templates in a visual form builder; controls mandatory/optional fields, validations, order, eligibility and default values subject to security.
- Types: text/multiline, number/currency, date/time, select, employee selector, file, boolean, relationship to other CRM record.
- Published templates are versioned and immutable; edits publish a new version; existing requests retain original schema and stored values. Disable/deprecate rather than rewrite historical requests.
- Both website and Telegram forms use same backend validation/template-version policies, no duplicated business logic.

## 6. Telegram

- Employees only; verified Telegram user ID connected to active CRM account. Create requests from bot in private dialogs or corporate groups via wizard and Mini App, selecting authorized assignee.
- No reading/group-chat archive in CRM, no conversation sync, no linking a chat thread to a task. Store minimal provenance (e.g. source, Telegram chat/message ID if strictly needed), with privacy limits.
- Bot sends task/mention/deadline/status/checkpoint/project notifications as selected, and scheduled digest reports. Notification preferences/frequency TBD.
- Login: Telegram username + password -> bot authorization prompt tied to login attempt; verified email as recovery contact, admin-driven Telegram loss/rebinding. Telegram unavailable: Telegram-dependent actions fail safely; existing authenticated web sessions and non-dependent CRM operations continue under normal ACL.

## 7. Analytics / automations

- Employee only own metrics; manager managed departments; superuser company. Metrics: task counts by status, overdue, percent on-time, employee statistics, average completion time.
- Admin-configurable dashboards via visual builder; reports on screen and Excel/CSV export. Filter engine designed to add custom filters and future fields; access restrictions apply to every aggregation and export.
- Admin configures automations: deadline reminders, manager escalation for overdue, task reassignment on deactivation, scheduled digests. **No auto status change on checkpoint completion.**

## 8. Security / operations

- Backend RBAC + department/record scope enforcement; permission updates immediate across active sessions.
- Audit changes to tasks, permissions, users, templates, critical settings (and privileged actions).
- File max 100MB; total volume unknown. Storage abstraction with pluggable local/S3 provider; final provider TBD after volume/security assessment.
- Own VPS with Docker; 3 separate environments (logical isolation, no shared production data/secrets); automated tested CI/CD; observability dashboard and Telegram alerts.
- 30-day backup retention, RPO/RTO and backup cadence TBD after risk assessment; backups external to production VPS, encrypted, restore-tested.

## 9. Non-functional goals

- Responsive desktop/mobile, keyboard-friendly and accessible controls. Russian UI default, localization-ready strings and dates.
- No unapproved quantitative performance/SLA promise. Define measurable p95 response, upload and availability targets before production acceptance.
- No project/role based leakage through APIs, exports, search, notifications, analytics or file URLs.

## 10. Explicit non-goals for first version

- Telegram chat viewer or chat-to-task conversation mirror.
- Multi-tenant SaaS for multiple companies.
- Microservice decomposition.
- All checkpoints completed: status unchanged (D015).
- Generating full product in a single unreviewed Claude Code run.

## 11. Definition of acceptance

End-to-end employee journey: authenticate with Telegram confirmation, open My Tasks, view only assigned tasks, complete checkpoints, change own task deadline with manager notification, mark completed then find in Archive; build a request through web and Telegram; manager see only owned department tasks, approve interdepartmental invitation; superuser view company tasks; admin manage roles/templates/statuses; all attempted unauthorized cross-scope access denied and audited where necessary.

## Approved clarifications Q01–Q09 and Q30 (2026-11-19)

- Each active employee has exactly one administrator-designated primary department. The other memberships are unlimited. If an employee is deactivated, tasks go to the designated responsible manager of that primary dept, else the designated authorized superuser; if neither exists, block deactivation and notify admin.
- Task creator receives only a creation receipt, not ongoing read/edit permissions, when assigning to another employee. Each task has exactly one assignee in v1, with future extension possible.
- Multiple `completed` statuses are allowed, all auto-archive on entry. `cancelled` is separate, must not count as completed. Checkpoint completion alone never transitions status.
- Archive is distinct from completion. Manager/superuser can archive unfinished tasks manually. Archived tasks can be reopened only by an authorized manager/superuser into their previous valid non-completed status; if retired, require explicit mapping. Incomplete manual archives remain incomplete.
- Trash has no automatic expiry; privileged deletion/restoration and admin-only purge. In-use status removal requires explicit mapping with audit/history preservation.
- Every user has unique stable CRM login; Telegram mutable username is only a suggestion at enrollment. Bound Telegram numeric user ID is the identity link.

## Q10–Q12 — approved access and enrollment clarifications

- Multi-department project invite explicitly selects the employee's participation department. Only its responsible manager or superuser holding separate approval permission can approve; verify active membership and approver authority server-side.
- Employee accounts are provisioned by administrator or manager authorized for their department. Initial Telegram linkage is completed through a private bot chat using an expiring one-time enrollment token; never depend on username alone.
- Lost Telegram access is recovered only through administrator-mediated identity verification, revocation of previous binding/challenges, reenrollment and audit. The exact verification procedure remains pending.

## Q19 — Approved task actions and permissions

- Assignee, responsible-department manager and specially authorized superuser can change task status (including completed where appropriate), subject to status transition graph and record ACL; completion immediately auto-archives.
- Only manager or specially authorized superuser can change priority. Assignee may add and check/uncheck checkpoints; manager may also edit them.
- Assignee and manager can add comments and files; edits to a user's own comments preserve full history and require ongoing task access.
- Assignee can still change deadline with auditable history and notice to manager. Only manager/specially granted superuser can change assignee.
- Author may edit task content solely with task record access and action permission; creating someone else's task grants neither. Read-only modal until explicit edit mode, and strict backend checks for every operation.

## Q20–Q21 — Approved saved-view and template scope

**Saved views:** Every employee can create private personal filter views. Managers can publish saved views for their managed departments; administrators can publish company-wide views. Sharing is a convenience feature only: users see only records they can actually read under the central ACL, even when opening a department/company view. Editing and publishing views require corresponding role/scope checks; views must survive normal filter state and may not expose confidential task counts through preview or autocomplete.

**Request templates:** Only an administrator can create, edit and publish a request template or change its department allowlist. Published templates are available to employees of the specifically designated departments, not automatically to the entire company. Each submission (web, bot, Mini App) must use the same server-side department membership and template-version checks. Existing published versions and historical submissions remain immutable.

## Approved Q22–Q23 — Telegram groups, privacy and digest delivery

- Telegram group commands are enabled **only** for an explicit administrator-approved allowlist of group IDs. Group entry presents a safe launch into a private bot DM or authenticated Mini App; form contents and task data must **not** appear in group chat. Apply CRM identity binding (Q11/Q30), task/template rights (Q02/Q21) and server-side ACL to all resulting actions. Do not synchronize chats into CRM.
- **Employee digests** are personal and include only visible assigned work. **Manager digests** are restricted to departments currently managed by the recipient. Reevaluate recipient visibility at send time, regardless of what a prior queued job contained.
- Run schedules in the recipient's individual configured timezone; only administrators control exact hours and frequency. Do not insert a global daily/weekly default without approval.
- Telegram send failures get bounded automatic retries, with final failure recorded and notified to authorized operations staff. A Telegram outage must not block unrelated CRM features or valid existing web sessions.

## Approved Q24 — employee archive experience
- Every authenticated employee can navigate to the dedicated **Archive** screen. Contents are strictly task-record-ACL filtered (employee: assigned tasks; manager: permitted responsible departments; superuser: granted global read scope).
- Archived tasks do not appear in active Kanban boards, "My Tasks" active lists, or normal search. Search includes an explicit **Include archive** filter; accessing an archived task by a direct ID must not bypass its ACL.
- Completed archived tasks contribute to historical completion reporting, subject to the approved analytics definitions and unresolved KPI edge cases. Manually archived unfinished tasks are not completed and do not contribute to completed-task KPI counts.
- Archive visibility does **not** grant permission to manually archive, unarchive, reopen, delete, restore, or change another employee's task.
- Preserve separate historical states for completed/archived/soft-deleted/cancelled; do not silently treat them as equivalent.

## Approved Q25 — deployment and international staff
- Host initial production CRM application and primary PostgreSQL/attachments on a VPS physically located in **Russia**.
- Employees may use the CRM while located in **multiple countries**. UI and timezones remain per-user according to prior decisions.
- Privacy, data-residency compliance, international data transfers and Telegram handling require separate documented assessment before production. No unreviewed third-party data transfer is authorized by this statement.

## Approved Q26 — initial load, availability and releases
- Design the first production release for **up to 20 concurrently active users**; validate with representative multi-role load tests, not just a count of registered users.
- Target **99.5% monthly availability**, measured under a subsequently approved definition. It is an objective, not a current guarantee of the single-VPS architecture.
- Every production deployment requires all mandatory automated checks to pass **and** an explicit manual administrator approval. Staging may remain automated after tests. Record release approver, artifact version/digest, date and outcome.

## Approved Q27 — first-release product boundary
- Deliver task management, projects, departments, requests as task types (including template workflow), reports and analytics.
- Provide only those references to external CRM entities **necessary** for the above workflows; never assume external data sync or read privileges from mere links.
- Full contact, company, deal and product modules are deferred beyond the first release, including their databases, admin CRUD, pipelines, import and search, unless subsequently and explicitly approved.
- Keep extensible modular boundaries so these features can be introduced in later iterations without bypassing current RBAC, audit and search architecture.

## Approved Q28 — Email verification and recovery UX
- An administrator alone can verify and confirm an employee's email in the protected user-management interface. Show verification status and audit metadata to authorized administrative viewers only.
- Employees can request help with lost access but cannot use an automatic email link as sufficient proof to reset a password, remove Telegram MFA, or gain entry. Recovery actions occur only through an administrator-mediated manual workflow and existing Q12 identity check.
- Specific identity-proof, mailbox-check and emergency administrator procedures remain explicitly OPEN; design the interface without claiming unapproved steps have been accepted.

## Approved Q29 — Superuser capability
- Superuser can find and read tasks from every department across permitted read interfaces. Any change, completion, reassignment, department/project invitation approval, archive, restore or deletion requires an explicitly granted per-action right.
- Preserve simple modal view and separate edit mode, disabling unauthorized controls *in the UI*, while enforcing actual denial in DRF backend. Grant changes apply immediately.
- Superuser does not inherit administrator-only email verification, account recovery, template publication or permanent task purge merely from the superuser role.

## Account recovery UX — REC-01 / REC-02 (approved)
- Keep recovery **simple for employees**: contact administrator; administrator checks existing HR records and asks the employee’s recorded manager to confirm identity; no mandatory video call or document-upload flow in standard recovery.
- Administrator performs manual reset/rebinding only after both checks. Employee receives a safe private enrollment method; any old Telegram binding and pending MFA approvals are revoked in accordance with existing approved rules.
- Dedicated emergency administrator account exists for exceptional account-access outages and is protected by a separate procedure; not a standard employee recovery method and not a routine interactive admin UI login.
- Exact verification channel and emergency operator procedure remain unapproved OPEN details.
