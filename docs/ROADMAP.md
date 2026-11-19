# Implementation roadmap — reviewed small increments

**Principle:** These are milestone/sprint groups, not commitments to dates or one gigantic Claude Code generation. Branches and PRs should be narrow and testable. `OPEN_QUESTIONS.md` blockers must be resolved before relevant code.

## S0 — repository + executable foundation

Deliver: polyglot monorepo (pnpm + Turborepo for JS/TS, uv for Python), pinned versions and lockfiles (`pnpm-lock.yaml`, `uv.lock`), Next.js baseline in `apps/web`, Django + DRF baseline in `apps/api`, Celery worker baseline in `apps/worker`, Docker Compose local dev, PostgreSQL + Django migrations baseline (technical table only), lint/typecheck/test for both languages (Vitest + React Testing Library, pytest + pytest-django, Playwright smoke), GitHub Actions CI, environment sample with placeholders, README setup. No real credentials. Review API/OpenAPI style and migrations.

**Exit:** `docker compose` starts; smoke endpoints and placeholder UI work locally, CI passes; no real CRM business logic assumed.

**Status (2026-11-19):** implemented on branch `s0-foundation`. Verified locally: lint, types, Vitest, pytest (Python 3.14.10 and 3.15.2), Next.js build, Docker Compose stack healthy, smoke script, Playwright. The GitHub Actions run must be confirmed green before S0 is closed. Known S0 limits, intentionally left to later sprints: no authentication, sessions or CSRF (S1, after D032); no TLS/HSTS and no reverse proxy (S8); no shadcn/ui components yet (S3); `manage.py check --deploy` therefore reports W003, W004, W008.

## S1 — identity, Telegram enrollment/MFA, users

Resolve Q11–Q13, Q28 and Q30. Introduce the custom Django user model as the first identity migration and the minimal aiogram bot process needed for binding and login approval (the request wizard and Mini App stay in S6). Implement verified Telegram binding, login username/password and per-attempt bot confirmation, account lock/rate limits, sessions, admin/manager-managed user creation within allowed scope, revocation, recovery admin workflow. Tests for username change, duplicate binds, replay, rejected challenge, Telegram outage.

**Exit:** real end-to-end authenticated login; Telegram-dependent login blocked when bot offline; safe existing sessions continue; access revokes on deactivation.

## S2 — organization & authorization core

Resolve Q01–Q03/Q08. Dept/role/permission tables, multi-membership, manager assignments and primary dept, ACL evaluator, scope enforcement hooks/query builder. Audit and negative cross-department tests.

**Exit:** employee, manager, superuser, admin privileges distinct and measurable via APIs; access revokes immediately.

## S3 — canonical tasks & personal boards

Resolve Q04–Q07/Q09/Q19. Tasks, assignee, single responsible dept, status/transition admin UI, checkpoints, due date, audit, archive/trash, modal details/edit mode, personal Kanban, drag-and-drop, responsive UX, light/dark and i18n structure.

**Exit:** employee cannot enumerate others' tasks; completion auto-archives; checkboxes do not change status; unauthorized transitions denied; history and archive/trash tested.

## S4 — projects, invitations, comments and files

Resolve Q10/Q16. Projects and membership, own-dept invites direct, other-dept approval, comments, private upload/download with <=100MB, file storage abstraction. Confirm production storage provider.

**Exit:** cross-dept invitation flow works without granting task read by mere project membership; file IDOR tests pass.

## S5 — request templates & web creation

Template builder UI, published immutable versions, all eight field types and validation, eligibility, dynamic fields, task creation with eligible assignee, checkpoint templates, history. Shared service for future Telegram forms.

**Exit:** edit/publish new template does not mutate old request; all field types validated; user cannot submit unsupported/custom values to bypass ACL.

## S6 — Telegram bot/Mini App and notifications

aiogram webhooks, Telegram wizard and Mini App both calling same task creation service, no chat sync, notification service, outbox/retries/idempotency, permissions checked at dispatch.

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
