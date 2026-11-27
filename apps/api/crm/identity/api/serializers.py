from typing import Any

from rest_framework import serializers

LOGIN_STATES = ["pending", "denied", "expired", "invalid", "authenticated"]
DELIVERY_STATES = ["pending", "sent", "failed"]


class LoginRequestSerializer(serializers.Serializer[Any]):
    login = serializers.CharField(max_length=64, trim_whitespace=True)
    # Not trimmed: spaces may be part of a password. The length limit is enforced
    # by the domain service, with the same answer as a wrong password.
    password = serializers.CharField(max_length=1024, trim_whitespace=False, write_only=True)


class LoginStartedSerializer(serializers.Serializer[Any]):
    expires_at = serializers.DateTimeField()
    expires_in = serializers.IntegerField(
        min_value=0, help_text="Seconds until the attempt expires."
    )


class CurrentUserSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    crm_login = serializers.CharField()
    display_name = serializers.CharField()


class LoginProgressSerializer(serializers.Serializer[Any]):
    state = serializers.ChoiceField(choices=LOGIN_STATES)
    delivery = serializers.ChoiceField(choices=DELIVERY_STATES, allow_null=True)


class SessionInfoSerializer(serializers.Serializer[Any]):
    expires_at = serializers.DateTimeField()


class MeSerializer(serializers.Serializer[Any]):
    user = CurrentUserSerializer()
    session = SessionInfoSerializer()
    permissions = serializers.DictField(
        child=serializers.ChoiceField(choices=["own", "managed_departments", "company"]),
        help_text="Permission code -> widest scope currently granted.",
    )


class PasswordSetupRequestSerializer(serializers.Serializer[Any]):
    token = serializers.CharField(max_length=128, trim_whitespace=True)
    password = serializers.CharField(max_length=1024, trim_whitespace=False, write_only=True)


class UserDepartmentSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    is_primary = serializers.BooleanField()
    is_manager = serializers.BooleanField()


class UserSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    crm_login = serializers.CharField()
    display_name = serializers.CharField()
    responsibility = serializers.CharField(allow_blank=True)
    email = serializers.EmailField(allow_null=True)
    is_active = serializers.BooleanField()
    telegram_bound = serializers.BooleanField()
    has_password = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    departments = UserDepartmentSerializer(many=True)


class UserListSerializer(serializers.Serializer[Any]):
    results = UserSerializer(many=True)


class UserCreateRequestSerializer(serializers.Serializer[Any]):
    crm_login = serializers.CharField(max_length=64, trim_whitespace=True)
    display_name = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField(
        max_length=254, required=False, allow_null=True, allow_blank=True
    )
    department_id = serializers.UUIDField(required=False, allow_null=True)


class UserUpdateRequestSerializer(serializers.Serializer[Any]):
    responsibility = serializers.CharField(
        max_length=300, allow_blank=True, trim_whitespace=True, required=False
    )


class BindingCodeSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(help_text="One-time Telegram binding code. Shown once.")
    expires_at = serializers.DateTimeField()
    command = serializers.CharField(help_text="What the employee sends to the bot.")


class UserCreatedSerializer(serializers.Serializer[Any]):
    user = UserSerializer()
    binding = BindingCodeSerializer()


class ErrorBodySerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField(allow_null=True)


class ErrorSerializer(serializers.Serializer[Any]):
    error = ErrorBodySerializer()
