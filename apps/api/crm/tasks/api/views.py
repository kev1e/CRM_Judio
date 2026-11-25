from typing import Any, cast
from uuid import UUID

from django.db import transaction
from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity.api.serializers import ErrorSerializer
from crm.identity.models import User
from crm.tasks import attachments, policy, services
from crm.tasks.api.serializers import (
    VIEWS,
    CheckpointCreateSerializer,
    CheckpointUpdateSerializer,
    CommentWriteSerializer,
    OptionsSerializer,
    StatusListSerializer,
    TaskCreatedSerializer,
    TaskCreateSerializer,
    TaskDetailSerializer,
    TaskListSerializer,
    TaskUpdateSerializer,
    TransitionSerializer,
)
from crm.tasks.models import StatusTransition, Task

# Every view needs a session (the API default). What the signed-in user may see
# or do is decided by `crm.tasks.services` and `crm.tasks.policy`, never here.
# A task outside the caller's reach is answered as "not found" (404).

_ERRORS = {400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}
_MAX_CARDS = 500
_ACTION_KEYS = {
    "task.update": "edit",
    "task.status": "status",
    "task.deadline": "deadline",
    "task.checkpoints.use": "checkpoints_use",
    "task.checkpoints.manage": "checkpoints_manage",
    "task.attach": "attach",
    "task.attachment.delete": "attachment_delete",
    "task.comment": "comment",
    "task.comment.delete": "comment_delete",
    "task.priority": "priority",
    "task.reassign": "reassign",
    "task.archive": "archive",
    "task.delete": "delete",
}


def _actor(request: Request) -> Actor:
    return Actor.for_user(cast(User, request.user))


def _no_store(body: Any, code: int = status.HTTP_200_OK) -> Response:
    response = Response(body, status=code)
    response["Cache-Control"] = "no-store"
    return response


def _card(task: Task, done: int, total: int) -> dict[str, Any]:
    return {
        "id": task.pk,
        "title": task.title,
        "task_type": task.task_type,
        "priority": task.priority,
        "status_id": task.status_id,
        "due_at": task.due_at,
        "department": {
            "id": task.responsible_department_id,
            "name": task.responsible_department.name,
        },
        "assignee": {"id": task.assignee_id, "name": task.assignee.display_name},
        "checkpoints_done": done,
        "checkpoints_total": total,
        "is_completed": task.completed_at is not None,
        "is_archived": task.archived_at is not None,
        "is_deleted": task.deleted_at is not None,
        "version": task.row_version,
    }


def _detail(actor: Actor, task: Task) -> dict[str, Any]:
    checkpoints = list(task.checkpoints.all())
    events = (
        AuditEvent.objects.filter(entity_type="task", entity_id=str(task.pk))
        .select_related("actor")
        .order_by("-occurred_at", "-id")[:50]
    )
    allowed = policy.actions(actor, task)
    return {
        **_card(task, sum(c.is_done for c in checkpoints), len(checkpoints)),
        "description": task.description,
        "author": {"id": task.author_id, "name": task.author.display_name},
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "checkpoints": [{"id": c.pk, "text": c.label, "is_done": c.is_done} for c in checkpoints],
        "attachments": [
            {
                "id": a.pk,
                "name": a.original_name,
                "byte_size": a.byte_size,
                "content_type": a.content_type,
                "uploader": {"id": a.uploader_id, "name": a.uploader.display_name},
                "created_at": a.created_at,
            }
            for a in attachments.attachments(actor, task)
        ],
        "comments": [
            {
                "id": c.pk,
                "author": {"id": c.author_id, "name": c.author.display_name},
                "text": c.body,
                "created_at": c.created_at,
                "edited_at": c.edited_at,
                "is_own": actor.user is not None and c.author_id == actor.user.pk,
            }
            for c in services.comments(actor, task)
        ],
        # Only what happened and who did it; never the old or new text of a field.
        "history": [
            {
                "occurred_at": event.occurred_at,
                "action": event.action,
                "actor_name": event.actor.display_name if event.actor else "",
            }
            for event in events
        ],
        "actions": {_ACTION_KEYS[code]: ok for code, ok in allowed.items()},
    }


def _task_response(actor: Actor, task_id: UUID, code: int = status.HTTP_200_OK) -> Response:
    return _no_store(_detail(actor, services.get_task(actor, task_id)), code)


class StatusListView(APIView):
    @extend_schema(
        operation_id="task_statuses", responses={200: StatusListSerializer}, tags=["tasks"]
    )
    def get(self, request: Request) -> Response:
        moves: dict[UUID, list[UUID]] = {}
        for source, target in StatusTransition.objects.filter(
            to_status__is_active=True
        ).values_list("from_status_id", "to_status_id"):
            moves.setdefault(source, []).append(target)
        return _no_store(
            {
                "results": [
                    {
                        "id": item.pk,
                        "name": item.name,
                        "category": item.category,
                        "position": item.position,
                        "next_status_ids": moves.get(item.pk, []),
                    }
                    for item in services.statuses()
                ]
            }
        )


class TaskDepartmentsView(APIView):
    """Departments a new task may be addressed to."""

    @extend_schema(
        operation_id="task_departments", responses={200: OptionsSerializer}, tags=["tasks"]
    )
    def get(self, request: Request) -> Response:
        departments = services.assignable_departments(_actor(request))
        return _no_store({"results": [{"id": d.pk, "name": d.name} for d in departments]})


class TaskAssigneesView(APIView):
    """Employees a task of the given department may be assigned to (names only)."""

    @extend_schema(
        operation_id="task_assignees",
        parameters=[OpenApiParameter("department_id", str, required=True)],
        responses={200: OptionsSerializer, 400: ErrorSerializer},
        tags=["tasks"],
    )
    def get(self, request: Request) -> Response:
        try:
            department_id = UUID(request.query_params.get("department_id", ""))
        except ValueError:
            raise DomainError("department_not_found", "No such open department.") from None
        people = services.eligible_assignees(_actor(request), department_id)
        return _no_store({"results": [{"id": u.pk, "name": u.display_name} for u in people]})


class TaskCollectionView(APIView):
    @extend_schema(
        operation_id="tasks_list",
        parameters=[OpenApiParameter("view", str, enum=VIEWS, description="Default: mine.")],
        responses={200: TaskListSerializer, 400: ErrorSerializer},
        tags=["tasks"],
    )
    def get(self, request: Request) -> Response:
        view = request.query_params.get("view", "mine")
        tasks = (
            services.board(_actor(request), view=view)
            .annotate(
                total=Count("checkpoints"),
                done=Count("checkpoints", filter=Q(checkpoints__is_done=True)),
            )
            .order_by("due_at", "created_at")[:_MAX_CARDS]
        )
        return _no_store({"results": [_card(t, t.done, t.total) for t in tasks]})

    @extend_schema(
        operation_id="tasks_create",
        request=TaskCreateSerializer,
        responses={201: TaskCreatedSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["tasks"],
    )
    def post(self, request: Request) -> Response:
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        task = services.create_task(actor=actor, **serializer.validated_data)
        # Q02: the creator always gets a receipt, and the task itself only if
        # they may read it (assignee, manager of the department, superuser).
        visible = policy.allowed(actor, policy.READ, task)
        body = {
            "id": task.pk,
            "title": task.title,
            "task": _detail(actor, services.get_task(actor, task.pk)) if visible else None,
        }
        return _no_store(body, status.HTTP_201_CREATED)


class TaskView(APIView):
    @extend_schema(
        operation_id="tasks_get", responses={200: TaskDetailSerializer, **_ERRORS}, tags=["tasks"]
    )
    def get(self, request: Request, task_id: UUID) -> Response:
        return _task_response(_actor(request), task_id)

    @extend_schema(
        operation_id="tasks_update",
        request=TaskUpdateSerializer,
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def patch(self, request: Request, task_id: UUID) -> Response:
        serializer = TaskUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = _actor(request)
        version: int | None = data["version"]
        # One save of the edit form: all of it or none of it. The version is
        # checked by the first operation; the following ones run in the same
        # transaction on the row it locked.
        with transaction.atomic():
            if "title" in data or "description" in data:
                services.update_content(
                    actor=actor,
                    task_id=task_id,
                    title=data.get("title"),
                    description=data.get("description"),
                    expected_version=version,
                )
                version = None
            if "due_at" in data:
                services.change_deadline(
                    actor=actor, task_id=task_id, due_at=data["due_at"], expected_version=version
                )
                version = None
            if "priority" in data:
                services.change_priority(
                    actor=actor,
                    task_id=task_id,
                    priority=data["priority"],
                    expected_version=version,
                )
                version = None
            if "assignee_id" in data:
                services.reassign(
                    actor=actor,
                    task_id=task_id,
                    assignee_id=data["assignee_id"],
                    expected_version=version,
                )
        return _task_response(actor, task_id)


class TaskTransitionView(APIView):
    @extend_schema(
        operation_id="tasks_transition",
        request=TransitionSerializer,
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def post(self, request: Request, task_id: UUID) -> Response:
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        services.change_status(
            actor=actor,
            task_id=task_id,
            status_id=serializer.validated_data["status_id"],
            expected_version=serializer.validated_data["version"],
        )
        return _task_response(actor, task_id)


def _simple_action(name: str, operation: Any) -> type[APIView]:
    class View(APIView):
        @extend_schema(
            operation_id=f"tasks_{name}",
            request=None,
            responses={200: TaskDetailSerializer, **_ERRORS},
            tags=["tasks"],
        )
        def post(self, request: Request, task_id: UUID) -> Response:
            actor = _actor(request)
            task = operation(actor=actor, task_id=task_id)
            if task.deleted_at is not None and not policy.allowed(actor, "task.delete", task):
                return _no_store(None, status.HTTP_204_NO_CONTENT)
            return _task_response(actor, task_id)

    View.__name__ = f"Task{name.title()}View"
    return View


TaskArchiveView = _simple_action("archive", services.archive_task)
TaskReopenView = _simple_action("reopen", services.reopen_task)
TaskTrashView = _simple_action("trash", services.trash_task)
TaskRestoreView = _simple_action("restore", services.restore_task)


class TaskCheckpointsView(APIView):
    @extend_schema(
        operation_id="tasks_add_checkpoint",
        request=CheckpointCreateSerializer,
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def post(self, request: Request, task_id: UUID) -> Response:
        serializer = CheckpointCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        services.add_checkpoint(
            actor=actor, task_id=task_id, label=serializer.validated_data["text"]
        )
        return _task_response(actor, task_id)


class TaskCheckpointView(APIView):
    @extend_schema(
        operation_id="tasks_set_checkpoint",
        request=CheckpointUpdateSerializer,
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def patch(self, request: Request, task_id: UUID, checkpoint_id: UUID) -> Response:
        serializer = CheckpointUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        services.set_checkpoint_done(
            actor=actor,
            task_id=task_id,
            checkpoint_id=checkpoint_id,
            done=serializer.validated_data["is_done"],
        )
        return _task_response(actor, task_id)

    @extend_schema(
        operation_id="tasks_remove_checkpoint",
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def delete(self, request: Request, task_id: UUID, checkpoint_id: UUID) -> Response:
        actor = _actor(request)
        services.remove_checkpoint(actor=actor, task_id=task_id, checkpoint_id=checkpoint_id)
        return _task_response(actor, task_id)


class TaskCommentsView(APIView):
    @extend_schema(
        operation_id="tasks_add_comment",
        request=CommentWriteSerializer,
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def post(self, request: Request, task_id: UUID) -> Response:
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        services.add_comment(actor=actor, task_id=task_id, body=serializer.validated_data["text"])
        return _task_response(actor, task_id)


class TaskCommentView(APIView):
    @extend_schema(
        operation_id="tasks_edit_comment",
        request=CommentWriteSerializer,
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def patch(self, request: Request, task_id: UUID, comment_id: UUID) -> Response:
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        services.edit_comment(
            actor=actor,
            task_id=task_id,
            comment_id=comment_id,
            body=serializer.validated_data["text"],
        )
        return _task_response(actor, task_id)

    @extend_schema(
        operation_id="tasks_delete_comment",
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def delete(self, request: Request, task_id: UUID, comment_id: UUID) -> Response:
        actor = _actor(request)
        services.delete_comment(actor=actor, task_id=task_id, comment_id=comment_id)
        return _task_response(actor, task_id)
