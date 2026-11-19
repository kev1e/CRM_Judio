from typing import Any

from rest_framework import serializers

CHECK_CHOICES = ["ok", "fail"]


class HealthSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=["ok"])


class ReadinessChecksSerializer(serializers.Serializer[Any]):
    database = serializers.ChoiceField(choices=CHECK_CHOICES)
    redis = serializers.ChoiceField(choices=CHECK_CHOICES)


class ReadinessSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=["ok", "unavailable"])
    checks = ReadinessChecksSerializer()
