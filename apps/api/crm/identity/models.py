from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from crm.common.ids import new_id

# Provisional technical format (OPEN_QUESTIONS.md): Q30 fixes only that the login is
# unique, owned by the CRM and independent of the Telegram username.
CRM_LOGIN_REGEX = r"^[a-z0-9][a-z0-9._-]{2,63}$"


class UserManager(BaseUserManager["User"]):
    pass


class User(AbstractBaseUser):
    """A CRM employee account (D032-A1).

    Identity is the immutable `id`; `crm_login` is the unique sign-in name (Q30).
    The Telegram link is the numeric `telegram_user_id`; `telegram_username` is a
    mutable display label and is never used to find or authenticate a user.
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    crm_login = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=150)
    # What the employee answers for, in the company's own words. Shown in the
    # company structure; it grants nothing and restricts nothing.
    responsibility = models.CharField(max_length=300, blank=True, default="")

    # Recovery contact (Q28). Verified only by an administrator action.
    email = models.EmailField(max_length=254, null=True, blank=True)  # noqa: DJ001 - NULL means "no email", required by the partial unique constraint
    email_verified_at = models.DateTimeField(null=True, blank=True)
    email_verified_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    telegram_user_id = models.BigIntegerField(null=True, blank=True, unique=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    telegram_bound_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    # Incremented whenever the user's roles or their grants change (D020): anything
    # issued for an older version (sessions, caches, subscriptions) is stale.
    permissions_version = models.PositiveBigIntegerField(default=1)

    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "crm_login"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        db_table = "identity_user"
        constraints = [
            models.CheckConstraint(
                condition=Q(crm_login__regex=CRM_LOGIN_REGEX),
                name="identity_user_login_format",
            ),
            models.UniqueConstraint(
                fields=["email"],
                condition=Q(email__isnull=False),
                name="identity_user_email_unique",
            ),
            models.CheckConstraint(
                condition=Q(email__isnull=True) | Q(email=models.functions.Lower("email")),
                name="identity_user_email_lowercase",
            ),
            # Verified state always names the administrator and needs an address.
            models.CheckConstraint(
                condition=(
                    Q(email_verified_at__isnull=True, email_verified_by__isnull=True)
                    | Q(
                        email_verified_at__isnull=False,
                        email_verified_by__isnull=False,
                        email__isnull=False,
                    )
                ),
                name="identity_user_email_verification_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    Q(telegram_user_id__isnull=True, telegram_bound_at__isnull=True)
                    | Q(telegram_user_id__isnull=False, telegram_bound_at__isnull=False)
                ),
                name="identity_user_telegram_binding_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_active=True, deactivated_at__isnull=True)
                    | Q(is_active=False, deactivated_at__isnull=False)
                ),
                name="identity_user_deactivation_consistent",
            ),
        ]

    def __str__(self) -> str:
        return self.crm_login


class TelegramEnrollmentToken(models.Model):
    """A one-time, expiring ticket that lets an employee bind their Telegram account (Q11).

    Only the SHA-256 of the token is stored; the token itself is shown once to
    whoever issued it. A user has at most one pending token: issuing a new one
    revokes the previous.
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="enrollment_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(db_default=Now())
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_telegram_enrollment_token"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(used_at__isnull=True, revoked_at__isnull=True),
                name="identity_enrollment_one_pending_per_user",
            ),
            models.CheckConstraint(
                condition=Q(used_at__isnull=True) | Q(revoked_at__isnull=True),
                name="identity_enrollment_used_xor_revoked",
            ),
            models.CheckConstraint(
                condition=Q(token_hash__regex=r"^[0-9a-f]{64}$"),  # noqa: S106 - a format, not a secret
                name="identity_enrollment_hash_format",
            ),
        ]

    def __str__(self) -> str:
        return f"enrollment:{self.pk}"


class PasswordSetupToken(models.Model):
    """A one-time, expiring ticket that lets an employee choose their own password
    (D036): sent by the bot to the Telegram account that has just been bound.

    Only the SHA-256 of the token is stored. A user has at most one pending token.
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="password_setup_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(db_default=Now())
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_password_setup_token"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(used_at__isnull=True, revoked_at__isnull=True),
                name="identity_password_setup_one_pending_per_user",
            ),
            models.CheckConstraint(
                condition=Q(used_at__isnull=True) | Q(revoked_at__isnull=True),
                name="identity_password_setup_used_xor_revoked",
            ),
            models.CheckConstraint(
                condition=Q(token_hash__regex=r"^[0-9a-f]{64}$"),  # noqa: S106 - a format, not a secret
                name="identity_password_setup_hash_format",
            ),
        ]

    def __str__(self) -> str:
        return f"password-setup:{self.pk}"


class LoginChallengeStatus(models.TextChoices):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    # Approved and exchanged for a session. Terminal: it can never be used again.
    CONSUMED = "consumed"
    # Replaced by a newer attempt or cancelled by a security action. Terminal.
    CANCELLED = "cancelled"


class ChallengeDelivery(models.TextChoices):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class LoginChallenge(models.Model):
    """One login attempt waiting for approval in Telegram (Q13).

    Created only after the password was verified. It is bound to the account, to
    the Telegram ID that was bound at that moment and to the browser that started
    the attempt (through a secret the browser keeps; only its SHA-256 is stored).
    It lives for 180 seconds; "expired" is a pending or approved challenge past
    `expires_at`, never a stored state.
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="login_challenges"
    )
    telegram_user_id = models.BigIntegerField()
    attempt_key_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=16, choices=LoginChallengeStatus.choices, default=LoginChallengeStatus.PENDING
    )
    delivery = models.CharField(
        max_length=16, choices=ChallengeDelivery.choices, default=ChallengeDelivery.PENDING
    )
    telegram_message_id = models.BigIntegerField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)

    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_login_challenge"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status=LoginChallengeStatus.PENDING.value),
                name="identity_challenge_one_pending_per_user",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in LoginChallengeStatus]),
                name="identity_challenge_status",
            ),
            models.CheckConstraint(
                condition=Q(delivery__in=[d.value for d in ChallengeDelivery]),
                name="identity_challenge_delivery",
            ),
            # Q13: never valid for more than 180 seconds.
            models.CheckConstraint(
                condition=Q(expires_at__gt=models.F("created_at"))
                & Q(expires_at__lte=models.F("created_at") + timedelta(seconds=180)),
                name="identity_challenge_ttl",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=LoginChallengeStatus.CONSUMED.value, consumed_at__isnull=False)
                    | (~Q(status=LoginChallengeStatus.CONSUMED.value) & Q(consumed_at__isnull=True))
                ),
                name="identity_challenge_consumed_consistent",
            ),
            models.CheckConstraint(
                condition=Q(attempt_key_hash__regex=r"^[0-9a-f]{64}$"),
                name="identity_challenge_hash_format",
            ),
        ]

    def __str__(self) -> str:
        return f"challenge:{self.pk}"


class Session(models.Model):
    """An authenticated web session (Q13).

    The browser holds a random token; only its SHA-256 is stored. A session lasts
    at most 12 hours from issuance and is never prolonged. It is checked against
    this table on every request, so revocation and deactivation apply at once.
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sessions"
    )
    # The approved challenge this session was issued for: one session per challenge.
    challenge = models.OneToOneField(
        LoginChallenge, on_delete=models.PROTECT, related_name="session"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    # Informational: the user's permission version at issuance. Rights are always
    # read live from the database, never from the session.
    permissions_version = models.PositiveBigIntegerField()

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)

    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = "identity_session"
        indexes = [models.Index(fields=["user", "revoked_at"], name="identity_session_user_idx")]
        constraints = [
            # Q13: absolute maximum of 12 hours.
            models.CheckConstraint(
                condition=Q(expires_at__gt=models.F("created_at"))
                & Q(expires_at__lte=models.F("created_at") + timedelta(hours=12)),
                name="identity_session_max_lifetime",
            ),
            models.CheckConstraint(
                condition=Q(token_hash__regex=r"^[0-9a-f]{64}$"),  # noqa: S106 - a format, not a secret
                name="identity_session_hash_format",
            ),
            models.CheckConstraint(
                condition=(
                    Q(revoked_at__isnull=True, revoked_reason="")
                    | (Q(revoked_at__isnull=False) & ~Q(revoked_reason=""))
                ),
                name="identity_session_revocation_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"session:{self.pk}"


class ThrottleKind(models.TextChoices):
    LOGIN_AND_SOURCE = "login_source"  # one login from one address
    LOGIN = "login"  # one login from anywhere
    SOURCE = "source"  # one address, any login
    MFA = "mfa"  # Telegram prompts sent for one account
    ENROLLMENT = "enrollment"  # binding codes tried by one Telegram account
    SETUP_LINK_USE = "setup_use"  # first-password links tried from one address
    SETUP_LINK_ISSUE = "setup_issue"  # first-password links requested for one account


class ThrottleCounter(models.Model):
    """Failed attempts for one subject, used for progressive delays (Q13).

    The subject (a login, an address, an account) is stored only as a keyed hash.
    There is no permanent lock: `blocked_until` is always a bounded moment, and the
    counter starts over after a quiet period.
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    kind = models.CharField(max_length=16, choices=ThrottleKind.choices)
    subject_digest = models.CharField(max_length=64)
    failures = models.PositiveIntegerField(default=0)
    last_failure_at = models.DateTimeField()
    blocked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_throttle_counter"
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "subject_digest"], name="identity_throttle_subject_unique"
            ),
            models.CheckConstraint(
                condition=Q(kind__in=[k.value for k in ThrottleKind]),
                name="identity_throttle_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"throttle:{self.kind}:{self.pk}"
