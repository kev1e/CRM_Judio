# Decision log — confirmed product decisions

Status: **APPROVED** unless marked `PROPOSED` / `OPEN`.

| ID | Decision | Status |
|---|---|---|
| D001 | Internal universal CRM for one company; UX inspired by YouGile, minimal buttons/transitions | APPROVED |
| D002 | Departments and roles are separate; admins create departments and configurable permission roles; user can have multiple roles and memberships | APPROVED |
| D003 | Employee only sees tasks as assignee; manager tasks of managed departments; superuser all company tasks; project membership does not bypass task ACL | APPROVED |
| D004 | Departments + projects; personal staff Kanban; home = My Tasks; task opens modal with collapsible extras and separate edit mode | APPROVED |
| D005 | Admin-managed statuses/columns and legal drag-drop; compact card fields title, priority, due, checkpoint progress, project/dept, assignee | APPROVED |
| D006 | Request is type of task, creator selects eligible specific assignee, immediate assignment; comments/files; checkpoint template and manual additions | APPROVED |
| D007 | Only manager/superuser may change assignee; creator, assignee, manager may edit content subject to read/access scope | APPROVED |
| D008 | One responsible department per task; multi-dept employees' task manager visibility determined by task responsible department | APPROVED |
| D009 | Admin creates versioned visual request templates with 8 field types; historical requests keep published version | APPROVED |
| D010 | Telegram bot + Mini App and bot wizard create requests for authorized employees; no CRM Telegram chat sync/viewer or chat attachment to task | APPROVED |
| D011 | Telegram username/password with bot approval; email recovery contact; Telegram user ID verified; loss of Telegram handled through administrator | APPROVED |
| D012 | In-app + Telegram notifications: assignments, due/overdue, comments/mentions, status, checkpoints, project invitations/approvals, scheduled digests | APPROVED |
| D013 | Employee own analytics, manager managed dept, superuser company; 5 KPIs; visual dashboard builder; Excel/CSV; extensible filters | APPROVED |
| D014 | Admin-only automation configuration; reminders, overdue escalation, reassign on deactivation, scheduled digests | APPROVED |
| D015 | All checkpoints completed do NOT change status automatically; supersedes earlier optional checkpoint-triggered status automation | APPROVED |
| D016 | Enter completed status -> **immediate automatic archive**; manager/superuser authorized manual archive action; distinct soft-delete Trash and restore | APPROVED |
| D017 | Assignee can change deadline; audit and notify manager | APPROVED |
| D018 | Admin and managers of own dept can create staff; own-dept project invites direct; other-dept requires approval by target-dept manager or privileged superuser | APPROVED |
| D019 | Deactivation reassigns open tasks to manager of employee's primary dept; if none active, authorized superuser fallback | APPROVED |
| D020 | Permissions changes effective immediately including existing sessions; audit significant changes tasks, grants, users, templates, settings | APPROVED |
| D021 | Search global+local; filters by status, priority, due, project/dept, assignee, type, author; personal and shared views | APPROVED |
| D022 | Default Russian + expandable internationalization; light and dark themes | APPROVED |
| D023 | Own VPS + Docker; initial <=20 users; dev/staging/prod; automated test-gated CI/CD; Telegram+dashboard monitoring | APPROVED |
| D024 | Max attachment 100 MB, total volume/storage provider undecided; backup retention 30 days and backup frequency selected after RPO/risk review | APPROVED |
| D025 | Accepted stack (**revised 2026-11-19**, see change log): frontend Next.js + React + TypeScript, Tailwind/shadcn; backend Python with Django + Django REST Framework; Django ORM; PostgreSQL; background workers Celery + Redis; Telegram via aiogram + Telegram Mini App; Docker Compose on VPS; GitHub Actions. NestJS, Prisma and BullMQ are no longer part of the stack | APPROVED |
| D026 | Modular monolith rather than microservices for first release, with the backend implemented on Django/DRF (**approved 2026-11-19**). Repository keeps `apps/web`, `apps/api`, `apps/worker` in S0 | APPROVED |
| D027 | Archive as `archived_at` on canonical task, not duplicate table; task statuses have completed category | PROPOSED |
| D028 | Object storage adapter Local/S3 provider to postpone storage provider decision | PROPOSED |
| D029 | Tooling: pnpm for JS/TS dependencies; Turborepo for monorepo orchestration of build and tests; uv for Python dependencies; Vitest + React Testing Library for frontend unit/component tests; pytest + pytest-django for Django backend, business logic and permissions; Playwright for browser E2E. Vitest is not used for Python packages. CI/CD runs the matching test suites automatically | APPROVED (2026-11-19) |
| D030 | Version policy: use the latest stable release of every program and library, pinned exactly in lockfiles. Supersedes the earlier "do not uncritically choose latest" wording | APPROVED (2026-11-19) |
| D031 | Exceptions to D030: **TypeScript 6.0.3** (latest is 7.0.x) and **ESLint 9.39.5** (latest is 10.x), used after their compatibility with every tool in the repository is verified; **7-day quarantine** for newly published dependencies, with documented exceptions for urgent security fixes. Evidence and the exception procedure in `ARCHITECTURE.md` | APPROVED WITH CONDITIONS (2026-11-19) |
| D032 | Django specifics: user model, Django admin site, authorization tables. Full wording, alternatives and recommendation in the section "D032" below. **Not approved; nothing in S0 depends on it** | PENDING |
| D033 | **Python 3.14.10** is the primary version for development, staging and production. **Python 3.15.2** is used only for an additional compatibility run in CI. A move to 3.15 may be proposed after the critical dependencies (Celery, kombu, billiard, redis-py, pytest-django, drf-spectacular) officially declare support | APPROVED (2026-11-19) |
| D034 | Source control: private GitHub repository `kev1e/CRM_Judio`; development is local and synchronised through Git. No secrets or real credentials in the repository | APPROVED (2026-11-19) |
| D035 | S0 plan approved: Django + DRF backend, pnpm, Turborepo, Vitest, Playwright, uv, pytest, pytest-django, Celery + Redis. Functional sprints do not start until S0 is finished and its baseline checks pass | APPROVED (2026-11-19) |

## D032 — Django specifics (PENDING, decision needed before S1)

S0 is neutral: it installs none of `django.contrib.auth`, `admin`, `sessions`, `contenttypes` and creates no tables for them, so every option below stays available. A test guards this until D032 is decided.

### D032-A. User model

| Option | What it means | Consequences |
|---|---|---|
| **A1 (recommended)** — own user model from the first identity migration (`AUTH_USER_MODEL`, built on `AbstractBaseUser`) | The CRM `users` table from `DATABASE.md` is the Django user: UUID key, CRM login label, immutable `telegram_user_id`, `permissions_version`, activity flags; no unused `first_name`/`is_staff`/`is_superuser` columns | Fits D011 (login label is mutable, identity is the Telegram ID) and D020 (permission version on the user). Slightly more code in S1. Django's own documentation recommends a custom model for new projects because replacing it after the first migration is very costly |
| A2 — Django's built-in `auth.User` plus a one-to-one profile table | Standard table with `username`, `is_staff`, `is_superuser`, groups; CRM fields live in a second table | Fastest start. `is_superuser` would collide in meaning with the CRM "superuser" role (company-wide read, D003) and silently bypass Django permission checks; every query needs a join; integer keys are guessable |
| A3 — start with A2, replace later | — | Not recommended: the swap requires rewriting migrations and foreign keys of every table that references users |

### D032-B. Django admin site (`/admin`)

| Option | What it means | Consequences |
|---|---|---|
| **B1 (recommended)** — not installed at all | Administration (departments, roles, statuses, templates, users) is built as CRM screens over the same domain services | One enforcement path: record-level ACL, audit and immediate revocation apply to every action. Costs UI work in S2/S3/S5, which the PRD requires anyway ("Admin ... through UI") |
| B2 — installed, restricted to a break-glass technical account, reachable only from a private network, every action audited | Emergency data repair without a deploy | The admin edits rows directly: it bypasses domain services, shows task bodies to whoever can log in (contradicts "admin rights != task visibility", D003) and writes no CRM audit events unless each model admin is hand-wrapped. Needs `auth`, `sessions`, `contenttypes`, `messages` tables |
| B3 — used as the main administrator interface | Least front-end work | Contradicts D003/D020 and the audit requirements; English-first generic UI does not meet `UX_GUIDELINES.md` |

### D032-C. Where roles and grants live

| Option | What it means | Consequences |
|---|---|---|
| **C1 (recommended)** — own tables (`roles`, `permissions`, `role_permissions` with scope, `user_roles`, `department_managers`) evaluated by one policy layer | As drawn in `DATABASE.md` and `PERMISSIONS.md` | Supports the three scopes `self` / `managed_departments` / `company` and the permission-version revocation directly |
| C2 — Django groups and model permissions, plus an object-permission library | Reuses built-in tables | Built-in permissions are per model ("can change task"), with no department scope; record-level rules would still be custom code, now split across two systems |
| C3 — hybrid: Django groups for coarse roles, own tables for scopes | — | Two sources of truth for one decision; harder to audit and to revoke atomically |

**Recommendation:** A1 + B1 + C1. If emergency data repair is a concern, it is covered by audited management commands calling the domain services rather than by B2.

## Reconciliation notes

- D016 resolves apparent conflict of #81 automatic archive and #82 “manager/superuser archives”: system auto-archive on completion, human-triggered archive/unarchive remains permissioned. If user intended no manual archive at all, update decision after confirmation.
- D015 supersedes originally selected potential automation “change status from checkpoints”; user later explicitly chose no status change after completing checkpoints.
- D003 + D007: an author may edit only if task remains visible under assignee/manager/superuser scope; creator status alone does not grant read rights. This exposes a user-experience decision in `OPEN_QUESTIONS.md`.
- #46 arbitrary department memberships + #60 primary-dept manager transfer implies defining a **primary department** as a separate property; currently unresolved.

## Change control

Document new approved decisions with date, old behavior, new behavior and affected tests. Claude Code must not silently override a row above.

## Change log

### 2026-11-19 — technology stack change (D025, D026, D029, D030)

Decided by the product owner before any implementation code existed.

| Area | Old | New |
|---|---|---|
| Backend framework | NestJS + TypeScript | Python, Django + Django REST Framework |
| ORM / migrations | Prisma | Django ORM / Django migrations |
| Background jobs | BullMQ + Redis | Celery + Redis (Celery beat for schedules) |
| Telegram | Bot API (library not chosen) | aiogram + Telegram Mini App |
| Monorepo | TypeScript-only monorepo | Polyglot monorepo: pnpm + Turborepo (JS/TS and orchestration), uv (Python) |
| Tests | Vitest/Jest (undecided) + Playwright | Vitest + React Testing Library (frontend), pytest + pytest-django (backend), Playwright (E2E) |
| Version policy | Stable, "do not uncritically choose latest" | Latest stable of everything (D030); approved exceptions in D031; Python per D033 |
| Architecture status | D026 modular monolith PROPOSED | D026 APPROVED |

Unchanged: frontend (Next.js + React + TypeScript), PostgreSQL, Redis, Docker Compose on VPS, GitHub Actions, the `apps/web` / `apps/api` / `apps/worker` layout, and **every functional requirement of CRM v1.3** (D001–D024).

Affected tests: none existed. `TEST_PLAN.md` now names the tools per layer; the required scenarios are unchanged.

### 2026-11-19 — S0 approvals (D031, D033, D034, D035; D032 pending)

- D031 moved from PROPOSED to APPROVED WITH CONDITIONS: TypeScript 6.0.3 and ESLint 9.39.5 only after a compatibility check with all tools; 7-day quarantine with documented security exceptions.
- D033: primary Python changed from the proposed 3.15.2 to 3.14.10; 3.15.2 kept as a CI compatibility run.
- D032 stays PENDING; S0 was implemented so that it does not prejudge it.

Affected documents: `CLAUDE.md`, `README.md`, `prompts/00-bootstrap.md`, `ARCHITECTURE.md`, `DATABASE.md`, `ROADMAP.md`, `INFRASTRUCTURE.md`, `ANALYTICS_AUTOMATIONS.md`, `TELEGRAM.md`, `TEST_PLAN.md`, `OPEN_QUESTIONS.md`.
