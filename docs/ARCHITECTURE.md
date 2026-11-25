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
- **Version policy (D030, D031, D033):** latest stable release of every program and library, pinned exactly and committed in `pnpm-lock.yaml` and `uv.lock`. Approved exceptions: TypeScript 6.0.3, ESLint 9.39.5, Python 3.14.10 as the primary interpreter, and a 7-day quarantine for new releases.

## Pinned versions (installed and verified in S0, 2026-11-19)

| Component | Version | Note |
|---|---|---|
| Node.js | 26.13.1 (LTS) | `.node-version` |
| pnpm / Turborepo | 12.20.0 / 2.11.11 | Newest releases older than 7 days |
| TypeScript | **6.0.3** (latest is 7.0.2) | D031: typescript-eslint requires `typescript <6.1.0` |
| ESLint | **9.39.5** (latest is 10.x) | D031: `eslint-config-next` bundles plugins whose peer ranges stop at ESLint 9. See the warning below |
| typescript-eslint / eslint-config-next | 8.72.2 / 16.4.6 | |
| Next.js / React | 16.4.6 / 19.3.1 | |
| next-intl / next-themes | 4.15.1 / 0.4.6 | |
| Tailwind CSS | 4.3.5 | shadcn/ui components are added with the first real screens (S3) |
| Vitest / Vite / jsdom | 5.1.0 / 8.3.8 / 31.0.0 | |
| React Testing Library | 16.3.3 | `dom` 10.4.2, `jest-dom` 7.0.1, `user-event` 14.6.10 |
| Playwright | 1.65.0 | |
| Prettier | 3.10.1 | |
| OpenAPI → TS types | `@hey-api/openapi-ts` 0.99.0 | `openapi-typescript` requires TypeScript 5 |
| Python | **3.14.10** primary; 3.15.2 CI compatibility run | D033, `.python-version` |
| uv | 0.13.7 | |
| Django / DRF / drf-spectacular | 6.1.3 / 3.18.3 / 0.30.0 | Django 6.1 is not an LTS line; plan the move to the next LTS when it ships |
| psycopg | 3.3.9 (binary wheels) | |
| Celery / redis-py | 5.7.0 / 8.1.0 | `packaging` 26.3 is declared explicitly: kombu 5.7.0 imports it without declaring it |
| gunicorn | 27.0.0 | |
| django-environ | 0.14.0 | |
| pytest / pytest-django | 9.2.0 / 4.14.0 | |
| Ruff / mypy | 0.17.4 / 2.4.1 | With django-stubs 6.1.2, djangorestframework-stubs 3.18.2, celery-types 0.26.0 |
| PostgreSQL / Redis | 18.7 / 8.10.3 | Docker images |
| aiogram / argon2-cffi | 3.32.0 / 25.1.0 | aiogram left the 7-day quarantine on 2026-11-22 and is installed since S1.2b |

Compatibility evidence (D031 condition "after checking compatibility with all tools"):

- TypeScript 6.0.3: `tsc --noEmit` passes in `apps/web`, `packages/contracts` and `e2e`; Next.js 16.4.6 builds with it; Vitest, Playwright and `@hey-api/openapi-ts` run with it; pnpm reports no peer conflict with `strictPeerDependencies` on.
- ESLint 9.39.5: flat config with `typescript-eslint` 8.72.2, `eslint-config-next` 16.4.6 and `eslint-config-prettier` lints every TypeScript package with no peer conflict.
- **Warning about ESLint 9:** npm marks 9.39.5 as "no longer supported" (the 9.x line reached end of life; its last release is from July 2026). It is a development-only tool and never ships in an image, but it will not receive fixes. The supported alternative is ESLint 10 with a config assembled from `typescript-eslint`, `eslint-plugin-react-hooks` and `@next/eslint-plugin-next`, which loses `eslint-plugin-jsx-a11y`, `eslint-plugin-react` and `eslint-plugin-import` until they support ESLint 10. Revisit when those plugins or `eslint-config-next` move.
- Python: the full backend suite (API and worker) passes on 3.14.10 and on 3.15.2.
- Known incompatibility: `django-celery-beat` 2.9.0 requires `Django<6.1`. Not needed before S8.
- Known open advisory: `minimatch` <11.0.1 (moderate, GHSA-g3hv-75wg-m249) through `typescript-eslint`; development-only, no fixed version in the 10.x line that typescript-eslint accepts.

### Dependency quarantine (D031)

- pnpm: `minimumReleaseAge: 10080` (minutes) with `minimumReleaseAgeStrict: true` in `pnpm-workspace.yaml`.
- uv: `exclude-newer = "7 days"` in the root `pyproject.toml`.
- Exception for an urgent security fix: add the package to `minimumReleaseAgeExclude` (pnpm) or `exclude-newer-package` (uv) **with a comment naming the advisory and the date**, record it in the pull request, and remove the entry once the release is older than 7 days.
- Transitive security fixes go through `overrides` in `pnpm-workspace.yaml`, each with its advisory ID.
- The quarantine covers packages from npm and PyPI. Tool and image versions (Node.js, Python, PostgreSQL, Redis, pnpm, uv) are pinned by hand.

## Repository layout

```text
apps/
  web/            # Next.js web app (TypeScript)
  api/            # Django project + DRF API; all domain apps (modules) live here
  worker/         # Celery app entrypoint, worker/beat runtime config and worker tests; imports domain services from api
  telegram-bot/   # aiogram bot process (crm_bot): Telegram binding and login approval; extended in S6
  telegram-mini/  # Optional dedicated Mini App front-end — S6
packages/
  contracts/      # OpenAPI schema exported from the API + generated TypeScript types; no hand-written business logic
  config/         # Shared tsconfig, ESLint and Prettier config
  ui/             # Shared accessible components & theme — added when a second front-end needs it
e2e/              # Playwright tests against the running Docker Compose stack
infra/
  docker/         # Dockerfiles (CI lives in .github/workflows, monitoring arrives in S8)
scripts/          # init-env.sh, smoke.sh
docs/
pyproject.toml    # uv workspace root (members: apps/api, apps/worker), Ruff/mypy/pytest config
uv.lock
package.json  pnpm-workspace.yaml  pnpm-lock.yaml  turbo.json
```

S0 created `apps/web`, `apps/api`, `apps/worker`, `packages/contracts`, `packages/config` and `e2e`; S1 added `apps/telegram-bot`.

Rules:

- Each module from the list below is one Django app inside `apps/api` with `models`, `services` (domain logic and authorization), `selectors` (rights-scoped queries), `api` (serializers, views, urls) and `tests`.
- The Celery application object is defined in `apps/api/crm/celery.py`, next to the settings, because the API process enqueues tasks; `apps/worker` re-exports it and owns the worker runtime and its tests.
- `apps/worker` and the bot hold no business rules; Celery tasks and bot handlers call the same domain services as the HTTP views.
- `apps/web` talks to the backend only through HTTP using the generated contract types. It never connects to PostgreSQL or Redis.
- The browser talks only to the web origin. `/api/v1/*` there is a relay (`apps/web/src/lib/api-proxy.ts`) to the API on the internal network: it forwards cookies, `Origin` and the body, adds nothing and decides nothing. Server components ask the API who the request's cookies belong to on every render. When the HTTPS ingress arrives (S8) it may route `/api/` to the API directly.
- `crm.telegram` (inside `apps/api`, not a Django app) is the only code that sends to Telegram from synchronous code; `settings.TELEGRAM_GATEWAY` names the transport, and tests use a recording one. The bot process answers through aiogram itself.
- The API is deny-by-default: `SessionAuthentication` + `IsAuthenticated` are the DRF defaults; a view open to anonymous callers says so explicitly.
- D032 (approved): own user model, no Django admin site (`/admin` does not exist; administration is CRM screens over the DRF API), own scoped RBAC. None of `django.contrib.auth`, `admin`, `sessions`, `contenttypes` is installed.
- **Authorization** lives in `crm.access` and is the only place that answers "may this actor do this": REST views, Celery tasks and Telegram handlers all call it. Grants are read from PostgreSQL on every check, so a change of rights applies to already open sessions at once.
- **Audit** lives in `crm.audit`: append-only events written by the domain services in the same transaction as the change.
- Error responses use one envelope: `{"error": {"code", "message", "details"}}`; unhandled errors never expose internals.

## Key modules and their responsibilities

Implemented so far as Django apps in `apps/api/crm`: `system` (probes), `identity` (users, password policy, Telegram binding, sign-in, sessions, throttling, provisioning and deactivation, first password), `access` (roles, scoped grants, the authorization service incl. department scopes), `audit` (append-only events), `organization` (departments, memberships, managers). Shared building blocks are in `crm/common`: `Actor` (who performs an operation — a user, a system component or a CLI operator), `DomainError`/`PermissionDeniedError`, UUIDv7 identifiers and the error envelope.

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

## Approved task lifecycle service rules (Q05–Q09)

- Task status, automatic completion/archive and manual archival are separate domain operations with a shared auditable service layer.
- `archive_task` can archive incomplete tasks only when invoked by authorized manager/superuser; `reopen_completed_task` restores the prior valid non-completed status, with explicit remapping if obsolete.
- `soft_delete_task`/`restore_task` verify action and record scope; `purge_task` is a separate administrator-only safeguarded operation with no automatic Trash TTL.
- `deactivate_user` locks affected rows, finds one designated responsible manager for employee primary dept, else one designated authorized superuser, or stops with alert. Audit, session revocation, assignment changes and outbox must be consistent.
- `retire_status` requires explicit old-to-new mapping and historical event preservation; no automatic matching by name or nearest position.
- A valid CRM login is unique; Telegram numeric user ID is the provider identity; Django auth uses a custom user model from first migration.

## Approved Q26 — performance and release architecture
- The first deployment has a **measured design target of up to 20 simultaneous active users**. Exercise the Next.js UI, Django/DRF API, PostgreSQL, Celery/Redis workers, Telegram and local file IO under representative concurrent activity. Production VPS sizing remains a measured choice.
- Monthly availability target: **99.5%**, not an observed guarantee. Monitor external health checks, dependency failure modes and latency; one VPS is a potential single point of failure. Keep RPO ≤1h and RTO ≤4h requirements distinct from availability.
- Promote tested immutable artifacts through staging and a **protected manual approval gate owned by an authorized administrator**, then deploy with controlled migration, smoke tests and rollback plan; do not deploy to production automatically solely upon tests passing.

## Approved Q27 — scope boundaries
- V1 modules: organization/departments/RBAC, tasks/projects, requests/templates, reporting/analytics, and supporting auth/Telegram/audit/files/automation services already approved.
- Model any necessary external CRM entity association as a **minimal external reference/link**, with authorization and safe URL/identifier validation. Do not fabricate a universal external CRM data model or data synchronization flow.
- Contacts, companies, deals and products as first-class internal domain modules are explicitly **out of scope for the initial release**, not permanently rejected. Future designs must obtain separate approval and add migrations/contracts/tests.
