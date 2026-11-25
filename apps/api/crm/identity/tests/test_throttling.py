from datetime import timedelta

import pytest
from django.utils import timezone

from crm.identity import throttling
from crm.identity.models import ThrottleCounter, ThrottleKind
from crm.identity.throttling import POLICIES, Policy, Subject

pytestmark = pytest.mark.django_db

SUBJECT = Subject(ThrottleKind.LOGIN_AND_SOURCE, "anna|203.0.113.5")
POLICY = POLICIES[ThrottleKind.LOGIN_AND_SOURCE]


def test_delay_grows_and_is_capped() -> None:
    policy = Policy(free_failures=2, base_seconds=5, cap_seconds=60, quiet_seconds=600)

    delays = [policy.delay_after(n) for n in range(1, 9)]

    assert delays == [0, 0, 5, 10, 20, 40, 60, 60]
    assert policy.delay_after(10**9) == 60


def test_every_policy_has_a_bounded_delay() -> None:
    # Q13: no permanent lockout, whatever the number of failures.
    for policy in POLICIES.values():
        assert 0 < policy.delay_after(10**6) <= 15 * 60
        assert policy.quiet_seconds > 0


def test_free_failures_do_not_block() -> None:
    for _ in range(POLICY.free_failures):
        throttling.register_failure([SUBJECT])

    assert throttling.retry_after([SUBJECT]) == 0


def test_next_failure_blocks_and_the_wait_ends() -> None:
    now = timezone.now()
    for _ in range(POLICY.free_failures + 1):
        throttling.register_failure([SUBJECT], now=now)

    assert 0 < throttling.retry_after([SUBJECT], now=now) <= POLICY.base_seconds + 1
    later = now + timedelta(seconds=POLICY.base_seconds + 1)
    assert throttling.retry_after([SUBJECT], now=later) == 0


def test_counter_starts_over_after_a_quiet_period() -> None:
    now = timezone.now()
    for _ in range(POLICY.free_failures + 3):
        throttling.register_failure([SUBJECT], now=now)

    much_later = now + timedelta(seconds=POLICY.quiet_seconds + 1)
    throttling.register_failure([SUBJECT], now=much_later)

    counter = ThrottleCounter.objects.get()
    assert counter.failures == 1
    assert counter.blocked_until is None


def test_subjects_are_independent_and_the_longest_wait_wins() -> None:
    other = Subject(ThrottleKind.LOGIN_AND_SOURCE, "anna|198.51.100.9")
    now = timezone.now()
    for _ in range(POLICY.free_failures + 2):
        throttling.register_failure([SUBJECT], now=now)

    assert throttling.retry_after([other], now=now) == 0
    assert throttling.retry_after([other, SUBJECT], now=now) > 0


def test_reset_removes_the_delay() -> None:
    for _ in range(POLICY.free_failures + 2):
        throttling.register_failure([SUBJECT])

    throttling.reset([SUBJECT])

    assert throttling.retry_after([SUBJECT]) == 0
    assert not ThrottleCounter.objects.exists()


def test_the_subject_is_not_stored_in_clear() -> None:
    throttling.register_failure([SUBJECT])

    counter = ThrottleCounter.objects.get()
    assert "anna" not in counter.subject_digest
    assert len(counter.subject_digest) == 64
