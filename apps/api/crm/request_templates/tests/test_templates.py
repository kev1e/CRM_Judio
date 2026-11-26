"""Request templates, the administrator's side (D009, Q21, D040)."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, transaction

from crm.access import services as access
from crm.access.models import Role
from crm.access.permissions import ADMINISTRATOR_GRANTS, DEPARTMENT_MANAGER_GRANTS, Scope
from crm.audit.models import AuditEvent
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import STRONG_PASSWORD, Employee, EmployeeFactory
from crm.organization import services as org
from crm.request_templates import schema, services
from crm.request_templates.models import RequestTemplate, TemplateVersion
from crm.tasks.tests.test_tasks import World, uid, world  # noqa: F401
from crm.tasks.tests.test_tasks_api import call, sign_in

pytestmark = pytest.mark.django_db

FIELDS: list[dict[str, Any]] = [
    {"key": "client", "type": "text", "label": "Клиент", "required": True},
    {"key": "comment", "type": "text", "label": "Комментарий", "multiline": True},
    {"key": "amount", "type": "number", "label": "Сумма", "currency": "RUB", "min": 0},
    {"key": "due", "type": "date", "label": "Срок оплаты", "with_time": False},
    {"key": "kind", "type": "select", "label": "Вид", "options": ["Счёт", "Акт"]},
    {"key": "owner", "type": "employee", "label": "Ответственный"},
    {"key": "scan", "type": "file", "label": "Скан"},
    {"key": "urgent", "type": "boolean", "label": "Срочно"},
    {"key": "deal", "type": "reference", "label": "Сделка"},
]


def template(world: World, **draft: Any) -> RequestTemplate:  # noqa: F811
    created = services.create_template(actor=world.admin, name="Счёт клиенту")
    if draft:
        services.update_template(actor=world.admin, template_id=created.pk, **draft)
    return created


def code(error: pytest.ExceptionInfo[DomainError]) -> str:
    return error.value.code


# --- Who manages templates (Q21) --------------------------------------------


def test_permission_is_the_administrators_alone(world: World) -> None:  # noqa: F811
    assert ADMINISTRATOR_GRANTS["template.manage"] is Scope.COMPANY
    assert "template.manage" not in DEPARTMENT_MANAGER_GRANTS
    assert access.has_permission(world.admin, "template.manage", at_least=Scope.COMPANY)
    # Built-in roles only: it cannot be handed out through a custom role.
    role = access.create_role(actor=world.admin, key="editor", name="Редактор")
    with pytest.raises(DomainError):
        access.set_role_grants(
            actor=world.admin, role=role, grants={"template.manage": Scope.COMPANY}
        )


@pytest.mark.parametrize("who", ["olga", "anna", "zoya"])
def test_manager_employee_and_superuser_cannot_manage(world: World, who: str) -> None:  # noqa: F811
    existing = template(world, fields=FIELDS)
    actor = getattr(world, who)
    operations: list[Callable[[], object]] = [
        lambda: services.all_templates(actor=actor),
        lambda: services.create_template(actor=actor, name="Свой"),
        lambda: services.update_template(actor=actor, template_id=existing.pk, name="Х"),
        lambda: services.set_departments(
            actor=actor, template_id=existing.pk, department_ids=[world.sales.pk]
        ),
        lambda: services.set_active(actor=actor, template_id=existing.pk, active=False),
        lambda: services.publish(actor=actor, template_id=existing.pk),
    ]
    for operation in operations:
        with pytest.raises(PermissionDeniedError):
            operation()
    existing.refresh_from_db()
    assert existing.name == "Счёт клиенту"
    assert not TemplateVersion.objects.exists()
    assert AuditEvent.objects.filter(action__startswith="request_template.").count() == 2


# --- The draft --------------------------------------------------------------


def test_all_eight_field_types_are_stored_in_canonical_form(world: World) -> None:  # noqa: F811
    created = template(world, fields=FIELDS, checkpoints=["  Проверить   реквизиты ", "Отправить"])
    created.refresh_from_db()

    assert {field["type"] for field in created.draft_fields} == set(schema.FIELD_TYPES)
    by_key = {field["key"]: field for field in created.draft_fields}
    assert by_key["client"] == {
        "key": "client",
        "type": "text",
        "label": "Клиент",
        "required": True,
        "help": "",
        "multiline": False,
        "max_length": 500,
    }
    assert by_key["amount"]["currency"] == "RUB"
    assert by_key["amount"]["max"] is None
    assert by_key["kind"] == {
        "key": "kind",
        "type": "select",
        "label": "Вид",
        "required": False,
        "help": "",
        "multiple": False,
        "options": ["Счёт", "Акт"],
    }
    assert created.draft_checkpoints == ["Проверить реквизиты", "Отправить"]
    assert created.has_unpublished_changes


@pytest.mark.parametrize(
    "bad",
    [
        {"key": "x", "type": "video", "label": "Видео"},  # a ninth type
        {"key": "x", "type": "text", "label": ""},
        {"key": "X", "type": "text", "label": "Имя"},
        {"key": "1x", "type": "text", "label": "Имя"},
        {"key": "x", "type": "text", "label": "Имя", "required": "yes"},
        {"key": "x", "type": "text", "label": "Имя", "max_length": 10**6},
        {"key": "x", "type": "text", "label": "Имя", "options": ["a"]},  # not its setting
        {"key": "x", "type": "text", "label": "Имя", "on_submit": "run()"},  # unknown setting
        {"key": "x", "type": "number", "label": "Сумма", "min": 5, "max": 1},
        {"key": "x", "type": "number", "label": "Сумма", "currency": "рубли"},
        {"key": "x", "type": "number", "label": "Сумма", "min": "0"},
        {"key": "x", "type": "select", "label": "Вид", "options": []},
        {"key": "x", "type": "select", "label": "Вид", "options": ["А", "а"]},
        {"key": "x", "type": "select", "label": "Вид"},
        "not an object",
    ],
)
def test_invalid_field_definitions_are_refused(world: World, bad: Any) -> None:  # noqa: F811
    created = template(world)
    with pytest.raises(DomainError) as error:
        services.update_template(actor=world.admin, template_id=created.pk, fields=[bad])
    assert code(error) == "invalid_template"
    created.refresh_from_db()
    assert created.draft_fields == []


def test_duplicate_keys_and_oversized_forms_are_refused(world: World) -> None:  # noqa: F811
    created = template(world)
    field = {"key": "a", "type": "boolean", "label": "Да"}
    too_many = [{**field, "key": f"f{i}"} for i in range(schema.MAX_FIELDS + 1)]
    for fields in ([field, field], too_many, "text"):
        with pytest.raises(DomainError) as error:
            services.update_template(actor=world.admin, template_id=created.pk, fields=fields)
        assert code(error) == "invalid_template"
    with pytest.raises(DomainError):
        services.update_template(actor=world.admin, template_id=created.pk, checkpoints=["x"] * 31)


def test_names(world: World) -> None:  # noqa: F811
    created = template(world)
    with pytest.raises(DomainError) as error:
        services.create_template(actor=world.admin, name="счёт клиенту")
    assert code(error) == "template_name_taken"
    with pytest.raises(DomainError) as error:
        services.update_template(actor=world.admin, template_id=created.pk, name="  ")
    assert code(error) == "invalid_template_name"
    with pytest.raises(DomainError) as error:
        services.update_template(actor=world.admin, template_id=uuid4(), name="Нет")
    assert code(error) == "template_not_found"


# --- Publishing (D009) ------------------------------------------------------


def test_publish_makes_an_immutable_version_and_a_new_edit_makes_the_next(
    world: World,  # noqa: F811
) -> None:
    created = template(world, fields=FIELDS[:1], checkpoints=["Шаг"])

    first = services.publish(actor=world.admin, template_id=created.pk)

    assert (first.number, len(first.fields), first.checkpoints) == (1, 1, ["Шаг"])
    assert first.published_by == world.admin.user
    created.refresh_from_db()
    assert not created.has_unpublished_changes
    with pytest.raises(DomainError) as error:
        services.publish(actor=world.admin, template_id=created.pk)
    assert code(error) == "nothing_to_publish"

    services.update_template(actor=world.admin, template_id=created.pk, fields=FIELDS[:3])
    # Editing the draft does not touch what is published.
    assert len(TemplateVersion.objects.get(pk=first.pk).fields) == 1
    second = services.publish(actor=world.admin, template_id=created.pk)

    assert (second.number, len(second.fields)) == (2, 3)
    assert len(TemplateVersion.objects.get(pk=first.pk).fields) == 1
    assert services.latest_version(created) == second
    events = AuditEvent.objects.filter(action="request_template.published").order_by("occurred_at")
    assert [e.metadata["version"] for e in events] == [1, 2]


def test_saving_the_same_draft_is_not_a_change(world: World) -> None:  # noqa: F811
    created = template(world, fields=FIELDS[:1])
    services.publish(actor=world.admin, template_id=created.pk)
    services.update_template(actor=world.admin, template_id=created.pk, fields=FIELDS[:1])
    created.refresh_from_db()
    assert not created.has_unpublished_changes


def test_a_published_version_cannot_be_changed_or_deleted_even_in_the_database(
    world: World,  # noqa: F811
) -> None:
    created = template(world, fields=FIELDS[:1])
    version = services.publish(actor=world.admin, template_id=created.pk)

    version.fields = []
    with pytest.raises(TypeError):
        version.save()
    with pytest.raises(TypeError):
        version.delete()
    for statement in (
        "UPDATE request_templates_version SET fields = '[]' WHERE id = %s",
        "DELETE FROM request_templates_version WHERE id = %s",
    ):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(statement, [str(version.pk)])
    assert len(TemplateVersion.objects.get(pk=version.pk).fields) == 1


def test_retired_template_is_not_published_and_keeps_its_versions(world: World) -> None:  # noqa: F811
    created = template(world, fields=FIELDS[:1])
    services.publish(actor=world.admin, template_id=created.pk)
    services.update_template(actor=world.admin, template_id=created.pk, fields=FIELDS[:2])

    services.set_active(actor=world.admin, template_id=created.pk, active=False)

    with pytest.raises(DomainError) as error:
        services.publish(actor=world.admin, template_id=created.pk)
    assert code(error) == "template_retired"
    assert TemplateVersion.objects.filter(template=created).count() == 1
    assert AuditEvent.objects.filter(action="request_template.retired").count() == 1
    services.set_active(actor=world.admin, template_id=created.pk, active=True)
    assert services.publish(actor=world.admin, template_id=created.pk).number == 2


# --- Availability (Q21, D040) -----------------------------------------------


def test_template_is_available_to_nobody_until_departments_are_listed(world: World) -> None:  # noqa: F811
    created = template(world, fields=FIELDS[:1])
    services.publish(actor=world.admin, template_id=created.pk)
    assert list(services.usable_templates(world.olga)) == []

    services.set_departments(
        actor=world.admin, template_id=created.pk, department_ids=[world.sales.pk]
    )

    assert list(services.usable_templates(world.olga)) == [created]  # manages Sales
    assert list(services.usable_templates(world.pavel)) == []  # manages Support
    # D040: employees do not submit requests; neither do the administrator or
    # the read-only superuser.
    for actor in (world.anna, world.admin, world.zoya):
        assert list(services.usable_templates(actor)) == []
    event = AuditEvent.objects.get(action="request_template.departments_changed")
    assert event.metadata["added"] == [str(world.sales.pk)]


def test_unpublished_and_retired_templates_are_not_offered(world: World) -> None:  # noqa: F811
    created = template(world, fields=FIELDS[:1])
    services.set_departments(
        actor=world.admin, template_id=created.pk, department_ids=[world.sales.pk]
    )
    assert list(services.usable_templates(world.olga)) == []  # nothing published
    services.publish(actor=world.admin, template_id=created.pk)
    assert list(services.usable_templates(world.olga)) == [created]
    services.set_active(actor=world.admin, template_id=created.pk, active=False)
    assert list(services.usable_templates(world.olga)) == []


def test_availability_follows_the_current_state(world: World) -> None:  # noqa: F811
    created = template(world, fields=FIELDS[:1])
    services.publish(actor=world.admin, template_id=created.pk)
    services.set_departments(
        actor=world.admin,
        template_id=created.pk,
        department_ids=[world.sales.pk, world.support.pk],
    )
    assert list(services.usable_templates(world.pavel)) == [created]

    # The list is shortened; then Olga stops managing Sales.
    services.set_departments(
        actor=world.admin, template_id=created.pk, department_ids=[world.sales.pk]
    )
    assert list(services.usable_templates(world.pavel)) == []
    org.add_manager(
        actor=world.admin, department_id=world.sales.pk, user_id=uid(world.boris), designated=True
    )
    org.remove_manager(actor=world.admin, department_id=world.sales.pk, user_id=uid(world.olga))
    assert list(services.usable_templates(world.olga)) == []
    assert list(services.usable_templates(world.boris)) == [created]


def test_unknown_or_closed_department_cannot_be_listed(world: World) -> None:  # noqa: F811
    created = template(world)
    closed = org.create_department(actor=world.admin, name="Закрытый")
    org.set_department_active(actor=world.admin, department_id=closed.pk, active=False)
    for department_id in (uuid4(), closed.pk):
        with pytest.raises(DomainError) as error:
            services.set_departments(
                actor=world.admin, template_id=created.pk, department_ids=[department_id]
            )
        assert code(error) == "department_not_found"


def test_form_contents_stay_out_of_the_audit_log(world: World) -> None:  # noqa: F811
    template(world, fields=[{"key": "secret", "type": "text", "label": "Кодовое слово клиента"}])
    assert "Кодовое" not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))


# --- HTTP -------------------------------------------------------------------


def test_api_round_trip(world: World, make_employee: EmployeeFactory) -> None:  # noqa: F811
    boss = make_employee("boss")
    access.assign_role(
        actor=world.admin, user=boss.user, role=Role.objects.get(key="administrator")
    )
    assert world.olga.user is not None
    assert world.olga.user.telegram_user_id is not None
    admin = sign_in(boss)
    olga = sign_in(
        Employee(
            user=world.olga.user,
            password=STRONG_PASSWORD,
            telegram_user_id=world.olga.user.telegram_user_id,
        )
    )

    created = call(admin, "post", "/api/v1/request-templates", {"name": "Счёт клиенту"})
    assert created.status_code == 201
    template_id = created.json()["id"]
    base = f"/api/v1/request-templates/{template_id}"

    saved = call(
        admin,
        "patch",
        base,
        {
            "draft_fields": FIELDS,
            "draft_checkpoints": ["Проверить реквизиты"],
            "department_ids": [str(world.sales.pk)],
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert len(body["draft_fields"]) == 9
    assert body["departments"] == [{"id": str(world.sales.pk), "name": "Продажи"}]
    assert body["versions"] == []

    bad = call(
        admin, "patch", base, {"draft_fields": [{"key": "x", "type": "video", "label": "В"}]}
    )
    assert (bad.status_code, bad.json()["error"]["code"]) == (400, "invalid_template")

    published = call(admin, "post", f"{base}/publish")
    assert published.status_code == 200
    assert [v["number"] for v in published.json()["versions"]] == [1]
    assert published.json()["has_unpublished_changes"] is False
    assert call(admin, "post", f"{base}/publish").status_code == 400

    # Q21: a manager cannot read or change templates through the API.
    assert call(olga, "get", "/api/v1/request-templates").status_code == 403
    assert call(olga, "post", "/api/v1/request-templates", {"name": "Свой"}).status_code == 403
    assert call(olga, "patch", base, {"department_ids": []}).status_code == 403
    assert call(olga, "post", f"{base}/publish").status_code == 403

    assert (
        call(admin, "patch", f"/api/v1/request-templates/{uuid4()}", {"name": "Н"}).status_code
        == 404
    )
    listing = call(admin, "get", "/api/v1/request-templates")
    assert listing["Cache-Control"] == "no-store"
    assert [t["name"] for t in listing.json()["results"]] == ["Счёт клиенту"]
