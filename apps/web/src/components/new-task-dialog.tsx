"use client";

import { API_PATHS, type Options, type TaskCreated } from "@crm/contracts";
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useState } from "react";

import { Modal } from "@/components/modal";
import { callApi } from "@/lib/api-client";
import { fromLocalInput } from "@/lib/tasks";

const ERRORS = [
  "invalid_title",
  "assignee_not_eligible",
  "department_not_found",
  "validation_error",
  "permission_denied",
  "unavailable",
] as const;
type ErrorKey = (typeof ERRORS)[number];

const fieldClass =
  "h-11 w-full rounded-md border border-border bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

type Option = Options["results"][number];

export function NewTaskDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (created: TaskCreated) => void;
}) {
  const t = useTranslations("newTask");
  const tBoard = useTranslations("board");
  const tErrors = useTranslations("task.errors");
  const [departments, setDepartments] = useState<Option[] | null>(null);
  const [departmentId, setDepartmentId] = useState("");
  const [assignees, setAssignees] = useState<Option[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);

  useEffect(() => {
    let active = true;
    void callApi<Options>(API_PATHS.taskDepartments, { method: "GET" }).then((result) => {
      if (!active) {
        return;
      }
      const list = result.ok ? result.data.results : [];
      setDepartments(list);
      setDepartmentId(list[0]?.id ?? "");
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!departmentId) {
      return;
    }
    let active = true;
    void callApi<Options>(`${API_PATHS.taskAssignees}?department_id=${departmentId}`, {
      method: "GET",
    }).then((result) => {
      if (active) {
        setAssignees(result.ok ? result.data.results : []);
      }
    });
    return () => {
      active = false;
    };
  }, [departmentId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    const result = await callApi<TaskCreated>(API_PATHS.tasks, {
      method: "POST",
      body: {
        title: String(data.get("title") ?? ""),
        description: String(data.get("description") ?? ""),
        department_id: departmentId,
        assignee_id: String(data.get("assignee_id") ?? ""),
        priority: String(data.get("priority") ?? "normal"),
        task_type: String(data.get("task_type") ?? "task"),
        due_at: fromLocalInput(String(data.get("due_at") ?? "")),
      },
    });
    setBusy(false);
    if (result.ok) {
      onCreated(result.data);
    } else {
      setError(
        (ERRORS as readonly string[]).includes(result.code)
          ? (result.code as ErrorKey)
          : "unavailable",
      );
    }
  }

  return (
    <Modal labelledBy="new-task-title" onClose={onClose}>
      <h2 id="new-task-title" className="text-xl font-semibold">
        {t("title")}
      </h2>
      {departments !== null && departments.length === 0 ? (
        <>
          <p className="text-muted-foreground">{t("noDepartments")}</p>
          <button
            type="button"
            onClick={onClose}
            className="h-11 w-fit rounded-md border border-border px-4 hover:bg-muted"
          >
            {t("cancel")}
          </button>
        </>
      ) : (
        <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4">
          {error ? (
            <p
              role="alert"
              className="rounded-md border border-danger px-3 py-2 text-sm text-danger"
            >
              {tErrors(error)}
            </p>
          ) : null}
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("titleLabel")}
            <input name="title" required maxLength={200} autoFocus className={fieldClass} />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("departmentLabel")}
              <select
                value={departmentId}
                onChange={(event) => {
                  setAssignees([]);
                  setDepartmentId(event.target.value);
                }}
                required
                className={fieldClass}
              >
                {(departments ?? []).map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("assigneeLabel")}
              <select name="assignee_id" required defaultValue="" className={fieldClass}>
                <option value="" disabled>
                  {assignees.length === 0 ? t("noAssignees") : t("chooseAssignee")}
                </option>
                {assignees.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("priorityLabel")}
              <select name="priority" defaultValue="normal" className={fieldClass}>
                {(["low", "normal", "high", "urgent"] as const).map((priority) => (
                  <option key={priority} value={priority}>
                    {tBoard(`priority.${priority}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("dueLabel")}
              <input name="due_at" type="datetime-local" className={fieldClass} />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("typeLabel")}
              <select name="task_type" defaultValue="task" className={fieldClass}>
                <option value="task">{t("typeTask")}</option>
                <option value="request">{t("typeRequest")}</option>
              </select>
            </label>
          </div>
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("descriptionLabel")}
            <textarea
              name="description"
              rows={4}
              maxLength={20000}
              className={`${fieldClass} h-auto py-2`}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={busy}
              className="h-11 rounded-md bg-primary px-4 font-medium text-primary-foreground hover:opacity-90 disabled:opacity-60"
            >
              {busy ? t("creating") : t("create")}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="h-11 rounded-md border border-border px-4 hover:bg-muted"
            >
              {t("cancel")}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
