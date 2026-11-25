from typing import Any

from rest_framework import serializers


class PersonSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    crm_login = serializers.CharField()
    display_name = serializers.CharField()
    is_active = serializers.BooleanField()


class MemberSerializer(PersonSerializer):
    is_primary = serializers.BooleanField()


class ManagerSerializer(PersonSerializer):
    is_designated = serializers.BooleanField()


class DepartmentSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()
    members = MemberSerializer(many=True)
    managers = ManagerSerializer(many=True)


class DepartmentListSerializer(serializers.Serializer[Any]):
    results = DepartmentSerializer(many=True)


class DepartmentCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150, trim_whitespace=True)


class DepartmentUpdateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150, trim_whitespace=True, required=False)
    is_active = serializers.BooleanField(required=False)


class MemberAddSerializer(serializers.Serializer[Any]):
    user_id = serializers.UUIDField()
    is_primary = serializers.BooleanField(required=False, default=False)


class ManagerAddSerializer(serializers.Serializer[Any]):
    user_id = serializers.UUIDField()
    is_designated = serializers.BooleanField(required=False, default=False)
