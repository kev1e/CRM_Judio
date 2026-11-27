"use client";

import {
  API_PATHS,
  type Candidate,
  type ParticipantAdded,
  type Project,
  type ProjectInvitation,
  type ProjectList,
} from "@crm/contracts";
import { useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";

import { ProjectZones } from "@/components/project-zones";
import { callApi } from "@/lib/api-client";

const ERROR_KEYS = [
  "invalid_project_name",
  "project_name_taken",
  "project_not_found",
  "project_closed",
  "department_not_found",
  "not_in_department",
  "already_member",
  "already_invited",
  "member_not_found",
  "invitation_not_found",
  "invitation_decided",
  "invalid_zone_name",
  "zone_name_taken",
  "zone_not_found",
  "zone_member_not_found",
  "permission_denied",
  "unavailable",
] as const;
type ErrorKey = (typeof ERROR_KEYS)[number];

function toErrorKey(code: string): ErrorKey {
  return (ERROR_KEYS as readonly string[]).includes(code) ? (code as ErrorKey) : "unavailable";
}

type Option = { id: string; name: string };

const fieldClass =
  "h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const buttonClass =
  "h-9 rounded-md border border-border px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";
const primaryClass =
  "h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";

export function ProjectsPanel({
  initial,
  departments,
  candidates,
}: {
  initial: ProjectList;
  /** Departments the viewer manages: a new project belongs to one of them. */
  departments: Option[];
  /** Employees who can be added or invited; empty for somebody who runs no project. */
  candidates: Candidate[];
}) {
  const t = useTranslations("projects");
  const [projects, setProjects] = useState(initial.results);
  const [inbox, setInbox] = useState(initial.invitations_to_decide);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [notice, setNotice] = useState<"added" | "invited" | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const createRef = useRef<HTMLFormElement>(null);

  function put(project: Project) {
    setProjects((current) =>
      current.some((item) => item.id === project.id)
        ? current.map((item) => (item.id === project.id ? project : item))
        : [...current, project].sort((a, b) => a.name.localeCompare(b.name, "ru")),
    );
  }

  async function send<T>(
    path: string,
    method: "POST" | "PATCH" | "DELETE",
    body?: unknown,
  ): Promise<T | null> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await callApi<T>(path, { method, body });
      if (!result.ok) {
        setError(toErrorKey(result.code));
        return null;
      }
      return result.data ?? ({} as T);
    } finally {
      setBusy(false);
    }
  }

  async function change(path: string, method: "POST" | "PATCH" | "DELETE", body?: unknown) {
    const project = await send<Project>(path, method, body);
    if (project) {
      put(project);
    }
    return project !== null;
  }

  /** After a decision the lists are read again: memberships may have changed. */
  async function reload() {
    const result = await callApi<ProjectList>(API_PATHS.projects, { method: "GET" });
    if (result.ok) {
      setProjects(result.data.results);
      setInbox(result.data.invitations_to_decide);
    }
  }

  async function decide(invitation: ProjectInvitation, action: "approve" | "decline" | "cancel") {
    const done = await send<object>(
      `${API_PATHS.projectInvitations}/${invitation.id}/${action}`,
      "POST",
      action === "decline" ? {} : undefined,
    );
    if (done) {
      await reload();
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void change(API_PATHS.projects, "POST", {
      name: String(data.get("name") ?? ""),
      department_id: String(data.get("department_id") ?? ""),
    }).then((ok) => {
      if (ok) {
        createRef.current?.reset();
      }
    });
  }

  function addMember(event: FormEvent<HTMLFormElement>, project: Project) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const userId = String(data.get("user_id") ?? "");
    const departmentId = String(data.get("department_id") ?? "");
    if (!userId || !departmentId) {
      return;
    }
    void send<ParticipantAdded>(`${API_PATHS.projects}/${project.id}/members`, "POST", {
      user_id: userId,
      department_id: departmentId,
    }).then((added) => {
      if (added) {
        put(added.project);
        setNotice(added.outcome);
        setChosen((current) => ({ ...current, [project.id]: "" }));
        form.reset();
      }
    });
  }

  return (
    <div className="flex flex-col gap-8">
      {error ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="rounded-md border border-border px-3 py-2 text-sm">
          {t(notice)}
        </p>
      ) : null}

      {inbox.length > 0 ? (
        <section
          aria-labelledby="projects-inbox"
          className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4"
        >
          <h2 id="projects-inbox" className="text-lg font-semibold">
            {t("inboxTitle")}
          </h2>
          <ul className="flex flex-col gap-3">
            {inbox.map((invitation) => (
              <li key={invitation.id} className="flex flex-wrap items-center gap-3 text-sm">
                <span className="min-w-60 flex-1">
                  {t("inboxItem", {
                    requester: invitation.requested_by.name,
                    name: invitation.user.name,
                    department: invitation.department.name,
                    project: invitation.project.name,
                    projectDepartment: invitation.project_department.name,
                  })}
                </span>
                <button
                  type="button"
                  disabled={busy}
                  aria-label={t("approveLabel", { name: invitation.user.name })}
                  onClick={() => void decide(invitation, "approve")}
                  className={primaryClass}
                >
                  {t("approve")}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  aria-label={t("declineLabel", { name: invitation.user.name })}
                  onClick={() => void decide(invitation, "decline")}
                  className={buttonClass}
                >
                  {t("decline")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {initial.can_create && departments.length > 0 ? (
        <form
          ref={createRef}
          onSubmit={create}
          aria-label={t("addTitle")}
          className="flex flex-wrap items-end gap-3"
        >
          <label className="flex min-w-60 flex-1 flex-col gap-1 text-sm font-medium">
            {t("nameLabel")}
            <input name="name" required maxLength={150} autoComplete="off" className={fieldClass} />
          </label>
          <label className="flex min-w-48 flex-col gap-1 text-sm font-medium">
            {t("departmentLabel")}
            <select name="department_id" required className={fieldClass}>
              {departments.map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={busy} className={primaryClass}>
            {t("create")}
          </button>
        </form>
      ) : null}

      {projects.length === 0 ? (
        <p className="text-muted-foreground">{t(initial.can_create ? "empty" : "emptyReadOnly")}</p>
      ) : null}

      {projects.map((project) => {
        const base = `${API_PATHS.projects}/${project.id}`;
        const editable = project.can_manage && project.is_active;
        const taken = new Set([
          ...project.members.map((member) => member.user.id),
          ...project.pending_invitations.map((invitation) => invitation.user.id),
        ]);
        const available = candidates.filter((candidate) => !taken.has(candidate.id));
        const selected = available.find((candidate) => candidate.id === chosen[project.id]);
        return (
          <section
            key={project.id}
            aria-labelledby={`project-${project.id}`}
            className="flex flex-col gap-4 rounded-md border border-border p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-col gap-1">
                <h2 id={`project-${project.id}`} className="text-lg font-semibold">
                  {project.name}
                  {project.is_active ? null : (
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      ({t("closed")})
                    </span>
                  )}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {t("department", { name: project.department.name })}
                </p>
              </div>
              {project.can_manage ? (
                <div className="flex flex-wrap gap-2">
                  {project.is_active ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setRenaming(renaming === project.id ? null : project.id)}
                      className={buttonClass}
                    >
                      {t("rename")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void change(base, "PATCH", { is_active: !project.is_active })}
                    className={buttonClass}
                  >
                    {t(project.is_active ? "close" : "reopen")}
                  </button>
                </div>
              ) : null}
            </div>

            {renaming === project.id ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  const name = String(new FormData(event.currentTarget).get("name") ?? "");
                  void change(base, "PATCH", { name }).then((ok) => {
                    if (ok) {
                      setRenaming(null);
                    }
                  });
                }}
                className="flex flex-wrap items-end gap-3"
              >
                <label className="flex min-w-60 flex-1 flex-col gap-1 text-sm font-medium">
                  {t("nameLabel")}
                  <input
                    name="name"
                    required
                    maxLength={150}
                    defaultValue={project.name}
                    autoComplete="off"
                    className={fieldClass}
                  />
                </label>
                <button type="submit" disabled={busy} className={primaryClass}>
                  {t("save")}
                </button>
                <button type="button" onClick={() => setRenaming(null)} className={buttonClass}>
                  {t("cancel")}
                </button>
              </form>
            ) : null}

            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">{t("members")}</h3>
              {project.members.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("nobody")}</p>
              ) : (
                <ul className="flex flex-col gap-1 text-sm">
                  {project.members.map((member) => (
                    <li key={member.user.id} className="flex items-center gap-2">
                      <span className="flex-1">
                        {t("memberFrom", {
                          name: member.user.name,
                          department: member.department.name,
                        })}
                        {member.is_active ? null : (
                          <span className="text-muted-foreground"> ({t("inactiveMark")})</span>
                        )}
                      </span>
                      {project.can_manage ? (
                        <button
                          type="button"
                          disabled={busy}
                          aria-label={t("remove", { name: member.user.name })}
                          onClick={() => void change(`${base}/members/${member.user.id}`, "DELETE")}
                          className="rounded px-2 text-muted-foreground hover:bg-muted"
                        >
                          ×
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {project.pending_invitations.length > 0 ? (
              <div className="flex flex-col gap-2">
                <h3 className="text-sm font-medium">{t("pending")}</h3>
                <ul className="flex flex-col gap-1 text-sm">
                  {project.pending_invitations.map((invitation) => (
                    <li key={invitation.id} className="flex items-center gap-2">
                      <span className="flex-1">
                        {t("pendingItem", {
                          name: invitation.user.name,
                          department: invitation.department.name,
                        })}
                      </span>
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={t("cancelInvitation", { name: invitation.user.name })}
                        onClick={() => void decide(invitation, "cancel")}
                        className="rounded px-2 text-muted-foreground hover:bg-muted"
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {editable ? (
              <form
                onSubmit={(event) => addMember(event, project)}
                aria-label={t("addMember")}
                className="flex flex-col gap-2"
              >
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex min-w-52 flex-1 flex-col gap-1 text-sm font-medium">
                    {t("employeeLabel")}
                    <select
                      name="user_id"
                      required
                      value={chosen[project.id] ?? ""}
                      onChange={(event) =>
                        setChosen((current) => ({ ...current, [project.id]: event.target.value }))
                      }
                      className={fieldClass}
                    >
                      <option value="">{t("chooseEmployee")}</option>
                      {available.map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          {candidate.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex min-w-48 flex-col gap-1 text-sm font-medium">
                    {t("fromDepartmentLabel")}
                    <select
                      name="department_id"
                      required
                      disabled={!selected}
                      key={selected?.id ?? "none"}
                      className={fieldClass}
                    >
                      {(selected?.departments ?? []).map((department) => (
                        <option key={department.id} value={department.id}>
                          {department.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="submit" disabled={busy || !selected} className={buttonClass}>
                    {t("add")}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">{t("addHint")}</p>
              </form>
            ) : null}

            <ProjectZones project={project} editable={editable} busy={busy} change={change} />
          </section>
        );
      })}
    </div>
  );
}
