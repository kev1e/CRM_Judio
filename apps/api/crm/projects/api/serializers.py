from typing import Any

from rest_framework import serializers

from crm.tasks.api.serializers import NamedSerializer


class ProjectMemberSerializer(serializers.Serializer[Any]):
    user = NamedSerializer()
    department = NamedSerializer(help_text="The department the person takes part from.")
    is_active = serializers.BooleanField(help_text="False when the account is deactivated.")


class ProjectInvitationSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    project = NamedSerializer()
    project_department = NamedSerializer()
    user = NamedSerializer()
    department = NamedSerializer(help_text="The department whose manager decides.")
    requested_by = NamedSerializer()
    created_at = serializers.DateTimeField()


class ZoneMemberSerializer(serializers.Serializer[Any]):
    user = NamedSerializer()
    is_responsible = serializers.BooleanField()


class ProjectZoneSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    members = ZoneMemberSerializer(many=True)


class ZoneNameSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150, trim_whitespace=True)


class ZoneMemberSetSerializer(serializers.Serializer[Any]):
    user_id = serializers.UUIDField()
    is_responsible = serializers.BooleanField(required=False, default=False)


class ProjectSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    department = NamedSerializer()
    is_active = serializers.BooleanField()
    members = ProjectMemberSerializer(many=True)
    zones = ProjectZoneSerializer(
        many=True, help_text="Areas of responsibility inside the project and who is in each."
    )
    pending_invitations = ProjectInvitationSerializer(
        many=True, help_text="Shown only to somebody who runs the project."
    )
    can_manage = serializers.BooleanField(
        help_text="A hint for the interface. Every operation is checked again by the server."
    )


class ProjectListSerializer(serializers.Serializer[Any]):
    results = ProjectSerializer(many=True)
    invitations_to_decide = ProjectInvitationSerializer(many=True)
    can_create = serializers.BooleanField()


class ProjectCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150, trim_whitespace=True)
    department_id = serializers.UUIDField()


class ProjectUpdateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150, trim_whitespace=True, required=False)
    is_active = serializers.BooleanField(required=False)


class ParticipantAddSerializer(serializers.Serializer[Any]):
    user_id = serializers.UUIDField()
    department_id = serializers.UUIDField(
        help_text="One of the employee's departments: the one they take part from."
    )


class ParticipantAddedSerializer(serializers.Serializer[Any]):
    outcome = serializers.ChoiceField(choices=["added", "invited"])
    project = ProjectSerializer()


class DeclineSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(
        max_length=500, allow_blank=True, required=False, default="", trim_whitespace=True
    )


class CandidateSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    departments = NamedSerializer(many=True)


class CandidateListSerializer(serializers.Serializer[Any]):
    results = CandidateSerializer(many=True)
