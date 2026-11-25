from django.urls import path

from crm.tasks.api import views

urlpatterns = [
    path("task-statuses", views.StatusListView.as_view(), name="task-statuses"),
    path("task-departments", views.TaskDepartmentsView.as_view(), name="task-departments"),
    path("task-assignees", views.TaskAssigneesView.as_view(), name="task-assignees"),
    path("tasks", views.TaskCollectionView.as_view(), name="tasks"),
    path("tasks/<uuid:task_id>", views.TaskView.as_view(), name="task"),
    path(
        "tasks/<uuid:task_id>/transitions",
        views.TaskTransitionView.as_view(),
        name="task-transitions",
    ),
    path("tasks/<uuid:task_id>/archive", views.TaskArchiveView.as_view(), name="task-archive"),
    path("tasks/<uuid:task_id>/reopen", views.TaskReopenView.as_view(), name="task-reopen"),
    path("tasks/<uuid:task_id>/trash", views.TaskTrashView.as_view(), name="task-trash"),
    path("tasks/<uuid:task_id>/restore", views.TaskRestoreView.as_view(), name="task-restore"),
    path(
        "tasks/<uuid:task_id>/checkpoints",
        views.TaskCheckpointsView.as_view(),
        name="task-checkpoints",
    ),
    path(
        "tasks/<uuid:task_id>/checkpoints/<uuid:checkpoint_id>",
        views.TaskCheckpointView.as_view(),
        name="task-checkpoint",
    ),
]
