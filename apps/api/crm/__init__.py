"""CRM backend project package (Django modular monolith)."""

from crm.celery import app as celery_app

__all__ = ["celery_app"]
