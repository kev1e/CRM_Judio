from django.urls import path

from crm.tasks.api import views, workflow_views

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
    path("workflow/statuses", workflow_views.WorkflowView.as_view(), name="workflow"),
    path("workflow/order", workflow_views.WorkflowOrderView.as_view(), name="workflow-order"),
    path(
        "workflow/statuses/<uuid:status_id>",
        workflow_views.WorkflowStatusView.as_view(),
        name="workflow-status",
    ),
    path(
        "workflow/statuses/<uuid:status_id>/retire",
        workflow_views.WorkflowRetireView.as_view(),
        name="workflow-retire",
    ),
    path(
        "workflow/statuses/<uuid:status_id>/restore",
        workflow_views.WorkflowRestoreView.as_view(),
        name="workflow-restore",
    ),
]
