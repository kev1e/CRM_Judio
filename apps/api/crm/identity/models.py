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
