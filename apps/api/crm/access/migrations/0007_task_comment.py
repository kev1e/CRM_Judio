from django.db import migrations


def forwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    manager = Role.objects.get(key="department_manager", is_system=True)
    RoleGrant.objects.get_or_create(
        role=manager, permission_code="task.comment", defaults={"scope": "managed_departments"}
    )


def backwards(apps, schema_editor):
    apps.get_model("access", "RoleGrant").objects.filter(
        role__key="department_manager", role__is_system=True, permission_code="task.comment"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0006_workflow_manage")]

    operations = [migrations.RunPython(forwards, backwards)]
