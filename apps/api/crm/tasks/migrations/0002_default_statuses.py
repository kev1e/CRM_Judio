from django.db import migrations

# The starting board. Statuses and moves are configuration: the administrator
# changes them later; nothing in the code depends on these names.
STATUSES = [
    ("Нужно сделать", "new", 10),
    ("В работе", "active", 20),
    ("Готово", "completed", 30),
    ("Отменено", "cancelled", 40),
]
MOVES = [
    ("Нужно сделать", "В работе"),
    ("В работе", "Нужно сделать"),
    ("Нужно сделать", "Готово"),
    ("В работе", "Готово"),
    ("Нужно сделать", "Отменено"),
    ("В работе", "Отменено"),
    ("Отменено", "Нужно сделать"),
]


def forwards(apps, schema_editor):
    TaskStatus = apps.get_model("tasks", "TaskStatus")
    StatusTransition = apps.get_model("tasks", "StatusTransition")
    if TaskStatus.objects.exists():
        return
    by_name = {
        name: TaskStatus.objects.create(name=name, category=category, position=position)
        for name, category, position in STATUSES
    }
    StatusTransition.objects.bulk_create(
        StatusTransition(from_status=by_name[a], to_status=by_name[b]) for a, b in MOVES
    )


class Migration(migrations.Migration):
    dependencies = [("tasks", "0001_initial")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
