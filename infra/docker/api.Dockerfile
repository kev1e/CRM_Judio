# One image for every Python process: API (gunicorn), worker (Celery) and migrations.
# Build context: repository root.
ARG PYTHON_VERSION=3.14.10

FROM python:${PYTHON_VERSION}-slim-trixie AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN pip install --no-cache-dir --disable-pip-version-check uv==0.13.7

WORKDIR /app

# Third-party dependencies first: this layer is rebuilt only when the lockfile changes.
COPY pyproject.toml uv.lock .python-version ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN uv sync --locked --no-dev --all-packages --no-install-workspace

COPY apps/api apps/api
COPY apps/worker apps/worker
RUN uv sync --locked --no-dev --all-packages --no-editable


FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    DJANGO_SETTINGS_MODULE=crm.settings \
    CRM_ENV_FILE=""

RUN groupadd --system --gid 10001 crm \
    && useradd --system --uid 10001 --gid crm --no-create-home --shell /usr/sbin/nologin crm

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY apps/api/manage.py /app/manage.py

USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "crm.wsgi:application", "--bind", "0.0.0.0:8000", "--worker-tmp-dir", "/dev/shm", "--access-logfile", "-"]
