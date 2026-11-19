#!/bin/sh
# Creates `.env` from `.env.example` with freshly generated local secrets.
# Does nothing if `.env` already exists.
set -eu

cd "$(dirname "$0")/.."

if [ -e .env ]; then
  echo ".env already exists — left untouched." >&2
  exit 0
fi

random_alnum() {
  # $1 = length
  LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1"
}

postgres_password=$(random_alnum 32)
django_secret_key=$(random_alnum 64)

umask 077
sed \
  -e "s/change-me-postgres-password/${postgres_password}/g" \
  -e "s/change-me-django-secret-key/${django_secret_key}/g" \
  .env.example > .env

echo "Created .env with generated local secrets."
