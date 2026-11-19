"""Worker entrypoint: `celery -A crm_worker.app worker`.

Re-exports the Celery application configured in `crm.celery` so the worker, the
API and (later) the scheduler always share one task registry and one configuration.
"""

import logging

from celery.signals import worker_ready

from crm.celery import app

logger = logging.getLogger(__name__)

__all__ = ["app"]


@worker_ready.connect
def _log_worker_ready(**_: object) -> None:
    logger.info("CRM worker is ready and consuming tasks")
