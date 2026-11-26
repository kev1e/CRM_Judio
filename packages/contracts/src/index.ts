// Public surface of the API contract. Everything here is generated from the
// OpenAPI schema exported by apps/api.
export type * from "./generated/types.gen";

/** Paths of the endpoints, kept next to their types so callers do not hard-code strings. */
export const API_PATHS = {
  health: "/api/v1/health",
  ready: "/api/v1/ready",
  login: "/api/v1/auth/login",
  loginComplete: "/api/v1/auth/login/complete",
  me: "/api/v1/auth/me",
  logout: "/api/v1/auth/logout",
  passwordSetup: "/api/v1/auth/password/setup",
  users: "/api/v1/users",
  departments: "/api/v1/departments",
  projects: "/api/v1/projects",
  projectCandidates: "/api/v1/project-candidates",
  projectInvitations: "/api/v1/project-invitations",
  requestTemplates: "/api/v1/request-templates",
  requestForms: "/api/v1/request-forms",
  requests: "/api/v1/requests",
  tasks: "/api/v1/tasks",
  taskStatuses: "/api/v1/task-statuses",
  taskDepartments: "/api/v1/task-departments",
  workflowStatuses: "/api/v1/workflow/statuses",
  workflowOrder: "/api/v1/workflow/order",
  taskProjects: "/api/v1/task-projects",
  taskAssignees: "/api/v1/task-assignees",
} as const satisfies Record<string, `/api/v${number}/${string}`>;
