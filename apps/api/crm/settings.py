"""Django settings.

Every deployment-specific value comes from the environment (see `.env.example`).
A missing required variable stops the process at start-up instead of running
with an unsafe default.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

# Local development convenience: read the repository-root `.env` if it exists.
# Real environment variables always win. Set CRM_ENV_FILE to another path, or to
# an empty string to disable file loading (containers and CI pass real variables).
_env_file = env.str("CRM_ENV_FILE", default=str(BASE_DIR.parent.parent / ".env"))
if _env_file and Path(_env_file).is_file():
    env.read_env(_env_file, overwrite=False)

# --- Core -------------------------------------------------------------------

SECRET_KEY: str = env.str("DJANGO_SECRET_KEY")
DEBUG: bool = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS")

_PLACEHOLDER_PREFIX = "change-me"
_MIN_SECRET_KEY_LENGTH = 50

if not DEBUG and (
    SECRET_KEY.startswith(_PLACEHOLDER_PREFIX) or len(SECRET_KEY) < _MIN_SECRET_KEY_LENGTH
):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be a random string of at least "
        f"{_MIN_SECRET_KEY_LENGTH} characters, not the placeholder from .env.example."
    )

# D032: django.contrib.auth, admin, sessions and contenttypes are deliberately not
# installed. Users, sessions, roles and grants are own tables, administration is
# done through the CRM's own screens, and there is no /admin route.
INSTALLED_APPS = [
    "rest_framework",
    "drf_spectacular",
    "crm.system",
    "crm.identity",
    "crm.access",
    "crm.audit",
    "crm.organization",
    "crm.tasks",
]

AUTH_USER_MODEL = "identity.User"

# Argon2id only; there are no legacy hashes to accept.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]

# Q13: at least 12 characters and not a common/known-compromised password. No
# character-class rules and no periodic rotation. The bundled list holds 20,000
# leaked passwords; PASSWORD_COMMON_LIST_PATH may point to a larger local file
# (one password per line, optionally gzipped). Passwords are never sent anywhere.
_common_password_options: dict[str, str] = {}
if _common_password_list := env.str("PASSWORD_COMMON_LIST_PATH", default=""):
    _common_password_options["password_list_path"] = _common_password_list

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
        "OPTIONS": _common_password_options,
    },
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "crm.common.middleware.OriginCheckMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "crm.urls"
WSGI_APPLICATION = "crm.wsgi.application"
APPEND_SLASH = False

# --- Database ---------------------------------------------------------------

DATABASES = {"default": env.db_url("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("DATABASE_URL must point to PostgreSQL (postgres://...).")
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = 3

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis / Celery ---------------------------------------------------------

REDIS_URL: str = env.str("REDIS_URL")

CELERY_BROKER_URL: str = env.str("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_TASK_DEFAULT_QUEUE = "crm"
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_IGNORE_RESULT = True
# Acknowledge after execution so a crashed worker does not lose the task. This is
# at-least-once delivery: every task must be idempotent.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = "UTC"
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# --- Telegram ---------------------------------------------------------------

# PROVISIONAL (docs/OPEN_QUESTIONS.md): Q11 asks for a "short-lived" binding token
# without fixing the number. Change it here or through the environment.
TELEGRAM_ENROLLMENT_TOKEN_TTL_MINUTES: int = env.int(
    "TELEGRAM_ENROLLMENT_TOKEN_TTL_MINUTES", default=30
)
if TELEGRAM_ENROLLMENT_TOKEN_TTL_MINUTES < 1:
    raise ImproperlyConfigured("TELEGRAM_ENROLLMENT_TOKEN_TTL_MINUTES must be at least 1.")

# Token of the CRM bot from BotFather. Empty means "no bot": the API still starts,
# but nobody can sign in, because a login needs approval in Telegram.
TELEGRAM_BOT_TOKEN: str = env.str("TELEGRAM_BOT_TOKEN", default="")
# Address of the Bot API. Change it only to a self-hosted Bot API server or a relay
# under the company's control: that host sees the bot token and every message.
TELEGRAM_API_BASE_URL: str = env.str(
    "TELEGRAM_API_BASE_URL", default="https://api.telegram.org"
).rstrip("/")
if not TELEGRAM_API_BASE_URL.startswith(("https://", "http://")):
    raise ImproperlyConfigured("TELEGRAM_API_BASE_URL must be an http(s) URL.")
# The transport used for outbound messages; tests replace it with a fake.
TELEGRAM_GATEWAY: str = env.str("TELEGRAM_GATEWAY", default="crm.telegram.gateway.AiogramGateway")

# --- Sessions and browser access --------------------------------------------

# Origins of the CRM web interface. A browser request that changes state must
# come from one of them (CSRF protection, see crm.common.middleware).
WEB_ORIGINS: list[str] = [
    origin.rstrip("/")
    for origin in env.list(
        "WEB_ORIGINS", default=["http://127.0.0.1:3000", "http://localhost:3000"]
    )
]
# The address employees open the CRM at; used in links the bot sends. Telegram
# does not treat `localhost` as a link, hence 127.0.0.1 for local runs.
WEB_PUBLIC_URL: str = env.str("WEB_PUBLIC_URL", default=WEB_ORIGINS[0]).rstrip("/")
if WEB_PUBLIC_URL not in WEB_ORIGINS:
    raise ImproperlyConfigured("WEB_PUBLIC_URL must be one of WEB_ORIGINS.")
# PROVISIONAL (docs/OPEN_QUESTIONS.md): how long a password-setup link is valid.
PASSWORD_SETUP_TOKEN_TTL_MINUTES: int = env.int("PASSWORD_SETUP_TOKEN_TTL_MINUTES", default=30)
if PASSWORD_SETUP_TOKEN_TTL_MINUTES < 1:
    raise ImproperlyConfigured("PASSWORD_SETUP_TOKEN_TTL_MINUTES must be at least 1.")

# Send the session cookie over HTTPS only. Browsers accept Secure cookies on
# http://localhost and http://127.0.0.1, so local development keeps the default.
SESSION_COOKIE_SECURE: bool = env.bool("SESSION_COOKIE_SECURE", default=True)
# How many reverse proxies in front of the API append to X-Forwarded-For
# (0: the header is ignored and the peer address is used). A wrong value lets a
# client forge its address, which weakens login throttling.
TRUSTED_PROXY_HOPS: int = env.int("TRUSTED_PROXY_HOPS", default=0)
if TRUSTED_PROXY_HOPS < 0:
    raise ImproperlyConfigured("TRUSTED_PROXY_HOPS must not be negative.")

# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- HTTP security ----------------------------------------------------------

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# --- API --------------------------------------------------------------------

REST_FRAMEWORK = {
    # Deny by default: a view is reachable without a session only when it says so.
    "DEFAULT_AUTHENTICATION_CLASSES": ["crm.identity.api.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "crm.common.errors.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "CRM API",
    "DESCRIPTION": "Internal corporate CRM — HTTP API.",
    "VERSION": "0.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "CheckResultEnum": "crm.system.api.serializers.CHECK_CHOICES",
    },
}

# Serving the schema over HTTP is off by default; the committed copy in
# packages/contracts is the contract.
API_SCHEMA_ENABLED: bool = env.bool("API_SCHEMA_ENABLED", default=False)

# --- Logging ----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": env.str("LOG_LEVEL", default="INFO")},
}

# --- Attachments (Q16, D039) --------------------------------------------------
# Production keeps attachment bytes in S3-compatible object storage ("s3").
# "local" is a directory for development and tests.
FILE_STORAGE: str = env.str("FILE_STORAGE", default="local")
FILE_STORAGE_LOCAL_ROOT: str = env.str(
    "FILE_STORAGE_LOCAL_ROOT", default=str(BASE_DIR / "var" / "files")
)
FILE_STORAGE_S3_ENDPOINT_URL: str = env.str("FILE_STORAGE_S3_ENDPOINT_URL", default="")
FILE_STORAGE_S3_REGION: str = env.str("FILE_STORAGE_S3_REGION", default="")
FILE_STORAGE_S3_BUCKET: str = env.str("FILE_STORAGE_S3_BUCKET", default="")
FILE_STORAGE_S3_ACCESS_KEY_ID: str = env.str("FILE_STORAGE_S3_ACCESS_KEY_ID", default="")
FILE_STORAGE_S3_SECRET_ACCESS_KEY: str = env.str("FILE_STORAGE_S3_SECRET_ACCESS_KEY", default="")
if FILE_STORAGE not in {"local", "s3"}:
    raise ImproperlyConfigured("FILE_STORAGE must be 'local' or 's3'.")
# Q16: 100 MB per file.
ATTACHMENT_MAX_BYTES: int = 100 * 1024 * 1024
# Uploads are written to a temporary file, never held in memory.
FILE_UPLOAD_HANDLERS = ["django.core.files.uploadhandler.TemporaryFileUploadHandler"]
# Where an upload waits while it is checked; the system temporary directory if empty.
FILE_UPLOAD_TEMP_DIR = env.str("FILE_UPLOAD_TEMP_DIR", default="") or None
