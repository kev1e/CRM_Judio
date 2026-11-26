from django.db import migrations


def forwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    administrator = Role.objects.get(key="administrator", is_system=True)
    RoleGrant.objects.get_or_create(
        role=administrator, permission_code="template.manage", defaults={"scope": "company"}
    )


def backwards(apps, schema_editor):
    apps.get_model("access", "RoleGrant").objects.filter(
        role__key="administrator", role__is_system=True, permission_code="template.manage"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0011_task_project")]

    operations = [migrations.RunPython(forwards, backwards)]
