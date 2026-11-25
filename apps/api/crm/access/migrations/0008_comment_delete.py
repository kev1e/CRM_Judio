from django.db import migrations


def forwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    manager = Role.objects.get(key="department_manager", is_system=True)
    RoleGrant.objects.get_or_create(
        role=manager,
        permission_code="task.comment.delete",
        defaults={"scope": "managed_departments"},
    )
    # D037: creating tasks is no longer available in the "own" scope.
    RoleGrant.objects.filter(permission_code="task.create", scope="own").delete()


def backwards(apps, schema_editor):
    apps.get_model("access", "RoleGrant").objects.filter(
        role__key="department_manager", role__is_system=True, permission_code="task.comment.delete"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0007_task_comment")]

    operations = [migrations.RunPython(forwards, backwards)]
