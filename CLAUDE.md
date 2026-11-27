# CLAUDE.md — обязательные инструкции разработчику

You are a principal full-stack engineer and software architect implementing an internal single-company CRM. User-facing interface defaults to Russian. Respect all approved decisions. Do not treat unapproved suggestions as binding product requirements.

## Before writing code

1. Read `README.md`, `docs/PRD.md`, `docs/DECISIONS.md`, `docs/OPEN_QUESTIONS.md`, and the relevant domain documents.
2. Summarize the affected features, risks, permissions, database migrations, test cases, and acceptance criteria.
3. Identify `BLOCKER` questions. Do not implement security-sensitive behavior by guessing; do unaffected work instead.
4. Produce a **small, reviewable implementation plan** for the current sprint, not the entire product.

## Non-negotiable product rules

- One company, initially <=20 employees; expandable design, not premature multi-tenancy.
- YouGile-inspired speed and clarity: minimal clicks/navigation, personal boards, modal task details, separate edit mode, responsive light/dark themes, Russian default with internationalization-ready architecture.
- Staff see tasks **only when they are assignees**. Department managers see tasks of departments they *manage*; superusers see tasks across the company. Admin rights are separate from global visibility.
- Every task has exactly one responsible department; users can belong to several departments and have several roles.
- Task/request is one entity with task type; task checklists are checkpoints, completion does **not** change task status.
- A completed task stays in its column for a month (30 days, configurable) and is then archived automatically; until it is reopened it is read-only (**D041, 2026-11-27, replaces the earlier "immediate automatic archival" of D016**). Manual archive/unarchive action is restricted to authorized manager/superuser where applicable. Archive and soft-delete trash are separate.
- Author, assignee, and department manager may edit task content **only when they already have permitted read access and appropriate edit permissions**. Changing assignee is reserved for manager/superuser in scope.
- Existing request instances keep the original published template version.
- Telegram: authorized company employees create requests via bot wizard or Mini App, from supported private/group contexts; no CRM chat viewer, no mirroring group conversations, no request-linked chat transcripts. Telegram bot is also used for notifications and login confirmation.
- Telegram username is a mutable login label, NOT an identity key. Bind user to immutable Telegram ID. Login: username+password+bot approval; verified email is recovery contact, reset/rebinding via administrator under controlled procedure.
- Preserve history/audit of tasks, users, permissions, templates, critical settings. Changes in permissions must revoke access for active sessions without requiring relogin.
- VPS + Docker, dev/staging/prod, CI/CD gated by tests, monitoring panel + Telegram alerts. Backup retention 30 days; frequency determined by RPO risk review, not arbitrary selection.

## Security architecture

- Deny by default, enforce authorization in backend service/repository queries, websocket events, downloads, search, exports, caches, analytics, job workers, Telegram endpoints.
- Project membership DOES NOT bypass record-level task visibility.
- Never rely on client-side filtering or hidden UI to restrict access.
- Avoid overprivileged default roles; admin configuration privilege != superuser task visibility.
- Use secure password hashing, authenticated/short-lived sessions, CSRF/origin checks where relevant, rate limits, signed/integrity-validated Telegram exchanges, webhook secret validation.
- Secrets only via environment/secret store; never commit tokens, logs containing passwords, or production data.

## Working agreement

- Use the approved stack (D025/D026, revised 2026-11-19): polyglot monorepo with `apps/web` (Next.js + React + TypeScript, Tailwind/shadcn), `apps/api` (Python, Django + Django REST Framework, Django ORM), `apps/worker` (Celery + Redis), PostgreSQL, aiogram + Telegram Mini App, Docker Compose, GitHub Actions. **Do not introduce NestJS, Prisma or BullMQ** — they were replaced.
- Tooling (D029): pnpm + Turborepo for JS/TS and task orchestration; uv for Python dependencies; Vitest + React Testing Library for frontend unit/component tests; pytest + pytest-django for backend, business logic and permissions; Playwright for browser E2E. Never use Vitest for Python packages.
- Versions (D030, D031, D033): latest stable releases, pinned exactly in `pnpm-lock.yaml` and `uv.lock`; approved exceptions are TypeScript 6.0.3, ESLint 9.39.5 and Python 3.14.10 as the primary interpreter (3.15.2 is a CI compatibility run only). New dependency releases wait 7 days (quarantine); a security exception must be documented next to the setting. Record every other deviation in `docs/ARCHITECTURE.md`. Verify compatibility before installing.
- D032 (approved): own user model; **no Django admin site** — never add `django.contrib.admin` or an `/admin` route, administration is CRM screens over the DRF API; own scoped RBAC (`OWN`, `MANAGED_DEPARTMENTS`, `COMPANY`). Do not add `django.contrib.auth`, `sessions` or `contenttypes` either: users, sessions, roles and grants are own tables. Every permission check goes through the single authorization service (`crm.access`), shared by REST, Celery and Telegram.
- Use Django migrations, DB constraints and tests for schema changes. No unreviewed destructive migrations or data loss.
- Write small cohesive Django apps (one per module) with typed serializers/DTOs, validation, domain services, idempotent Celery tasks and observability. Views, Celery tasks and the bot call domain services; they never bypass them with direct ORM writes.
- Keep docs synchronized with changes. Register any deviation as a proposal; await user confirmation if it changes behavior.
- Do not state work is complete unless code builds, tests run, and their outcomes are reported honestly.

## Definition of done for each issue

Code + migrations (if any) + unit/integration/e2e tests + permission-negative cases + error handling + documentation + runnable local setup + brief completion report. For security-sensitive features, include threat checks and audit events.

## Reporting format

- Implemented / files touched
- Migrations and operational impact
- Commands run; tests passed/failed/not run
- Security/permission implications
- Unresolved questions and next step

## Approved decisions 2026-11-19

Q01–Q09 and Q30 are APPROVED in `docs/DECISIONS.md`. Read this log before coding record lifecycle. Do not auto-purge Trash, treat cancelled as completed, grant creator implicit access, or silently reassign tasks/statuses. The bundle contains test specifications, not executable application tests.

## Approved decisions 2026-11-19 (Q10–Q12)
Cross-department project invitation must select participation department and validate approving manager or privileged superuser. Telegram first-time binding: admin/authorized manager provisioning + expiring one-time token + private bot verification of numeric ID. Telegram loss: administrator identity verification, revoke old link/challenges, re-enroll, audit; exact verification protocol is not approved. See `docs/DECISIONS.md` and `docs/OPEN_QUESTIONS.md`.
