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

## Approved Q17 — on-time completion dual KPIs

Report two separately named on-time-completion percentages using the same ACL-filtered eligible task population:
- **Original-deadline on-time rate**: compare completion timestamp against the initial recorded original due-date baseline.
- **Current-deadline on-time rate**: compare completion timestamp against the due date effective at the moment of that completion.

Track immutable original baseline and append-only due-date changes. A later due-date edit must not retroactively change a historical cycle's due date at completion. Exclude cancelled records from completed task counts. No-deadline rules and whether reopened cycles count separately in the rate remain **OPEN**, so no silently chosen denominator/aggregation policy.

## Approved Q18 — completion duration and reopened cycles

- Begin measurement at **assignment to the task's executor**, not task creation.
- Record each completion/reopening cycle separately, with timestamps, actor and cycle index or immutable event references.
- Report both **per-cycle completion duration** and **overall completion duration** without discarding any historic completion/reopening cycle.
- Do not zero out earlier duration when reopening or changing status.
- Exact reporting treatment of reassignment, reopened-cycle start, active/waiting time, and population/aggregation remains **OPEN**.

**Superseded draft definitions in this document:** the earlier sample formula `completed_at - created_at` and the earlier statement that Q17/Q18 themselves were open are obsolete as of this approval.

## Approved Q23 — Recipient-scoped digests and delivery

- Schedule digests for employees (personal tasks only) and managers (tasks in currently managed departments only); ensure data minimization and ACL at **execution and send time**, not merely when scheduling.
- Store recipient IANA timezone and use it to derive next delivery instant; handle DST transitions deterministically with tests. Time and frequency are administrator-configurable and deliberately **unspecified** here.
- Implement queued delivery with an idempotency key per recipient/schedule occurrence and finite retries (e.g. configurable exponential backoff + bounded jitter); handle Telegram `retry_after`/flood limits, distinguish retryable vs non-retryable errors. On final failure, persist status and notify authorized operator; do not retry forever or disclose private data in alerts.
- Admin alone configures automations/digest schedules under existing policy; ordinary users and managers cannot edit global automation rules without separately authorized permissions. Keep an audit of schedule/config changes.
- Open parameters: exact frequency, time, max retries and delay values, unconfigured timezone default, notification recipient for terminal failures, user opt-out specifics. Do not silently assume values.
