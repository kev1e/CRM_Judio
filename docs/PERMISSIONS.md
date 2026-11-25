# Permissions — RBAC + department ownership + record-level constraints

## Model

Use permission grants scoped to `self`, `managed_departments`, or `company`; grants are not inferred solely from role names. `superuser` means company-wide task read; `admin` means configuration (do not conflate). Role grants may union, but explicit protection of sensitive operations and deny-by-default remain mandatory.

Task visibility:
- Employee: `user_id IN task_assignees(task_id)`; a creator **does not gain persistent read access** merely by being author unless the creator also satisfies this rule or has managerial/superuser read scope. Creation flow may show a safe creation receipt without exposing subsequent restricted task data.
- Manager: task's `responsible_department_id` is among departments user actively manages.
- Superuser: all non-deleted tasks in company (deleted/archived are separate permission-gated views).
- Membership in a project or department alone **never** broadens ordinary employee's task visibility.
- Multi-department employee does not cause a task to appear for managers of all their memberships: only task responsible department governs manager visibility.

## Initial capability matrix (proposal implementing confirmed policies)

| Capability | Employee | Department manager | Superuser | Administrator |
|---|---|---|---|---|
| Read task | Assignee only | Managed-dept tasks | Company | Only if separately granted read scope |
| Create task/request | Yes, with eligible assignee | Yes, within assigned scope | Yes, subject to grants | Config role alone does not imply task read |
| Edit task body | Assigned visible task + grant | Managed-dept visible task + grant | Visible task + grant | Need edit grant plus read scope |
| Change task assignee | No | Tasks in managed department | Yes, if granted | Only if also manager/superuser |
| Change own assigned task deadline | Yes, with history/notice | Subject to task edit rights | Subject to grants | Not inherent |
| Manage departments, roles, templates, status configs | No | No unless narrowly delegated | No unless admin role | Yes |
| Create employee account | No | Within managed departments | If also admin/manager | Yes |
| Add own-dept project participant | No | Yes | Only with explicit permissions | Only with explicit permissions |
| Add other-dept participant | No | Request + approval | Approve with explicit approval right | Not automatic |
| Personal analytics | Own | Own + managed dept | Company | Only granted scopes |
| Archive/unarchive/reopen manually | No | In managed dept | Company, if granted | Separate permission; no implicit business access |
| Soft-delete/restore | No | Managed department only | Company only when explicitly granted | No business deletion privilege by default; may delegate separate grants |

## Permission evaluation

1. Authenticate session and ensure active identity.
2. Fetch effective permissions and managed-dept scope from authoritative source; invalidate on permission/membership change.
3. Apply record-level read scope in **database query** (not post-fetch filter).
4. Apply action-specific permission (update, status transition, archive, file, export, invite).
5. Write audit event for material mutation.
6. Publish notifications only to authorized recipients; invalidate existing subscriptions on access loss.

Use read, write, export, comment, upload, archive, restore, configure, invite, approve and admin privileges separately. Negative tests for every role and every access path.

## Multi-department & approval

- Membership in multiple departments is allowed; managed dept list is a separate assignment.
- Each task belongs to exactly one responsible department.
- Inviting employee from department A into B's project: requester manager of B; invited employee's relevant manager of A **or** explicitly authorized superuser approves; until approval no membership or task access granted.
- In multi-department scenarios, requester selects a department of participation from the invited employee's ACTIVE memberships; server checks that membership, requester's rights, and approving manager's scope or the superuser's explicit approval grant. Selection cannot bypass approval or confer task read access. Membership is added only after approval, atomically and with audit.
- On deactivation, incomplete tasks assigned to employee transfer to manager of employee's declared **primary department**, fallback to authorized superuser if unavailable. Prevent self-deactivation causing orphaned manager or race/partial reassignment.

## Immediate revocation

On role/scope/deactivation: bump user permission-version; revoke/refresh server sessions and tokens, invalidate relevant caches and websocket subscriptions. Backend checks current version on critical calls. Frontend clears stale data and reloads permitted views, but this is never enforcement.

## Open design decisions

See `OPEN_QUESTIONS.md`: multi-assignee support, creator access after assignment, permission to mark completed, deletion/restoration rights, primary-department model, superuser modification rights and cross-project scope.

## Approved record lifecycle permissions (Q05–Q09)

- **Soft-delete and restore:** manager within managed department, or superuser holding dedicated permission within company scope. They cannot read or edit records outside their approved task scope.
- **Purge:** administrator only with explicit administrative purge privilege, audited and subject to legal/audit retention rules. Admin status is not general task read access by default; privileged purge uses a separate approved workflow.
- **Archive manually:** manager within department or authorized superuser may archive an incomplete task. This does not complete it. **Reopen:** same privileged actors restore previous valid non-completed status. Ensure a separate operation if merely unarchiving an incomplete manual archive.
- **Deactivate and reassign:** only designated active responsible manager of user's primary dept, otherwise designated authorized superuser. No valid target -> block operation and alert admin. No employee can assign to self by manipulating this workflow.
- **Status remap:** administrator-configured mapping, approved service permission, auditable; must not implicitly grant editors permission to delete statuses.
- **Creator:** no persistent access from authorship alone. One required assignee in v1.

## Approved audit access (Q14)

| Actor | Audit access |
|---|---|
| Administrator | Company-wide audit events, using protected administrative audit endpoints |
| Department manager | Events belonging to currently managed departments only; event-specific record ACL and redaction still apply |
| Superuser | No implied audit access from task-read; requires separate `audit.read` grant and its explicit scope |
| Ordinary employee | No administrative audit access unless separately specified in a future approved decision |

Enforce audit visibility in PostgreSQL querysets and service-level checks for detail, list, filter, export and any live stream. Include `department_id`/event scope or a resolvable snapshot when auditing events, taking care that events involving multiple departments cannot be exposed simply because a viewer manages one of them. Deny by default. Audit cleanup is manual and separately permissioned to administrators, with an independent audit trail.

## Q19 — Approved field/action ACL (2026-11-19)

| Operation | Ordinary assignee (own task only) | Manager (managed responsible dept) | Superuser (company-wide read; action grant required) |
|---|---|---|---|
| Transition status, including completing task | Yes with status-change grant and legal transition | Yes with grant and legal transition | Only with separate status-change grant and legal transition |
| Change priority | **No** | Yes with priority-edit grant | Yes with priority-edit grant |
| Add checkpoint or mark it done/undone | Yes with checkpoint permissions | Yes with checkpoint permissions | Only if separately granted |
| Change checkpoint definition / other checkpoint edits | As separately approved (adding is approved; no blanket structural edits) | Yes with checkpoint-edit grant | Only if separately granted |
| Add comment or attach permitted file | Yes with relevant grants | Yes with relevant grants | Only if separately granted |
| Edit own comment | Yes, if still permitted to access task; append edit history | Same | Same if explicit task access and comment edit grant |
| Change deadline | Yes; audit and manager notice | Per existing scoped edit permission | Only if separately granted |
| Change assignee | **No** | Yes with reassignment grant | Only if specifically granted |

All operations require both record-level read eligibility and action-specific permission. Authorship alone never grants read/edit rights. Checkpoints never change task status automatically. Separate UI edit mode does not replace backend ACL checks. Other fields not explicitly covered retain existing `task.edit` rules, subject to a future detailed per-field review if necessary.

## Q20–Q21 approved authority and scoping

| Action | Employee | Department manager | Administrator | Superuser (without additional role/grant) |
|---|---|---|---|---|
| Create personal saved view | Yes | Yes | Yes | Yes |
| Publish department-shared view | No | Only managed departments | Not by admin role alone unless separately granted department publisher role | No automatic publish right |
| Publish company-shared view | No | No | Yes | No automatic publish right |
| Create/edit/publish request template | No | No | Yes | No automatic right |
| Change template allowed-department list | No | No | Yes | No automatic right |
| Use published template | Only when eligible by configured department scope | Same eligibility policy | Administrative title alone does not bypass user/template eligibility | Same eligibility policy unless another approved explicit grant exists |

All saved views are ACL-preserving server-executed filter definitions; **publication conveys no task-read capability**, including task counts, saved filter suggestions, exports and live subscriptions. Department publishing requires *current* management authority. Templates must be inaccessible to employees not in designated department(s), including by direct URL or API/Telegram submission. Admin-only template operations do not imply company-wide visibility of confidential task content.

## Approved Q22–Q23 — Telegram and scheduled digest ACL

| Operation | Employee | Department manager | Administrator | Authorized superuser |
|---|---|---|---|---|
| Use bot in an approved group | Only with active linked employee account | Same, with own CRM rights | Same, does not grant task-read by admin role | Same, with explicit action grants |
| Add/remove approved Telegram groups | No | No | Yes, audited | No unless separately approved in future |
| Submit private form from approved group command | Only templates available to their eligible department(s) | Same role/template checks | Admin role alone doesn't grant task contents | Only within explicit submit scope |
| Read employee digest | Own visible tasks only | Own personal digest as applicable | No implicit read of others' task content | Authorized task data only |
| Read department digest | No, unless future explicit permission | Currently managed departments only | Only if also separately entitled to task data | Only with explicit scoped reporting permission |
| Configure scheduling/frequency | No | No | Yes | No without separately approved rule |

No group approval, shared view or queue payload may extend recipient record ACL. Enforce query-level visibility and check again when sending. Audit group allowlist changes, schedule changes, unexpected access denials and terminal failures; audit content must not contain secrets or form values.

## Q24 — Archive visibility does not change business permissions
- An authenticated employee can open Archive only to view **their authorized assigned tasks**, subject to currently active record-level ACL; authorship alone does not authorize read.
- Department managers can view archived tasks associated with managed responsible departments; superusers retain only their granted company-wide task-read scope.
- Active boards/search default to `archived_at IS NULL`; dedicated Archive and explicit search `include_archived` remain ACL-filtered. Archived direct-ID requests, exports, analytics and file URLs are not permission bypasses.
- Manual archive/unarchive/reopen remains restricted under Q05/Q07; no implicit edit permission is granted by the Archive feature.
- Q25 international employee location does not change roles, manager scope or permissions. Any geo-restrictions require a separate decision.

## Approved Q28–Q29 — Explicit permission boundaries

| Action | Administrator | Superuser without extra grants | Superuser with action-specific grant |
|---|---|---|---|
| Verify/confirm employee recovery email | Yes (administrator only) | No | No; superuser grant is not administrator identity |
| Manually authorize account recovery | Yes, following separately specified identity-check procedure | No | No, unless also separately an administrator under an approved configuration |
| Read tasks across all departments | Not by admin role alone | Yes | Yes |
| Change task, priority, assignee, status, completion | Only with task-specific rights, not by admin role alone | No | Only relevant action(s) and applicable scope |
| Approve cross-department invitation | Per independently granted business authority | No | Only separate project invitation-approval grant |
| Audit log view / manual archive / Trash actions / permanent purge | Existing separate rules apply | No | Only individually permitted operations; permanent purge remains administrator-only |

All views remain permission-filtered; being a task creator does not grant read. A superuser's company-wide task-read must **not** be implemented as a universal allow for PATCH/POST/DELETE or other mutating endpoints. Permission assignment/revocation is centrally audited and effective during active sessions.

## Recovery authority — REC-01 / REC-02
- **Only administrator** performs email verification and account/Telegram recovery. The manager merely confirms employee identity as the recorded manager; manager confirmation is **not** authority to reset credentials, read secrets or bind a new Telegram ID.
- Require administrator authorization and prevent self-approval/conflict of interest. Ordinary employees, task authors, department managers and task-read-only superusers cannot initiate privileged recovery actions.
- Emergency administrator is a separately protected break-glass account, not a blanket task/content ACL bypass. Restrict it to incident functions and audit use.
- Ensure recovery requests and confirmation metadata are visible only to specifically authorized actors; revoke sessions/bindings before issuing replacement credentials.

## Implementation status (S1.1)

The authorization service is `crm.access.services` (D032-C1). REST views, Celery tasks and Telegram handlers call `require_permission(actor, code, at_least=scope)`; nothing else decides. Grants are read from PostgreSQL on every check.

Permission catalogue so far (codes are added together with the feature that checks them):

| Code | Scopes it can be granted in | Custom roles may hold it |
|---|---|---|
| `user.create` | managed departments, company | Yes |
| `user.read` | managed departments, company | Yes |
| `user.update` | company | Yes |
| `user.deactivate` | company | Yes |
| `user.email.verify` | company | **No** — administrator only (Q28) |
| `user.recovery.manage` | company | **No** — administrator only (Q12, Q28, REC-01) |
| `role.manage` | company | **No** — administrator only |
| `role.assign` | company | **No** — administrator only |
| `audit.read` | managed departments, company | Yes (Q14: a superuser needs this separate grant) |

Rules enforced by the service and covered by tests:

- A user without roles, a deactivated user, and every non-user actor (worker, CLI) hold no permissions.
- Several roles combine; the widest scope per permission wins. A department-scoped grant never satisfies a company-level check.
- The built-in `administrator` role holds every code above company-wide and **no task permission**; it cannot be edited or deleted at runtime.
- Only a holder of `role.assign` can give or take roles; nobody can raise their own rights. The last active administrator cannot lose the role.
- Every role creation, grant change, assignment and revocation is audited and bumps `permissions_version` of the affected users in the same transaction.

Not implemented yet: departments and the resolution of the `MANAGED_DEPARTMENTS` scope against concrete departments (S2), task permissions (S3), the superuser role (S2/S3), the HTTP API and screens for role administration (S2).
