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
