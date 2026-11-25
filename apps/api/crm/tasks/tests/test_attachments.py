"""Files on tasks (D006, Q16, Q19, Q24, Q29, D039): access follows the task,
content is checked, nothing leaks through the audit log or a direct address."""

import io
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from pytest_django.fixtures import Settings
from rest_framework.test import APIClient

from crm.access.models import Role
from crm.access.permissions import BASELINE_GRANTS, DEPARTMENT_MANAGER_GRANTS, Scope
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import Employee
from crm.files import storage
from crm.files.tests import samples
from crm.organization.models import Department
from crm.tasks import attachments, policy, services
from crm.tasks.models import Attachment
from crm.tasks.tests.test_tasks import World, make_task, reload, uid, world  # noqa: F401
from crm.tasks.tests.test_tasks_api import ORIGIN, call, new_task, sales, sign_in, team  # noqa: F401

pytestmark = pytest.mark.django_db

NAME = "Договор с клиентом.pdf"


def attach(actor: Actor, task_id: object, content: bytes = samples.PDF, name: str = NAME):  # type: ignore[no-untyped-def]
    return attachments.add_attachment(
        actor=actor,
        task_id=task_id,  # type: ignore[arg-type]
        stream=io.BytesIO(content),
        name=name,
    )


def stored_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def test_grants() -> None:
    assert BASELINE_GRANTS["task.attach"] is Scope.OWN
    assert "task.attachment.delete" not in BASELINE_GRANTS
    for code in ("task.attach", "task.attachment.delete"):
        assert DEPARTMENT_MANAGER_GRANTS[code] is Scope.MANAGED_DEPARTMENTS
        assert (
            Role.objects.get(key="department_manager")
            .grants.filter(permission_code=code, scope="managed_departments")
            .exists()
        )


# --- Attaching --------------------------------------------------------------


def test_assignee_and_manager_attach_files(world: World, file_storage: Path) -> None:  # noqa: F811
    task = make_task(world)

    first = attach(world.anna, task.pk)
    second = attach(world.olga, task.pk, samples.PNG, "scan.png")

    assert first.original_name == NAME
    assert first.content_type == "application/pdf"
    assert first.byte_size == len(samples.PDF)
    assert len(first.sha256) == 64
    assert first.uploader_id == uid(world.anna)
    assert first.storage == "local"
    # The key is the CRM's own; nothing of the user's name is in it.
    assert first.storage_key == f"attachments/{first.pk}"
    assert list(attachments.attachments(world.anna, task)) == [first, second]
    assert len(stored_files(file_storage)) == 2
    assert reload(task).row_version == 1


def test_file_name_and_content_never_reach_the_audit_log(world: World) -> None:  # noqa: F811
    task = make_task(world)
    attachment = attach(world.anna, task.pk)

    event = AuditEvent.objects.get(action="task.attachment_added")
    assert event.entity_id == str(task.pk)
    assert event.metadata == {
        "department_id": str(world.sales.pk),
        "attachment_id": str(attachment.pk),
        "byte_size": len(samples.PDF),
        "content_type": "application/pdf",
    }
    assert "Договор" not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))


@pytest.mark.parametrize("who", ["boris", "pavel", "vera", "admin"])
def test_outsiders_neither_attach_nor_download(
    world: World,  # noqa: F811
    file_storage: Path,
    who: str,
) -> None:
    task = make_task(world)
    attachment = attach(world.anna, task.pk)
    actor: Actor = getattr(world, who)

    with pytest.raises(DomainError) as error:
        attach(actor, task.pk)
    assert error.value.code == "task_not_found"
    with pytest.raises(DomainError) as error:
        attachments.open_attachment(actor=actor, task_id=task.pk, attachment_id=attachment.pk)
    assert error.value.code == "task_not_found"
    assert list(attachments.attachments(actor, task)) == []
    # Refused before anything was stored.
    assert len(stored_files(file_storage)) == 1


def test_superuser_downloads_and_does_not_attach(world: World, file_storage: Path) -> None:  # noqa: F811
    task = make_task(world)
    attachment = attach(world.anna, task.pk)

    record, chunks = attachments.open_attachment(
        actor=world.zoya, task_id=task.pk, attachment_id=attachment.pk
    )
    assert (record, b"".join(chunks)) == (attachment, samples.PDF)
    assert policy.actions(world.zoya, task)["task.attach"] is False
    with pytest.raises(PermissionDeniedError):
        attach(world.zoya, task.pk)
    assert len(stored_files(file_storage)) == 1


def test_refused_files_leave_nothing_behind(world: World, file_storage: Path) -> None:  # noqa: F811
    task = make_task(world)
    cases = [
        (b"MZ\x90\x00" + b"\x00" * 60, "invoice.pdf", "file_content_mismatch"),
        (samples.PDF, "run.exe", "file_type_not_allowed"),
        (samples.ZIP_BOMB, "bomb.zip", "file_archive_unsafe"),
        (b"", "empty.pdf", "file_empty"),
    ]
    for content, name, code in cases:
        with pytest.raises(DomainError) as error:
            attach(world.anna, task.pk, content, name)
        assert error.value.code == code
    assert not Attachment.objects.exists()
    assert stored_files(file_storage) == []
    assert not AuditEvent.objects.filter(action="task.attachment_added").exists()


def test_size_limit_is_exact(world: World, settings: Settings) -> None:  # noqa: F811
    task = make_task(world)
    settings.ATTACHMENT_MAX_BYTES = len(samples.PDF)
    attach(world.anna, task.pk)  # exactly the limit

    settings.ATTACHMENT_MAX_BYTES = len(samples.PDF) - 1
    with pytest.raises(DomainError) as error:
        attach(world.anna, task.pk)  # one byte over
    assert error.value.code == "file_too_large"
    assert Attachment.objects.count() == 1


def test_stored_object_is_removed_when_the_record_cannot_be_written(
    world: World,  # noqa: F811
    file_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = make_task(world)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(attachments, "_log", fail)
    with pytest.raises(RuntimeError):
        attach(world.anna, task.pk)

    assert not Attachment.objects.exists()
    assert stored_files(file_storage) == []


def test_storage_failure_is_a_clean_refusal(
    world: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = make_task(world)

    class Broken:
        name = "s3"

        def save(self, *args: object, **kwargs: object) -> None:
            raise storage.StorageError("save")

    monkeypatch.setattr(attachments, "get_storage", Broken)
    with pytest.raises(DomainError) as error:
        attach(world.anna, task.pk)
    assert error.value.code == "storage_unavailable"
    assert not Attachment.objects.exists()


def test_archived_and_deleted_tasks_keep_files_readable_only(world: World) -> None:  # noqa: F811
    task = make_task(world)
    attachment = attach(world.anna, task.pk)
    services.archive_task(actor=world.olga, task_id=task.pk)

    with pytest.raises(DomainError) as error:
        attach(world.anna, task.pk)
    assert error.value.code == "task_archived"
    with pytest.raises(DomainError) as error:
        attachments.delete_attachment(
            actor=world.olga, task_id=task.pk, attachment_id=attachment.pk
        )
    assert error.value.code == "task_archived"
    # Q24: the archive keeps files under the same access rules.
    _, chunks = attachments.open_attachment(
        actor=world.anna, task_id=task.pk, attachment_id=attachment.pk
    )
    assert b"".join(chunks) == samples.PDF
    with pytest.raises(DomainError):
        attachments.open_attachment(actor=world.boris, task_id=task.pk, attachment_id=attachment.pk)


def test_former_assignee_loses_the_files(world: World) -> None:  # noqa: F811
    task = make_task(world)
    attachment = attach(world.anna, task.pk)
    services.reassign(actor=world.olga, task_id=task.pk, assignee_id=uid(world.boris))

    with pytest.raises(DomainError) as error:
        attachments.open_attachment(actor=world.anna, task_id=task.pk, attachment_id=attachment.pk)
    assert error.value.code == "task_not_found"
    _, chunks = attachments.open_attachment(
        actor=world.boris, task_id=task.pk, attachment_id=attachment.pk
    )
    assert b"".join(chunks) == samples.PDF


def test_file_of_another_task_is_not_reachable_through_mine(world: World) -> None:  # noqa: F811
    # Anna sees `mine`; the file belongs to Boris's task.
    mine = make_task(world)
    other = make_task(world, assignee=world.boris)
    foreign = attach(world.boris, other.pk)

    for attachment_id in (foreign.pk, uuid4()):
        with pytest.raises(DomainError) as error:
            attachments.open_attachment(
                actor=world.anna, task_id=mine.pk, attachment_id=attachment_id
            )
        assert error.value.code == "attachment_not_found"


# --- Removing (provisional rule: the manager) -------------------------------


def test_manager_removes_a_file_and_it_disappears(world: World, file_storage: Path) -> None:  # noqa: F811
    task = make_task(world)
    attachment = attach(world.anna, task.pk)

    for actor in (world.anna, world.zoya):
        with pytest.raises(PermissionDeniedError):
            attachments.delete_attachment(actor=actor, task_id=task.pk, attachment_id=attachment.pk)
    attachments.delete_attachment(actor=world.olga, task_id=task.pk, attachment_id=attachment.pk)

    assert list(attachments.attachments(world.anna, task)) == []
    stored = Attachment.objects.get(pk=attachment.pk)
    assert stored.deleted_by_id == uid(world.olga)
    for operation in (
        lambda: attachments.open_attachment(
            actor=world.anna, task_id=task.pk, attachment_id=attachment.pk
        ),
        lambda: attachments.delete_attachment(
            actor=world.olga, task_id=task.pk, attachment_id=attachment.pk
        ),
    ):
        with pytest.raises(DomainError) as error:
            operation()
        assert error.value.code == "attachment_not_found"
    # Hidden, not purged (Q06: purge is a separate administrator decision).
    assert len(stored_files(file_storage)) == 1
    assert AuditEvent.objects.filter(action="task.attachment_deleted").count() == 1


# --- HTTP -------------------------------------------------------------------


def upload(client: APIClient, task_id: str, content: bytes = samples.PDF, name: str = NAME):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/tasks/{task_id}/attachments",
        {"file": SimpleUploadedFile(name, content)},
        format="multipart",
        headers={"Origin": ORIGIN},
    )


def test_api_upload_download_delete(
    team: dict[str, Employee],  # noqa: F811
    sales: Department,  # noqa: F811
) -> None:
    olga, anna, boris = (sign_in(team[name]) for name in ("olga", "anna", "boris"))
    task_id = new_task(olga, sales, team["anna"]).json()["id"]
    base = f"/api/v1/tasks/{task_id}"

    uploaded = upload(anna, task_id)
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["actions"]["attach"] is True
    assert body["actions"]["attachment_delete"] is False
    (item,) = body["attachments"]
    assert item["name"] == NAME
    assert item["byte_size"] == len(samples.PDF)
    assert item["content_type"] == "application/pdf"
    assert item["uploader"]["name"] == team["anna"].user.display_name
    assert "storage_key" not in item
    assert "sha256" not in item

    download = anna.get(f"{base}/attachments/{item['id']}")
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == samples.PDF  # type: ignore[attr-defined]
    assert download["Content-Type"] == "application/pdf"
    assert download["Content-Length"] == str(len(samples.PDF))
    disposition = download["Content-Disposition"]
    assert disposition.startswith("attachment; filename=\"file.pdf\"; filename*=UTF-8''")
    assert "%D0%94%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80" in disposition
    assert download["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in download["Content-Security-Policy"]
    assert download["Cache-Control"] == "no-store"

    # A colleague of the same department, and nobody at all.
    assert boris.get(f"{base}/attachments/{item['id']}").status_code == 404
    assert upload(boris, task_id).status_code == 404
    assert APIClient().get(f"{base}/attachments/{item['id']}").status_code == 401
    assert anna.get(f"{base}/attachments/{uuid4()}").status_code == 404

    assert call(anna, "delete", f"{base}/attachments/{item['id']}").status_code == 403
    deleted = call(olga, "delete", f"{base}/attachments/{item['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["attachments"] == []
    assert anna.get(f"{base}/attachments/{item['id']}").status_code == 404
    history = [entry["action"] for entry in call(anna, "get", base).json()["history"]]
    assert "task.attachment_added" in history
    assert "task.attachment_deleted" in history


def test_api_refuses_bad_uploads_with_stable_codes(
    team: dict[str, Employee],  # noqa: F811
    sales: Department,  # noqa: F811
    settings: Settings,
) -> None:
    olga, anna = sign_in(team["olga"]), sign_in(team["anna"])
    task_id = new_task(olga, sales, team["anna"]).json()["id"]

    def code(response: Any) -> tuple[int, str]:
        return response.status_code, response.json()["error"]["code"]

    assert code(upload(anna, task_id, b"<script>", "x.html")) == (400, "file_type_not_allowed")
    assert code(upload(anna, task_id, b"MZ" + b"\x00" * 40, "x.pdf")) == (
        400,
        "file_content_mismatch",
    )
    missing = anna.post(
        f"/api/v1/tasks/{task_id}/attachments", {}, format="multipart", headers={"Origin": ORIGIN}
    )
    assert code(missing) == (400, "file_missing")
    as_json = call(anna, "post", f"/api/v1/tasks/{task_id}/attachments", {"file": "x"})
    assert as_json.status_code == 415

    settings.ATTACHMENT_MAX_BYTES = 1024
    big = samples.PDF + b"\x00" * 2048
    assert code(upload(anna, task_id, big)) == (413, "file_too_large")
    # Far beyond the limit: refused from the declared length, before reading.
    huge = samples.PDF + b"\x00" * (3 * 1024 * 1024)
    assert code(upload(anna, task_id, huge)) == (413, "file_too_large")
    assert not Attachment.objects.exists()


def test_api_upload_without_origin_is_refused(
    team: dict[str, Employee],  # noqa: F811
    sales: Department,  # noqa: F811
) -> None:
    olga, anna = sign_in(team["olga"]), sign_in(team["anna"])
    task_id = new_task(olga, sales, team["anna"]).json()["id"]
    response = anna.post(
        f"/api/v1/tasks/{task_id}/attachments",
        {"file": SimpleUploadedFile(NAME, samples.PDF)},
        format="multipart",
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert not Attachment.objects.exists()
