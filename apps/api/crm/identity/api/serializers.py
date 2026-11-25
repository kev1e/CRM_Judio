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


class ErrorBodySerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField(allow_null=True)


class ErrorSerializer(serializers.Serializer[Any]):
    error = ErrorBodySerializer()
