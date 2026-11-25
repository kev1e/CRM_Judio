from django.db import migrations


def add_grant(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    role = Role.objects.get(key="administrator", is_system=True)
    RoleGrant.objects.get_or_create(
        role=role, permission_code="user.read", defaults={"scope": "company"}
    )


def remove_grant(apps, schema_editor):
    apps.get_model("access", "RoleGrant").objects.filter(
        role__key="administrator", role__is_system=True, permission_code="user.read"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0002_administrator_role")]

    operations = [migrations.RunPython(add_grant, remove_grant)]
