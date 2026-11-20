from django.db import migrations

# Frozen copy of the administrator's grants at the time of this migration. Later
# permissions are added by later migrations; a test keeps the database and
# `crm.access.permissions.ADMINISTRATOR_GRANTS` in agreement.
ADMINISTRATOR_GRANTS = [
    "audit.read",
    "role.assign",
    "role.manage",
    "user.create",
    "user.deactivate",
    "user.email.verify",
    "user.recovery.manage",
    "user.update",
]


def create_role(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    role = Role.objects.create(
        key="administrator",
        name="Администратор",
        description=(
            "Настройка системы: пользователи, роли, восстановление доступа, журнал аудита. "
            "Не даёт доступа к содержимому задач."
        ),
        is_system=True,
    )
    RoleGrant.objects.bulk_create(
        RoleGrant(role=role, permission_code=code, scope="company") for code in ADMINISTRATOR_GRANTS
    )


def remove_role(apps, schema_editor):
    apps.get_model("access", "Role").objects.filter(key="administrator", is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0001_initial")]

    operations = [migrations.RunPython(create_role, remove_role)]
