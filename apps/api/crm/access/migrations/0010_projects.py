from django.db import migrations

CODES = ["project.manage", "project.invitation.approve"]


def forwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    manager = Role.objects.get(key="department_manager", is_system=True)
    for code in CODES:
        RoleGrant.objects.get_or_create(
            role=manager, permission_code=code, defaults={"scope": "managed_departments"}
        )


def backwards(apps, schema_editor):
    apps.get_model("access", "RoleGrant").objects.filter(
        role__key="department_manager", role__is_system=True, permission_code__in=CODES
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0009_attachments")]

    operations = [migrations.RunPython(forwards, backwards)]
