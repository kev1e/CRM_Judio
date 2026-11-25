"""Progressive delays after repeated failures (Q13).

Every failure makes the next attempt wait longer, up to a cap; nothing is ever
locked permanently, and the counter starts over after a quiet period. Several
subjects are counted for one login attempt (the login from this address, the
login from anywhere, the address), so that changing only the source address does
not reset the delay, while a stranger hammering somebody's login from elsewhere
slows that account down far less than it slows the stranger.

The numbers are PROVISIONAL engineering values (docs/OPEN_QUESTIONS.md): Q13
fixes the behaviour, not the thresholds.
"""

import hashlib
import hmac
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.identity.models import ThrottleCounter, ThrottleKind


@dataclass(frozen=True, slots=True)
class Policy:
    free_failures: int  # failures that cause no delay
    base_seconds: int  # delay after the first counted failure; doubles each time
    cap_seconds: int  # the delay never exceeds this
    quiet_seconds: int  # the counter starts over after this long without failures

    def delay_after(self, failures: int) -> int:
        counted = failures - self.free_failures
        if counted <= 0:
            return 0
        # The exponent is bounded so a huge counter cannot overflow anything.
        return min(self.base_seconds << min(counted - 1, 20), self.cap_seconds)


@dataclass(frozen=True, slots=True)
class Subject:
    kind: ThrottleKind
    value: str


POLICIES: dict[ThrottleKind, Policy] = {
    ThrottleKind.LOGIN_AND_SOURCE: Policy(3, 5, 15 * 60, 30 * 60),
    ThrottleKind.LOGIN: Policy(10, 5, 5 * 60, 30 * 60),
    ThrottleKind.SOURCE: Policy(20, 5, 15 * 60, 30 * 60),
    ThrottleKind.MFA: Policy(3, 30, 15 * 60, 30 * 60),
    ThrottleKind.ENROLLMENT: Policy(5, 30, 15 * 60, 30 * 60),
}


def _digest(subject: Subject) -> str:
    message = f"{subject.kind.value}:{subject.value}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def retry_after(subjects: Iterable[Subject], *, now: datetime | None = None) -> int:
    """Seconds the caller still has to wait; 0 when an attempt is allowed."""
    now = now or timezone.now()
    wait = 0
    for subject in subjects:
        blocked_until = (
            ThrottleCounter.objects.filter(kind=subject.kind, subject_digest=_digest(subject))
            .values_list("blocked_until", flat=True)
            .first()
        )
        if blocked_until is not None and blocked_until > now:
            seconds = int((blocked_until - now).total_seconds()) + 1
            wait = max(wait, seconds)
    return wait


def _register(subject: Subject, now: datetime) -> None:
    policy = POLICIES[subject.kind]
    digest = _digest(subject)
    with transaction.atomic():
        counter = (
            ThrottleCounter.objects.select_for_update()
            .filter(kind=subject.kind, subject_digest=digest)
            .first()
        )
        if counter is None:
            counter = ThrottleCounter(
                kind=subject.kind, subject_digest=digest, failures=0, last_failure_at=now
            )
        elif now - counter.last_failure_at > timedelta(seconds=policy.quiet_seconds):
            counter.failures = 0
        counter.failures += 1
        counter.last_failure_at = now
        delay = policy.delay_after(counter.failures)
        counter.blocked_until = now + timedelta(seconds=delay) if delay else None
        counter.save()


def register_failure(subjects: Iterable[Subject], *, now: datetime | None = None) -> None:
    """Count one failure for every subject. Commits on its own, so the count is
    kept even though the operation that failed is refused."""
    now = now or timezone.now()
    for subject in subjects:
        try:
            _register(subject, now)
        except IntegrityError:
            # Another request created the counter at the same instant: count again.
            _register(subject, now)


def reset(subjects: Iterable[Subject]) -> None:
    for subject in subjects:
        ThrottleCounter.objects.filter(kind=subject.kind, subject_digest=_digest(subject)).delete()
