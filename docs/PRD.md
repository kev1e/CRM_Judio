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
- Employee deactivation blocks sessions immediately; reassign open tasks to manager of employee's **primary department**, or authorized superuser if manager missing. **Open question:** how primary department is designated when memberships are otherwise unlimited; see `OPEN_QUESTIONS.md`.

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
- Administrator configures status names, board columns and permitted transitions; statuses editable. Changes require migration/mapping policy for existing tasks; see open questions.
- Task fields include title, description, priority, deadline, author, assignee(s) if schema supports expansion, responsible department, optional project, type, status, file attachments, comments, checkpoints, extensible form values, audit history.
- Checkpoints can be pre-provisioned by template and added ad hoc. Completing all **never auto-transitions** the task status. Earlier suggested automation to change status from checkpoints is explicitly superseded.
- Assignee can change deadline; retain before/after history and notify the department manager.
- **Completion / archival:** task explicitly moved to completed status => archive automatically immediately. Keep original status, plus `archived_at`; archived tasks appear in dedicated Archive (accessible according to ACL). Manager or superuser controls any manual archive/unarchive actions, not the automatic system transition.
- Soft-delete is different from archival: deleted_at, Deleted by, trash listing, restore under policy. Never hard-delete attachments/history by simple button; retention/permanent purge policy TBD.

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
- Automatic status transition when all checkpoints completed.
- Generating full product in a single unreviewed Claude Code run.

## 11. Definition of acceptance

End-to-end employee journey: authenticate with Telegram confirmation, open My Tasks, view only assigned tasks, complete checkpoints, change own task deadline with manager notification, mark completed then find in Archive; build a request through web and Telegram; manager see only owned department tasks, approve interdepartmental invitation; superuser view company tasks; admin manage roles/templates/statuses; all attempted unauthorized cross-scope access denied and audited where necessary.
