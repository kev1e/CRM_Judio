"""Celery application.

Defined next to the Django settings so that both the API process (which enqueues
tasks) and the worker process (apps/worker) share one configuration.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crm.settings")

app = Celery("crm")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
