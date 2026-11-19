# Infrastructure & reliability — initial implementation proposal

## Approved requirements

- Own VPS, Docker containers.
- Up to 20 employees initially.
- Environments: development, staging, production **logically isolated**, including credentials and DB; staging must not copy production personal data without anonymization.
- Automated CI/CD after successful tests; production release only through approved workflow.
- Monitoring dashboard plus Telegram incident alerts.
- Max 100MB per attachment, total files unknown; final storage provider undecided.
- Backup retention: 30 days. Frequency **not yet determined** pending business risk review.

## Proposed deployment topology

Public TLS reverse proxy (Caddy or Nginx) -> web/API/Telegram webhook (HTTPS). Private Docker network PostgreSQL/Redis; isolated worker.

Containers (stack revised 2026-11-19):

| Service | Runtime | From sprint |
|---|---|---|
| `web` | Next.js (Node.js) | S0 |
| `api` | Django + DRF under gunicorn; runs `migrate` as a separate one-off step, not on every start | S0 |
| `worker` | Celery worker, same image as `api` with a different command | S0 |
| `beat` | Celery beat, exactly one instance | S8 (when schedules appear) |
| `bot` | aiogram process (webhook mode behind the proxy; long polling allowed in local dev only) | S1 |
| `postgres`, `redis` | Official images, private network only, named volumes | S0 |

`api`, `worker`, `beat` and `bot` are built from one Python image so they always run the same code and migrations. A live-update transport (WebSocket/SSE, which would add an ASGI server) is not decided and not part of S0. SMTP provider if needed for verified recovery email. Optional local storage with dedicated mounted volume or external S3-compatible bucket through same storage abstraction. Secret values stored outside repo.

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

## Backups & DR (decision pending)

1. Ask business owners for RPO (max acceptable data loss) and RTO (max recovery time).
2. Select backup method based on RPO: daily logical dump may be enough for >=24h RPO; shorter RPO likely requires PITR/WAL and suitable base backups.
3. Off-host encrypted copies of PostgreSQL, all file objects, metadata and configuration needed for recovery. Secrets/keys handled separately.
4. Retain 30 days, consider immutable/versioned storage and least-privilege backup credentials.
5. Test restoration to isolated staging regularly and record actual RTO; inspect backup age/size/integrity; alert on failure.
6. Object storage versioning alone is NOT a reliable substitute for backups.

## File backend decision

- Unknown total volume -> define `StorageProvider` interface now: upload, stream/get, delete, signed-url if used, metadata, integrity checksum.
- Development can use local volume with backing copy; production decision after volume, upload frequency, disaster recovery and cost assessment. S3 is preferred when large media/remote backups/rapid migration are important.
- Limit 100 MB in reverse proxy, frontend, API and storage; use streaming uploads and server-side permissions, not buffered in-process file loads where avoidable.

## Monitoring & alerts

Metrics: API health/latency/5xx, process/VM memory/disk, DB connections/storage, queue lag/failures, Telegram webhook latency/errors, backup success/age, certificate expiry. Grafana/Prometheus/Loki is an **implementation proposal**. Provide dashboards and alerts; use Telegram alert channel **plus an independent fallback** because Telegram may be down when incident occurs. Never expose monitoring UI publicly without authentication.

## Operations runbooks

Document: local setup, staging deploy, production deploy, migrations, secrets rotation, incident response, Telegram token rotation, disk exhaustion, restore drill, release rollback and permission emergency revoke.
