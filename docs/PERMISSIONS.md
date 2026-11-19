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
| Archive/unarchive manually | No | In managed dept | Company, if granted | Not automatic |
| Soft-delete/restore | **UNDECIDED** | **UNDECIDED** | **UNDECIDED** | **UNDECIDED** |

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
- In multi-department scenarios, which department's manager approves must be explicit in invitation data and validated. It must not be implicitly inferred from display order.
- On deactivation, incomplete tasks assigned to employee transfer to manager of employee's declared **primary department**, fallback to authorized superuser if unavailable. Prevent self-deactivation causing orphaned manager or race/partial reassignment.

## Immediate revocation

On role/scope/deactivation: bump user permission-version; revoke/refresh server sessions and tokens, invalidate relevant caches and websocket subscriptions. Backend checks current version on critical calls. Frontend clears stale data and reloads permitted views, but this is never enforcement.

## Open design decisions

See `OPEN_QUESTIONS.md`: multi-assignee support, creator access after assignment, permission to mark completed, deletion/restoration rights, primary-department model, superuser modification rights and cross-project scope.
