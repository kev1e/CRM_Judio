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
    # S0 exposes only unauthenticated health endpoints. Authentication and the
    # deny-by-default permission classes arrive with the identity module (S1).
    "DEFAULT_AUTHENTICATION_CLASSES": [],
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
