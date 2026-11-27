# Infrastructure & reliability — initial implementation proposal

## Approved requirements

- Own VPS, Docker containers.
- Up to 20 employees initially.
- Environments: development, staging, production **logically isolated**, including credentials and DB; staging must not copy production personal data without anonymization.
- Automated CI/CD after successful tests; production release only through approved workflow.
- Monitoring dashboard plus Telegram incident alerts.
- Maximum 100 MB per attachment. Local persistent VPS storage selected (Q16); total volume unknown. Allowed formats: PDF/Word/Excel documents, images and ZIP archives; no mandatory antivirus scanner in initial release.
- Backup retention: **30 days**. Business objectives **RPO ≤ 1 hour; RTO ≤ 4 hours** (Q15). Detailed schedule and tooling must demonstrate these targets by measured restore tests.

## Proposed deployment topology

Public TLS reverse proxy (Caddy or Nginx) -> web/API/Telegram webhook (HTTPS). Private Docker network PostgreSQL/Redis; isolated worker.

Containers (stack revised 2026-11-19):

| Service | Runtime | From sprint |
|---|---|---|
| `web` | Next.js (Node.js) | S0 |
| `migrate` | One-off job: `manage.py migrate`, exits; `api` and `worker` start only after it succeeds | S0 |
| `api` | Django + DRF under gunicorn | S0 |
| `worker` | Celery worker, same image as `api` with a different command | S0 |
| `beat` | Celery beat, exactly one instance | S8 (when schedules appear) |
| `bot` | aiogram process (webhook mode behind the proxy; long polling allowed in local dev only) | S1 |
| `postgres`, `redis` | Official images, private network only, named volumes | S0 |

`api`, `worker`, `beat` and `bot` are built from one Python image so they always run the same code and migrations. Local stack (S0): `compose.yaml`; PostgreSQL and Redis are not published to the host, `api` and `web` listen on `127.0.0.1` only, application containers run as non-root with all capabilities dropped (`api`/`worker` with a read-only root filesystem). `compose.dev.yaml` publishes PostgreSQL and Redis on localhost for host-based development.

A live-update transport (WebSocket/SSE, which would add an ASGI server) is not decided and not part of S0. SMTP provider if needed for verified recovery email. Optional local storage with dedicated mounted volume or external S3-compatible bucket through same storage abstraction. Secret values stored outside repo.

**Initial VPS sizing for load testing only**: 4 vCPU / 8GB RAM / 80GB SSD suggested as trial, NOT a guaranteed capacity figure. Measure memory under build/run, Redis queues, database connections and 100MB uploads before selecting production size.

## CI/CD gate proposal

- Push/PR, as separate jobs so each language fails independently:
  - **frontend:** `pnpm install --frozen-lockfile`, Prettier check, ESLint, `tsc`, Vitest + React Testing Library, Next.js build, generated contract types up to date.
  - **backend:** `uv sync --locked`, Ruff (lint + format check), mypy, `makemigrations --check`, migrations applied to an empty PostgreSQL service, pytest + pytest-django against PostgreSQL and Redis services (API and worker tests), OpenAPI schema validated and identical to the committed copy.
  - **e2e:** Docker Compose stack built and started, Playwright smoke tests against it.
  - **security:** secret scan, dependency audit for both lockfiles, Docker image builds.
- Staging: automatic deployment after test success + smoke/e2e tests with fixture accounts and ACL-negative cases.
- Production: automation on protected release/tag/approved branch with branch protections, environment checks and controlled migrations. No developer laptop deploy tokens.
- Rollback: roll back application image only if database schema compatible; use expand/contract migrations, maintenance plan for destructive changes, backup + restore for major incidents.
- Build images once and promote immutable digests from staging to production.

## Backups & disaster recovery (Q15 approved: RPO ≤1h / RTO ≤4h)

1. Design and test a recovery plan against approved objectives: RPO no more than 1 hour of lost data and RTO no more than 4 hours of unavailability.
2. Evaluate PostgreSQL base backups plus WAL archival/PITR; daily dumps alone do **not** satisfy the approved 1-hour RPO. Record actual WAL archiving, backup schedule, costs and recovery evidence.
3. Off-host encrypted copies of PostgreSQL, all file objects, metadata and configuration needed for recovery. Secrets/keys handled separately.
4. Retain 30 days, consider immutable/versioned storage and least-privilege backup credentials.
5. Test restoration to isolated staging regularly and record actual RTO; inspect backup age/size/integrity; alert on failure.
6. Object storage versioning alone is NOT a reliable substitute for backups.

## File backend decision

- Unknown total volume -> define `StorageProvider` interface now: upload, stream/get, delete, signed-url if used, metadata, integrity checksum.
- Production primary attachment storage is local on the VPS, in a persistent mounted volume. Keep an abstraction for future migration, but switching primary storage to S3 requires a new decision. Estimate capacity and monitor disk consumption before production.
- Limit 100 MB in reverse proxy, frontend, API and storage; use streaming uploads and server-side permissions, not buffered in-process file loads where avoidable.

## Monitoring & alerts

Metrics: API health/latency/5xx, process/VM memory/disk, DB connections/storage, queue lag/failures, Telegram webhook latency/errors, backup success/age, certificate expiry. Grafana/Prometheus/Loki is an **implementation proposal**. Provide dashboards and alerts; use Telegram alert channel **plus an independent fallback** because Telegram may be down when incident occurs. Never expose monitoring UI publicly without authentication.

## Operations runbooks

Document: local setup, staging deploy, production deploy, migrations, secrets rotation, incident response, Telegram token rotation, disk exhaustion, restore drill, release rollback and permission emergency revoke.


## Q16 — approved local attachment policy

- Approved groups only: documents (PDF/Word/Excel), images, ZIP archives. Specify exact extensions and MIME/content signatures before accepting files. Keep allowlist maintained and reject ambiguous/unapproved types; videos are not approved.
- Per-file size **100 MB maximum**, enforced at reverse proxy, API, backend streamed upload and storage. Prevent zip bombs, malicious filenames, path traversal, content sniffing and XSS on previews; force safe Content-Disposition for unknown/untrusted payloads.
- Files are private. Authorization is always performed against current task and record ACL before upload/download. Never expose filesystem paths or serve the volume directly to the public Internet.
- Antivirus scanning is **not mandatory** by approved decision; log residual risks, restrict active content, and add malware scanning later only through a new decision. Archive files must never be extracted automatically without limits.
- Back up local attachment volume **off-VPS** with encryption and integrity checks; design DB/file snapshot consistency and restore order. Off-VPS backup locations do not change the approved local **primary** storage choice.
- Capacity thresholds and quota choices remain OPEN because total volume is unknown. Recovery must include attachments within approved RPO/RTO and be measured in drills.

## Q25 — Approved infrastructure location, unresolved compliance
- The **initial production VPS and primary CRM storage must be in Russia**. Require verified physical location/provider evidence, not only a Russian IP address or `.ru` hostname.
- PostgreSQL, application service, private attachment volume and persistence for the production system must be in the approved Russian VPS environment. Employees can connect internationally through secured channels.
- Q15/Q16 are unchanged: RPO ≤1h, RTO ≤4h, 30-day encrypted *off-VPS* backups, local primary attachment storage, 100MB per-file cap; no obligatory antivirus. **Exact off-VPS backup country/provider is OPEN** pending compliance, durability and disaster recovery review. Do not place the only backups on the production VPS.
- Determine locations and processors for object storage if ever adopted, CI/CD logs, telemetry, crash reports, SMTP, Telegram, CDN, DNS, monitoring, support tooling. Avoid exporting personal data to unspecified third-party locations.
- Define access rules and operational guardrails for admins/employees connecting from multiple countries, including timezone configuration. Geography-based restrictions were not approved.
- Pre-launch gate: documented jurisdiction and cross-border data-flow assessment, data handling agreements where required, access control/crypto, provider evidence and tested recovery. `Q25-compliance` remains OPEN.

## Approved Q26 — production operating targets and gate
- Test design-load **up to 20 concurrently active users**, on a **Russia-hosted** production VPS; select size after concurrency/performance and 100 MB upload tests. Proposed 4 vCPU/8GB sizing earlier in this file is an unapproved trial estimate, not a requirement.
- **Target monthly availability 99.5%**. For a 30-day month this allows ~3 h 36 min total downtime if measured 24/7 with no exclusions. The 4-hour disaster RTO (Q15) alone does not ensure this target; monitoring, reliability design and incident preparedness must be validated.
- Production CI/CD gate: required automated tests and staging smoke checks green, immutable artifact/digest reviewed, then **explicit manual administrator approval** captured by GitHub protected environment or equivalent. Only after approval may an automated deployment runner act; record approver/time/version, backup/migration precautions, post-deploy health check and rollback path.
- Exact SLA measurement definition, monitoring alert thresholds, production capacity proof, maintenance/exclusions, approver identity and release evidence policy remain OPEN before production promises. Do not present 99.5% as a contractual provider SLA.
- Backup, data residency, international staff, file policy and legal readiness remain per approved Q15/Q16/Q25; do not alter them based on target uptime.

## Scheduler (2026-11-27)

`compose.yaml` has a `beat` service: `celery beat` over the same application as the worker. It only puts periodic jobs on the queue; the worker executes them. Jobs: `tasks.archive_completed`, hourly (D041). Run exactly one instance. Its schedule file is kept in memory (`/tmp`), so after a restart every job simply runs at its next interval; the jobs are idempotent.
