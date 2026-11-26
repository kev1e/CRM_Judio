"""Requests by a template (S5; D009, Q21, D040): who submits, what is accepted,
what the request keeps and who reads it."""

import io
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import Employee
from crm.files.tests import samples
from crm.identity import users
from crm.organization.models import Department
from crm.request_templates import services, submissions
from crm.request_templates.models import RequestTemplate, Submission
from crm.request_templates.values import FormValueError
from crm.tasks import attachments
from crm.tasks import services as tasks
from crm.tasks.models import Attachment, Task
from crm.tasks.tests.test_tasks import World, uid, world  # noqa: F401
from crm.tasks.tests.test_tasks_api import ORIGIN, sales, sign_in, team  # noqa: F401

pytestmark = pytest.mark.django_db

FIELDS: list[dict[str, Any]] = [
    {"key": "client", "type": "text", "label": "Клиент", "required": True, "max_length": 30},
    {"key": "comment", "type": "text", "label": "Комментарий", "multiline": True},
    {"key": "amount", "type": "number", "label": "Сумма", "currency": "RUB", "min": 0, "max": 1000},
    {"key": "count", "type": "number", "label": "Количество", "integer": True},
    {"key": "pay_by", "type": "date", "label": "Срок оплаты"},
    {"key": "call_at", "type": "date", "label": "Созвон", "with_time": True},
    {"key": "kind", "type": "select", "label": "Вид", "options": ["Счёт", "Акт"]},
    {
        "key": "tags",
        "type": "select",
        "label": "Метки",
        "options": ["Новый", "Важный", "VIP"],
        "multiple": True,
    },
    {"key": "owner", "type": "employee", "label": "Ответственный"},
    {"key": "scan", "type": "file", "label": "Скан"},
    {"key": "urgent", "type": "boolean", "label": "Срочно"},
    {"key": "deal", "type": "reference", "label": "Сделка"},
]
CHECKPOINTS = ["Проверить реквизиты", "Отправить клиенту"]


def published(
    world: World,  # noqa: F811
    fields: list[dict[str, Any]] | None = None,
    departments: list[Department] | None = None,
) -> RequestTemplate:
    template = services.create_template(actor=world.admin, name="Счёт клиенту")
    services.update_template(
        actor=world.admin,
        template_id=template.pk,
        fields=FIELDS if fields is None else fields,
        checkpoints=CHECKPOINTS,
    )
    services.set_departments(
        actor=world.admin,
        template_id=template.pk,
        department_ids=[d.pk for d in (departments or [world.sales])],
    )
    services.publish(actor=world.admin, template_id=template.pk)
    return template


def submit(world: World, template: RequestTemplate, **changes: Any) -> Task:  # noqa: F811
    arguments: dict[str, Any] = {
        "actor": world.olga,
        "template_id": template.pk,
        "version": 1,
        "department_id": world.sales.pk,
        "assignee_id": uid(world.anna),
        "title": "Счёт для «Ромашки»",
        "form_values": {"client": "ООО Ромашка"},
    }
    arguments.update(changes)
    return submissions.submit(**arguments)


def stored_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def refusal(error: pytest.ExceptionInfo[FormValueError]) -> tuple[str, str]:
    details = error.value.details or {}
    return details["field"], details["reason"]


# --- Submitting -------------------------------------------------------------


def test_manager_submits_a_request_with_all_field_types(
    world: World,  # noqa: F811
    file_storage: Path,
) -> None:
    template = published(world)

    task = submit(
        world,
        template,
        priority="high",
        form_values={
            "client": "  ООО   Ромашка ",
            "comment": "Первая строка\r\nвторая",
            "amount": "150,50",
            "count": 3,
            "pay_by": "2026-12-15",
            "call_at": "2026-12-01T12:30:00+03:00",
            "kind": "Акт",
            "tags": ["VIP", "Новый"],
            "owner": str(uid(world.boris)),
            "urgent": False,
            "deal": "CRM-1024",
        },
        files={"scan": (io.BytesIO(samples.PDF), "Скан.pdf")},
    )

    assert task.task_type == "request"
    assert task.title == "Счёт для «Ромашки»"
    assert task.priority == "high"
    assert task.author_id == uid(world.olga)
    assert task.assignee_id == uid(world.anna)
    assert task.responsible_department_id == world.sales.pk
    # The version's checkpoints, not done; the status is the starting one (D015).
    assert list(task.checkpoints.values_list("label", "is_done")) == [
        (label, False) for label in CHECKPOINTS
    ]
    assert task.status.category == "new"

    (attachment,) = Attachment.objects.filter(task=task)
    assert attachment.original_name == "Скан.pdf"
    assert len(stored_files(file_storage)) == 1
    submission = Submission.objects.get(task=task)
    assert submission.source == "web"
    assert submission.version.number == 1
    assert submission.values == {
        "client": "ООО Ромашка",
        "comment": "Первая строка\nвторая",
        "amount": "150.50",
        "count": "3",
        "pay_by": "2026-12-15",
        "call_at": "2026-12-01T09:30:00Z",
        "kind": "Акт",
        "tags": ["Новый", "VIP"],
        "owner": str(uid(world.boris)),
        "urgent": False,
        "deal": "CRM-1024",
        "scan": str(attachment.pk),
    }


def test_optional_fields_may_stay_empty(world: World) -> None:  # noqa: F811
    template = published(world)

    task = submit(world, template, form_values={"client": "Ромашка", "comment": " ", "tags": []})

    assert Submission.objects.get(task=task).values == {"client": "Ромашка"}
    assert not Attachment.objects.exists()


def test_nothing_typed_reaches_the_audit_log(world: World) -> None:  # noqa: F811
    template = published(world)

    task = submit(
        world,
        template,
        form_values={"client": "Секретный клиент", "deal": "CRM-777"},
        files={"scan": (io.BytesIO(samples.PDF), "Тайна.pdf")},
    )

    event = AuditEvent.objects.get(action="request.submitted")
    assert event.entity_id == str(task.pk)
    assert event.metadata == {
        "department_id": str(world.sales.pk),
        "template_id": str(template.pk),
        "version_id": str(services.latest_version(template).pk),  # type: ignore[union-attr]
        "version": 1,
        "source": "web",
        "filled_fields": 3,
        "files": 1,
    }
    everything = json.dumps(
        list(AuditEvent.objects.values_list("metadata", flat=True)), ensure_ascii=False
    )
    for secret in ("Секретный", "CRM-777", "Тайна", "Счёт для"):
        assert secret not in everything


# --- Who may submit (D040, Q21) ---------------------------------------------


@pytest.mark.parametrize("who", ["anna", "admin", "zoya", "pavel"])
def test_only_who_creates_tasks_for_the_department_submits(world: World, who: str) -> None:  # noqa: F811
    # An employee, the administrator, the superuser, a manager of another department.
    template = published(world)

    with pytest.raises(PermissionDeniedError):
        submit(world, template, actor=getattr(world, who))

    assert not Task.objects.exists()
    assert submissions.offers(getattr(world, who)) == [] or who == "pavel"


def test_template_must_be_available_in_the_department(world: World) -> None:  # noqa: F811
    template = published(world)  # Sales only

    with pytest.raises(DomainError) as error:
        submit(
            world,
            template,
            actor=world.pavel,
            department_id=world.support.pk,
            assignee_id=uid(world.vera),
        )

    assert error.value.code == "template_not_found"
    assert submissions.offers(world.pavel) == []
    assert not Task.objects.exists()


def test_offers_list_the_form_and_the_callers_departments(world: World) -> None:  # noqa: F811
    template = published(world, departments=[world.sales, world.support])
    services.create_template(actor=world.admin, name="Черновик")  # never published

    (for_olga,) = submissions.offers(world.olga)
    (for_vera,) = submissions.offers(world.vera)  # creates tasks company-wide (Q02)

    assert for_olga.template == template
    assert for_olga.version.number == 1
    assert for_olga.departments == [world.sales]
    assert for_vera.departments == [world.support, world.sales]
    for nobody in (world.anna, world.admin, world.zoya):
        assert submissions.offers(nobody) == []


def test_creator_outside_the_department_gets_no_access_to_the_request(world: World) -> None:  # noqa: F811
    template = published(world)

    task = submit(world, template, actor=world.vera)

    # Q02: creating gives no right to read — neither the task nor its form.
    with pytest.raises(DomainError) as error:
        submissions.submitted_form(world.vera, task.pk)
    assert error.value.code == "task_not_found"


@pytest.mark.parametrize("state", ["retired", "department_removed", "department_closed"])
def test_unavailable_template_takes_no_requests(world: World, state: str) -> None:  # noqa: F811
    template = published(world)
    if state == "retired":
        services.set_active(actor=world.admin, template_id=template.pk, active=False)
    elif state == "department_removed":
        services.set_departments(actor=world.admin, template_id=template.pk, department_ids=[])
    else:
        Department.objects.filter(pk=world.sales.pk).update(is_active=False)

    with pytest.raises(DomainError) as error:
        submit(world, template)

    # A closed department is nobody's to create tasks for.
    assert error.value.code == (
        "permission_denied" if state == "department_closed" else "template_not_found"
    )
    assert not Task.objects.exists()


def test_unpublished_template_and_unknown_one_are_alike(world: World) -> None:  # noqa: F811
    draft = services.create_template(actor=world.admin, name="Черновик")
    services.set_departments(
        actor=world.admin, template_id=draft.pk, department_ids=[world.sales.pk]
    )

    for template_id in (draft.pk, uuid4()):
        with pytest.raises(DomainError) as error:
            submit(world, draft, template_id=template_id)
        assert error.value.code == "template_not_found"


# --- Versions (D009) --------------------------------------------------------


def test_old_request_keeps_its_version_and_new_ones_use_the_latest(world: World) -> None:  # noqa: F811
    template = published(world)
    old = submit(world, template, form_values={"client": "Ромашка", "deal": "CRM-1"})
    services.update_template(
        actor=world.admin,
        template_id=template.pk,
        fields=[{"key": "buyer", "type": "text", "label": "Покупатель", "required": True}],
        checkpoints=[],
    )
    services.publish(actor=world.admin, template_id=template.pk)

    # Somebody who still has the old form open is told to reopen it.
    with pytest.raises(DomainError) as error:
        submit(world, template, version=1)
    assert error.value.code == "template_changed"

    new = submit(world, template, version=2, form_values={"buyer": "Лютик"})

    before = submissions.submitted_form(world.olga, old.pk)
    after = submissions.submitted_form(world.olga, new.pk)
    assert before is not None
    assert after is not None
    assert (before.version, after.version) == (1, 2)
    assert [a.question for a in before.answers if a.filled] == ["Клиент", "Сделка"]
    assert [(a.question, a.value) for a in after.answers] == [("Покупатель", "Лютик")]
    assert old.checkpoints.count() == 2
    assert new.checkpoints.count() == 0


# --- Values -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "field", "reason"),
    [
        ({}, "client", "required"),
        ({"client": "   "}, "client", "required"),
        ({"client": 5}, "client", "invalid"),
        ({"client": "я" * 31}, "client", "too_long"),
        ({"client": "A", "amount": "много"}, "amount", "invalid"),
        ({"client": "A", "amount": True}, "amount", "invalid"),
        ({"client": "A", "amount": "NaN"}, "amount", "invalid"),
        ({"client": "A", "amount": "-1"}, "amount", "out_of_range"),
        ({"client": "A", "amount": 1000.01}, "amount", "out_of_range"),
        ({"client": "A", "amount": "1.005"}, "amount", "too_precise"),
        ({"client": "A", "count": "2.5"}, "count", "not_integer"),
        ({"client": "A", "pay_by": "15.12.2026"}, "pay_by", "invalid"),
        ({"client": "A", "pay_by": "2026-02-30"}, "pay_by", "invalid"),
        ({"client": "A", "pay_by": "2026-12-15T10:00:00Z"}, "pay_by", "invalid"),
        ({"client": "A", "pay_by": "0900-01-01"}, "pay_by", "out_of_range"),
        ({"client": "A", "call_at": "2026-12-01T12:30:00"}, "call_at", "invalid"),
        ({"client": "A", "kind": "Накладная"}, "kind", "not_an_option"),
        ({"client": "A", "kind": ["Счёт"]}, "kind", "not_an_option"),
        ({"client": "A", "tags": "VIP"}, "tags", "not_an_option"),
        ({"client": "A", "tags": ["VIP", "VIP"]}, "tags", "not_an_option"),
        ({"client": "A", "tags": ["VIP", "Чужой"]}, "tags", "not_an_option"),
        ({"client": "A", "owner": "not-an-id"}, "owner", "not_an_option"),
        ({"client": "A", "owner": str(uuid4())}, "owner", "not_an_option"),
        ({"client": "A", "urgent": "да"}, "urgent", "invalid"),
        ({"client": "A", "deal": "x" * 201}, "deal", "too_long"),
        ({"client": "A", "scan": "attachments/123"}, "scan", "invalid"),
        ({"client": "A", "is_admin": True}, "is_admin", "unknown_field"),
    ],
)
def test_bad_values_are_refused_and_nothing_is_created(
    world: World,  # noqa: F811
    values: dict[str, Any],
    field: str,
    reason: str,
) -> None:
    template = published(world)

    with pytest.raises(FormValueError) as error:
        submit(world, template, form_values=values)

    assert refusal(error) == (field, reason)
    assert error.value.code == "invalid_form_value"
    assert not Task.objects.exists()
    assert not Submission.objects.exists()


def test_values_must_be_an_object(world: World) -> None:  # noqa: F811
    template = published(world)

    with pytest.raises(DomainError) as error:
        submit(world, template, form_values=["client"])

    assert error.value.code == "invalid_form"


def test_employee_field_names_only_people_of_the_department(world: World) -> None:  # noqa: F811
    template = published(world)
    # Olga manages Sales and may be named; Vera works elsewhere; a deactivated
    # colleague may not be named either.
    submit(world, template, form_values={"client": "A", "owner": str(uid(world.olga))})
    assert world.boris.user is not None
    users.deactivate_user(actor=world.admin, user=world.boris.user)

    for outsider in (world.vera, world.boris):
        with pytest.raises(FormValueError) as error:
            submit(world, template, form_values={"client": "A", "owner": str(uid(outsider))})
        assert refusal(error) == ("owner", "not_an_option")


def test_assignee_must_belong_to_the_department(world: World) -> None:  # noqa: F811
    template = published(world)

    with pytest.raises(DomainError) as error:
        submit(world, template, assignee_id=uid(world.vera))

    assert error.value.code == "assignee_not_eligible"
    assert not Submission.objects.exists()


# --- Files ------------------------------------------------------------------


def with_required_scan(world: World) -> RequestTemplate:  # noqa: F811
    return published(
        world,
        fields=[
            {"key": "scan", "type": "file", "label": "Скан", "required": True},
            {"key": "note", "type": "text", "label": "Заметка"},
        ],
    )


def test_required_file_must_arrive(world: World) -> None:  # noqa: F811
    template = with_required_scan(world)

    with pytest.raises(FormValueError) as error:
        submit(world, template, form_values={})

    assert refusal(error) == ("scan", "required")


def test_file_for_a_field_that_takes_none_is_refused(world: World, file_storage: Path) -> None:  # noqa: F811
    template = with_required_scan(world)
    scan = (io.BytesIO(samples.PDF), "a.pdf")

    for key in ("note", "other"):
        with pytest.raises(FormValueError) as error:
            submit(
                world,
                template,
                form_values={},
                files={"scan": scan, key: (io.BytesIO(samples.PDF), "b.pdf")},
            )
        assert refusal(error) == (key, "unknown_field")
    assert stored_files(file_storage) == []


def test_file_content_rules_apply(world: World, file_storage: Path) -> None:  # noqa: F811
    template = with_required_scan(world)

    with pytest.raises(DomainError) as error:
        submit(
            world,
            template,
            form_values={},
            files={"scan": (io.BytesIO(b"MZ\x90\x00 not a document"), "invoice.pdf")},
        )

    assert error.value.details == {"field": "scan"}
    assert not Task.objects.exists()
    assert stored_files(file_storage) == []


def test_failure_after_storing_leaves_no_file_behind(
    world: World,  # noqa: F811
    file_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = with_required_scan(world)

    def fail(**_: object) -> None:
        assert len(stored_files(file_storage)) == 1  # the file was already stored
        raise RuntimeError("database went away")

    monkeypatch.setattr(Submission.objects, "create", fail)

    with pytest.raises(RuntimeError):
        submit(world, template, form_values={}, files={"scan": (io.BytesIO(samples.PDF), "a.pdf")})

    assert stored_files(file_storage) == []
    assert not Task.objects.exists()
    assert not Attachment.objects.exists()


# --- Reading the form of a request ------------------------------------------


def test_form_is_read_by_who_reads_the_task(world: World) -> None:  # noqa: F811
    template = published(world)
    task = submit(
        world,
        template,
        form_values={
            "client": "Ромашка",
            "amount": 100,
            "call_at": "2026-12-01T09:30:00Z",
            "kind": "Счёт",
            "owner": str(uid(world.boris)),
            "urgent": True,
        },
        files={"scan": (io.BytesIO(samples.PDF), "Скан.pdf")},
    )
    attachment = Attachment.objects.get(task=task)

    for reader in (world.anna, world.olga, world.zoya):
        form = submissions.submitted_form(reader, task.pk)
        assert form is not None
        assert (form.template_name, form.version) == ("Счёт клиенту", 1)
        answers = {answer.key: answer for answer in form.answers}
        assert list(answers) == [field["key"] for field in FIELDS]
        assert answers["client"].value == "Ромашка"
        assert (answers["amount"].value, answers["amount"].currency) == ("100.00", "RUB")
        assert answers["call_at"].with_time is True
        assert answers["kind"].value == ["Счёт"]
        assert answers["owner"].value == world.boris.user.display_name  # type: ignore[union-attr]
        assert answers["urgent"].value is True
        assert (answers["scan"].value, answers["scan"].attachment_id) == ("Скан.pdf", attachment.pk)
        assert answers["comment"].filled is False
        assert answers["comment"].value is None

    # A colleague of the same department, another manager, the administrator.
    for stranger in (world.boris, world.pavel, world.admin):
        with pytest.raises(DomainError) as error:
            submissions.submitted_form(stranger, task.pk)
        assert error.value.code == "task_not_found"


def test_removed_file_is_shown_as_gone(world: World) -> None:  # noqa: F811
    template = with_required_scan(world)
    task = submit(
        world, template, form_values={}, files={"scan": (io.BytesIO(samples.PDF), "a.pdf")}
    )
    attachment = Attachment.objects.get(task=task)
    attachments.delete_attachment(actor=world.olga, task_id=task.pk, attachment_id=attachment.pk)

    form = submissions.submitted_form(world.anna, task.pk)

    assert form is not None
    scan = form.answers[0]
    assert (scan.filled, scan.value, scan.attachment_id) == (True, None, None)


def test_plain_task_has_no_form(world: World) -> None:  # noqa: F811
    task = tasks.create_task(
        actor=world.olga, title="Просто", department_id=world.sales.pk, assignee_id=uid(world.anna)
    )

    assert submissions.submitted_form(world.anna, task.pk) is None


# --- HTTP -------------------------------------------------------------------


def post_request(client: APIClient, payload: dict[str, Any], **files: SimpleUploadedFile):  # type: ignore[no-untyped-def]
    parts = {f"file.{key}": upload for key, upload in files.items()}
    return client.post(
        "/api/v1/requests",
        {"payload": json.dumps(payload), **parts},
        format="multipart",
        headers={"Origin": ORIGIN},
    )


@pytest.fixture
def invoice(admin_actor: Actor, sales: Department) -> RequestTemplate:  # noqa: F811
    template = services.create_template(actor=admin_actor, name="Счёт клиенту")
    services.update_template(
        actor=admin_actor, template_id=template.pk, fields=FIELDS, checkpoints=CHECKPOINTS
    )
    services.set_departments(actor=admin_actor, template_id=template.pk, department_ids=[sales.pk])
    services.publish(actor=admin_actor, template_id=template.pk)
    return template


def payload(template: RequestTemplate, department: Department, assignee: Employee, **values: Any):  # type: ignore[no-untyped-def]
    return {
        "template_id": str(template.pk),
        "version": 1,
        "department_id": str(department.pk),
        "assignee_id": str(assignee.user.pk),
        "title": "Счёт для «Ромашки»",
        "values": {"client": "Ромашка", **values},
    }


def test_api_needs_a_session(invoice: RequestTemplate) -> None:
    client = APIClient()

    assert client.get("/api/v1/request-forms").status_code == 401
    assert client.post("/api/v1/requests", {"payload": "{}"}, format="multipart").status_code == 401
    assert client.get(f"/api/v1/tasks/{uuid4()}/form").status_code == 401


def test_api_offer_submit_and_read(
    team: dict[str, Employee],  # noqa: F811
    sales: Department,  # noqa: F811
    invoice: RequestTemplate,
) -> None:
    olga, anna, boris = sign_in(team["olga"]), sign_in(team["anna"]), sign_in(team["boris"])

    forms = olga.get("/api/v1/request-forms")
    assert forms.status_code == 200
    assert forms["Cache-Control"] == "no-store"
    (form,) = forms.json()["results"]
    assert form["id"] == str(invoice.pk)
    assert form["version"] == 1
    assert form["departments"] == [{"id": str(sales.pk), "name": "Продажи"}]
    assert [field["key"] for field in form["form_fields"]] == [field["key"] for field in FIELDS]
    assert anna.get("/api/v1/request-forms").json() == {"results": []}

    created = post_request(
        olga,
        payload(invoice, sales, team["anna"], amount="99.90", urgent=True),
        scan=SimpleUploadedFile("Скан.pdf", samples.PDF),
    )
    assert created.status_code == 201, created.content
    body = created.json()
    task_id = body["id"]
    assert body["task"]["task_type"] == "request"
    assert [c["text"] for c in body["task"]["checkpoints"]] == CHECKPOINTS
    (attachment,) = body["task"]["attachments"]
    assert attachment["name"] == "Скан.pdf"

    read = anna.get(f"/api/v1/tasks/{task_id}/form")
    assert read.status_code == 200
    answers = {answer["key"]: answer for answer in read.json()["form"]["answers"]}
    assert answers["amount"] == {
        "key": "amount",
        "question": "Сумма",
        "type": "number",
        "filled": True,
        "value": "99.90",
        "currency": "RUB",
        "with_time": False,
        "attachment_id": None,
    }
    assert answers["scan"]["attachment_id"] == attachment["id"]
    assert boris.get(f"/api/v1/tasks/{task_id}/form").status_code == 404

    plain = olga.post(
        "/api/v1/tasks",
        {
            "title": "Просто",
            "department_id": str(sales.pk),
            "assignee_id": str(team["anna"].user.pk),
        },
        format="json",
        headers={"Origin": ORIGIN},
    ).json()["id"]
    assert anna.get(f"/api/v1/tasks/{plain}/form").json() == {"form": None}


def test_api_refusals(
    team: dict[str, Employee],  # noqa: F811
    sales: Department,  # noqa: F811
    invoice: RequestTemplate,
) -> None:
    olga, anna = sign_in(team["olga"]), sign_in(team["anna"])
    good = payload(invoice, sales, team["anna"])

    # An employee submits nothing (D040).
    assert post_request(anna, good).status_code == 403

    bad_value = post_request(olga, payload(invoice, sales, team["anna"], kind="Иное"))
    assert bad_value.status_code == 400
    assert bad_value.json()["error"] == {
        "code": "invalid_form_value",
        "message": "A value of the form was refused.",
        "details": {"field": "kind", "reason": "not_an_option"},
    }

    stale = post_request(olga, {**good, "version": 7})
    assert (stale.status_code, stale.json()["error"]["code"]) == (409, "template_changed")

    unknown = post_request(olga, {**good, "template_id": str(uuid4())})
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "template_not_found")

    for broken in ("not json", "[]"):
        response = olga.post(
            "/api/v1/requests",
            {"payload": broken},
            format="multipart",
            headers={"Origin": ORIGIN},
        )
        assert (response.status_code, response.json()["error"]["code"]) == (400, "invalid_form")

    stray = olga.post(
        "/api/v1/requests",
        {"payload": json.dumps(good), "avatar": SimpleUploadedFile("a.pdf", samples.PDF)},
        format="multipart",
        headers={"Origin": ORIGIN},
    )
    assert (stray.status_code, stray.json()["error"]["code"]) == (400, "invalid_form")

    wrong_file = post_request(olga, good, scan=SimpleUploadedFile("a.pdf", b"MZ\x90\x00 program"))
    assert wrong_file.status_code == 400
    assert wrong_file.json()["error"]["details"] == {"field": "scan"}

    missing_origin = olga.post(
        "/api/v1/requests", {"payload": json.dumps(good)}, format="multipart"
    )
    assert missing_origin.status_code == 403
    assert not Task.objects.exists()


def test_api_limits_the_size_of_a_request(
    team: dict[str, Employee],  # noqa: F811
    sales: Department,  # noqa: F811
    invoice: RequestTemplate,
    settings: Any,
    file_storage: Path,
) -> None:
    settings.ATTACHMENT_MAX_BYTES = 20
    olga = sign_in(team["olga"])

    response = post_request(
        olga,
        payload(invoice, sales, team["anna"]),
        scan=SimpleUploadedFile("Скан.pdf", samples.PDF),
    )

    assert (response.status_code, response.json()["error"]["code"]) == (413, "file_too_large")
    assert not Task.objects.exists()
    assert stored_files(file_storage) == []
