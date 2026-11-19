# Architecture — approved stack, proposed module boundaries

## Decisions

Stack revised on 2026-11-19 (D025, D026, D029, D030 in `DECISIONS.md`).

- One-company modular monolith (D026 APPROVED) in a polyglot monorepo.
- Frontend: Next.js + React + TypeScript, Tailwind CSS, shadcn/ui, dnd-kit for Kanban.
- Backend: Python, Django + Django REST Framework, Django ORM, PostgreSQL. OpenAPI schema generated from DRF (drf-spectacular).
- Jobs/notifications: Celery + Redis; dedicated worker process; a single Celery beat process for schedules.
- Telegram: aiogram bot (private/group request wizard, MFA confirmation, notifications) + Telegram Mini App.
- Deployment: Docker Compose on own VPS; GitHub Actions CI/CD; monitoring Grafana/Prometheus/Loki (proposed exact setup); file backend interface Local/S3.
- Tooling: pnpm (JS/TS dependencies), Turborepo (orchestration of build/lint/test across all apps, including the Python ones through thin `package.json` scripts), uv (Python dependencies, one workspace and one `uv.lock`).
- Testing: Vitest + React Testing Library for frontend unit/component tests; pytest + pytest-django for backend, business logic and permissions; Playwright for browser E2E. Vitest is never used for Python packages.
- **Version policy (D030):** latest stable release of every program and library, pinned exactly and committed in `pnpm-lock.yaml` and `uv.lock`. A release older than latest is allowed only for a proven incompatibility, recorded in the table below (D031, proposed).

## Verified versions (checked 2026-11-19; PROPOSED until the S0 plan is approved)

Sources: npm registry and PyPI metadata (`engines`, `peerDependencies`, `requires_python`, `requires_dist`, classifiers), Docker Hub tags, and a throwaway smoke project.

| Component | Version | Note |
|---|---|---|
| Node.js | 26.13.1 (LTS) | Accepted by Next, Vitest, ESLint, jsdom `engines` |
| pnpm / Turborepo | 12.21.0 / 2.11.13 | pnpm pinned through `packageManager` |
| TypeScript | **6.0.3** (latest is 7.0.2) | Exception: typescript-eslint 8.73.0 (and its canary) requires `typescript <6.1.0` |
| Next.js / React | 16.4.6 / 19.3.1 | |
| Tailwind CSS / shadcn CLI | 4.3.5 / 4.23.0 | |
| Vitest / Vite / jsdom | 5.1.1 / 8.3.8 / 31.0.1 | With `@vitejs/plugin-react` 6.3.0 |
| React Testing Library | 16.3.3 | `@testing-library/dom` 10.4.2, `jest-dom` 8.0.0, `user-event` 14.6.13 |
| Playwright | 1.65.1 | |
| ESLint | **9.39.5** (latest is 10.15.0) | Exception: `eslint-config-next` 16.4.6 pulls `eslint-plugin-react`, `-jsx-a11y`, `-import`, whose peer ranges stop at ESLint 9 |
| Prettier | 3.10.1 | |
| OpenAPI → TS types | `@hey-api/openapi-ts` 0.99.0 | `openapi-typescript` 7.13.0 requires TypeScript 5 |
| Python | 3.15.2 | |
| uv | 0.13.9 | |
| Django / DRF | 6.1.3 / 3.18.3 | Django 6.1 is not an LTS line; plan the move to the next LTS when it ships |
| drf-spectacular | 0.30.0 | |
| psycopg | 3.3.9 | |
| Celery / redis-py | 5.7.0 / 8.1.0 | |
| gunicorn | 27.0.1 | |
| pytest / pytest-django / pytest-cov | 9.2.0 / 4.14.0 / 7.1.0 | |
| Ruff / mypy | 0.17.6 / 2.4.1 | With django-stubs 6.1.2, djangorestframework-stubs 3.18.2, celery-types 0.26.0 |
| aiogram | 3.32.0 | Installed in S1; requires Python `<3.16` |
| argon2-cffi | 25.1.0 | Installed in S1 |
| PostgreSQL | 18.7 | |
| Redis | 8.10.3 | |

Compatibility evidence:

- `uv sync` of the Python set on CPython 3.15.2 resolves with no conflicts (`uv pip check` clean).
- Smoke project on Python 3.15.2 + PostgreSQL 18.7 + Redis 8.10.3: Django migrations applied, 3 pytest tests passed with `DeprecationWarning` as error, drf-spectacular schema validated, mypy strict clean, a Celery prefork worker executed a task that wrote through the ORM, gunicorn served the health endpoint.
- `pnpm install` of the frontend set resolves; the only peer conflict is ESLint 10 against the plugins bundled by `eslint-config-next`, hence ESLint 9.
- Not declared by upstream although it worked in the smoke run: Celery 5.7.0, kombu, billiard, redis-py, pytest-django and drf-spectacular list Python up to 3.14 in their classifiers; pytest-django and drf-spectacular list Django up to 6.0. Fallback if a defect appears: Python 3.14.10, where all of them declare support.
- Known incompatibility: `django-celery-beat` 2.9.0 requires `Django<6.1`. Not needed before S8.
- Freshly published packages: several of the versions above were released 0–3 days before the check. Proposal (D031): keep pnpm's release-age quarantine and uv's `exclude-newer` at 7 days and take the newest release older than that; the lockfiles record the result.

## Repository layout

```text
apps/
  web/            # Next.js web app (TypeScript)
  api/            # Django project + DRF API; all domain apps (modules) live here
  worker/         # Celery app entrypoint, worker/beat runtime config and worker tests; imports domain services from api
  telegram-bot/   # aiogram bot process — added in S1 (login approval), extended in S6
  telegram-mini/  # Optional dedicated Mini App front-end — S6
packages/
  contracts/      # OpenAPI schema exported from the API + generated TypeScript types; no hand-written business logic
  config/         # Shared tsconfig, ESLint and Prettier config
  ui/             # Shared accessible components & theme — added when a second front-end needs it
infra/
  docker/ ci/ monitoring/
docs/
pyproject.toml    # uv workspace root (members: apps/api, apps/worker), Ruff/mypy/pytest config
uv.lock
package.json  pnpm-workspace.yaml  pnpm-lock.yaml  turbo.json
```

S0 creates `apps/web`, `apps/api`, `apps/worker`, `packages/contracts`, `packages/config` only.

Rules:

- Each module from the list below is one Django app inside `apps/api` with `models`, `services` (domain logic and authorization), `selectors` (rights-scoped queries), `api` (serializers, views, urls) and `tests`.
- `apps/worker` and the bot hold no business rules; Celery tasks and bot handlers call the same domain services as the HTTP views.
- `apps/web` talks to the backend only through HTTP using the generated contract types. It never connects to PostgreSQL or Redis.
- The Django admin site is not exposed (D032, proposed): it would bypass record-level ACL and audit. Administration is built as CRM screens over the same services.
- CRM roles and scoped grants are own tables evaluated by the policy layer, not Django's model-level permissions.

## Key modules and their responsibilities

- **Identity/Session:** passwords, sessions, user lifecycle, Telegram binding, MFA challenges and recovery workflows.
- **Organization/RBAC:** departments, memberships, managed departments, roles/grants, scoped policy evaluator, immediate invalidation.
- **Projects/Invitations:** projects, membership, cross-department approval workflow.
- **Tasks:** canonical task/request entity, assignments, statuses, transitions, deadline edits, archive/trash, audit.
- **Templates:** draft/published template versions, field schemas, dynamic validation and values.
- **Comments/Files:** task comments, file metadata, storage provider adapter, download authorization.
- **Search/Views:** rights-scoped queries, saved personal/team views, consistent pagination.
- **Analytics:** SQL aggregations over rights-filtered data, typed metrics/filter definitions, Excel/CSV export.
- **Automations/Notifications:** rules, due dates, escalation, digests, worker idempotency, Telegram delivery.
- **Audit:** append-only mutation events containing actor, action, target, metadata and time.

## Domain boundaries

The browser, Bot wizard and Mini App must call **shared application services**; none may write database rows bypassing authorization or version validation. Worker invokes same domain services with explicit service-actor context. Queue message is not authorization proof. Data-access layer applies row scope to all read/export/aggregate operations.

## Suggested API surface (design, not implementation)

```text
POST   /auth/login                  # username + password -> pending challenge
POST   /auth/recovery/request       # admin-reviewed workflow, no email-only bypass
GET    /me
GET    /tasks?view=mine&...        # scope applied server-side
POST   /tasks                      # template version + fields + allowed assignee
GET    /tasks/:id                  # deny if unauthorized
PATCH  /tasks/:id                  # field-level permission controls
POST   /tasks/:id/transitions      # atomic status+archive if completed
POST   /tasks/:id/archive          # manager/superuser manual action
POST   /tasks/:id/trash            # pending authorization policy
POST   /tasks/:id/restore          # pending authorization policy
GET    /tasks/:id/comments
POST   /tasks/:id/comments
GET    /templates
POST   /templates/:id/publish      # immutable version
POST   /projects/:id/invitations
POST   /project-invitations/:id/approve
GET    /analytics/metrics
POST   /analytics/exports
POST   /integrations/telegram/webhook  # verify secret + source
```

OpenAPI contract generated from DRF serializers/views, serializer validation, consistent errors, idempotency key on create and webhook flows, pagination, revision (`version`) or optimistic locking for concurrent updates. No arbitrary SQL/JS expression execution from user-defined filters/templates.

## Business transitions

- Status transition handled atomically with audit and outbox event; when entering status classified `completed`, set `archived_at=now()` **within same transaction** (`transaction.atomic` with row locking). Completion policy must be defined for statuses and re-opening after archive.
- Checkpoint completion updates checkpoint progress only, NEVER triggers status change.
- Deactivation reassigns open tasks to primary-department manager or authorized superuser, under transactional/state-machine safety. Send outbox notifications.
- Deadline change by assignee: commit old/new in audit and enqueue manager notification. If task archived/deleted, mutation policy TBD.
- Revoked access: stop broadcasting sensitive task updates and invalidate cache entries immediately.

## Data/event delivery

Use transaction + outbox table for important state changes; Celery tasks are enqueued only after commit (outbox relay or `transaction.on_commit`), never inside an open transaction. Worker retries transient delivery failures, dedupes messages by event/outbox ID; user-facing operation succeeds even if Telegram notification delivery later fails, except actions that intrinsically require Telegram (login challenge, bot-created request). Do not sync Telegram group discussions.

## Non-functional implementation constraints

Time stored in UTC, rendered in user timezone; explicit currency codes; data validation both client/server. Files not publicly exposed; storage adapter must support secure streaming/presigned access after authorization. Structured logs redact credentials, bot tokens and sensitive form values.
