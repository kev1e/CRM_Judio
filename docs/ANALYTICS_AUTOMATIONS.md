# Analytics, dashboard builder & automations

## Approved analytics scope

- Employee: metrics only on employee's assigned tasks.
- Manager: metrics for tasks owned by managed departments.
- Superuser: company-wide task metrics.
- Administrator: configuration rights do **not** automatically grant task-data analytics.
- Same server-side scoped query filters apply for widgets, exports, drilldowns and saved views.

## Approved KPI catalog

1. Count of tasks grouped by status (include/exclude archive parameter explicitly).
2. Overdue tasks: task due date passed and task not completed/archived, per a consistent definition.
3. On-time completion percentage: completed <= due date / completed tasks with deadline; whether undated tasks excluded and how revised deadlines handled are **open**.
4. Employee stats: assigned/completed/overdue counts, source scoped.
5. Average completion time: `completed_at - created_at` (or assigned_at if later decided), exclude reopened cases if definition says so — **open**.

All dashboard calculations need documented definition, UTC storage, report timezone, sample fixture tests, sensible handling of empty denominators.

## Future-proof analytics filtering

- Typed declarative filter registry: `id`, `label`, `data_type`, allowed operators, field/path mapping, scope, optionally template field version.
- Initial filters: status, priority, deadline/range, project/department, assignee, request type, author, time range.
- Add new filters later without rewriting dashboards; validate filter expressions, limit nesting/complexity and bind query parameters (never interpolate SQL input).
- Saved personal and shared views; sharing cannot extend recipients' data access. Revalidate at every execution.
- Dashboard builder allows authorized users/admin-designated authoring with predefined safe widgets, not user-entered JS/SQL.
- Exports Excel/CSV use the identical scoped query, safe escaping and audit.

## Approved automations

- Reminder before due date; manager notification upon overdue.
- Reassign active tasks when user deactivated to primary-department manager, fallback authorized superuser.
- Flexible-schedule digest to recipients with appropriate scope.
- Admin is sole rule editor; workers can be retried without duplicate tasks/notifications.
- **Conflict resolution:** earlier option “automatically change status when all checkpoints complete” is superseded by approved rule #59: checkpoint completion **never** modifies task status. Do not ship automatic status transitions based on checkpoints.
- Task completion still invokes automatic archival as separate approved rule #81.

## Scheduler design

Celery tasks scheduled by a single Celery beat instance, with idempotency and timezone-aware schedules. Admin-editable schedules need a database-backed schedule store; as of 2026-11-19 `django-celery-beat` 2.9.0 declares `Django<6.1` and cannot be installed with Django 6.1, so the store is chosen in S8 (a newer release of it, or own `scheduled_reports`/`automation_rules` tables polled by one periodic task). Avoid sending full confidential task content in queue payload. Recheck permissions at execution/send time. Provide audit/config history and operation metrics for failed/late jobs.

## Open metrics decisions

What counts as complete/closed, historical changes to deadlines, reopened tasks, tasks without deadlines, deleted/archived inclusion, how manager counts multi-assignee tasks, shared dashboard editors, max export size, notification lead times and scheduled report retention.
