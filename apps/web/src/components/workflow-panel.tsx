"use client";

import { API_PATHS, type Workflow, type WorkflowStatus } from "@crm/contracts";
import { useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";

import { callApi } from "@/lib/api-client";

const ERROR_KEYS = [
  "invalid_status_name",
  "status_name_taken",
  "invalid_moves",
  "invalid_order",
  "status_retired",
  "status_active",
  "status_not_found",
  "last_new_status",
  "replacement_required",
  "invalid_replacement",
  "unsafe_replacement",
  "invalid_status_display",
  "permission_denied",
  "unavailable",
] as const;
type ErrorKey = (typeof ERROR_KEYS)[number];

function toErrorKey(code: string): ErrorKey {
  return (ERROR_KEYS as readonly string[]).includes(code) ? (code as ErrorKey) : "unavailable";
}

const CATEGORIES = ["new", "active", "completed", "cancelled"] as const;
type Category = (typeof CATEGORIES)[number];

function isOpen(category: string): boolean {
  return category === "new" || category === "active";
}

/** The server accepts a replacement only of the same kind; offer nothing else. */
function sameKind(a: string, b: string): boolean {
  return a === b || (isOpen(a) && isOpen(b));
}

const fieldClass =
  "h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const buttonClass =
  "h-9 rounded-md border border-border px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";
const primaryClass =
  "h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";

export function WorkflowPanel({ initialStatuses }: { initialStatuses: WorkflowStatus[] }) {
  const t = useTranslations("workflow");
  const [statuses, setStatuses] = useState(initialStatuses);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [retiring, setRetiring] = useState<string | null>(null);
  const createRef = useRef<HTMLFormElement>(null);
  // The new status: whether its cards show the project and whether the column
  // is divided by project (which needs the project to be shown).
  const [newShow, setNewShow] = useState(true);
  const [newGroup, setNewGroup] = useState(false);

  const active = statuses.filter((status) => status.is_active);
  const retired = statuses.filter((status) => !status.is_active);

  // Every operation answers with the whole configuration.
  async function change(path: string, method: "POST" | "PATCH", body?: unknown): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      const result = await callApi<Workflow>(path, { method, body });
      if (!result.ok) {
        setError(toErrorKey(result.code));
        return false;
      }
      setStatuses(result.data.results);
      return true;
    } finally {
      setBusy(false);
    }
  }

  const pathOf = (status: WorkflowStatus) => `${API_PATHS.workflowStatuses}/${status.id}`;

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void change(API_PATHS.workflowStatuses, "POST", {
      name: String(data.get("name") ?? ""),
      category: String(data.get("category") ?? "active"),
      show_project: newShow,
      group_by_project: newShow && newGroup,
    }).then((ok) => {
      if (ok) {
        createRef.current?.reset();
        setNewShow(true);
        setNewGroup(false);
      }
    });
  }

  function rename(event: FormEvent<HTMLFormElement>, status: WorkflowStatus) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "");
    void change(pathOf(status), "PATCH", { name }).then((ok) => {
      if (ok) {
        setRenaming(null);
      }
    });
  }

  function move(index: number, step: -1 | 1) {
    const order = active.map((status) => status.id);
    const target = index + step;
    const moved = order[index];
    const other = order[target];
    if (moved === undefined || other === undefined) {
      return;
    }
    order[index] = other;
    order[target] = moved;
    void change(API_PATHS.workflowOrder, "POST", { status_ids: order });
  }

  function toggleMove(status: WorkflowStatus, targetId: string, allowed: boolean) {
    const next = allowed
      ? [...status.next_status_ids, targetId]
      : status.next_status_ids.filter((id) => id !== targetId);
    void change(pathOf(status), "PATCH", { next_status_ids: next });
  }

  function retire(event: FormEvent<HTMLFormElement>, status: WorkflowStatus) {
    event.preventDefault();
    const replacement = String(new FormData(event.currentTarget).get("replacement_id") ?? "");
    void change(`${pathOf(status)}/retire`, "POST", {
      replacement_id: replacement || null,
    }).then((ok) => {
      if (ok) {
        setRetiring(null);
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

      <form
        ref={createRef}
        onSubmit={create}
        aria-label={t("addTitle")}
        className="flex flex-wrap items-end gap-3"
      >
        <label className="flex min-w-60 flex-1 flex-col gap-1 text-sm font-medium">
          {t("nameLabel")}
          <input name="name" required maxLength={80} autoComplete="off" className={fieldClass} />
        </label>
        <label className="flex min-w-48 flex-col gap-1 text-sm font-medium">
          {t("categoryLabel")}
          <select name="category" defaultValue="active" className={fieldClass}>
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {t(`categories.${category}`)} — {t(`categoryHints.${category}`)}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="flex w-full flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">{t("projectsTitle")}</legend>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={newShow}
              onChange={(event) => setNewShow(event.target.checked)}
            />
            {t("showProject")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={newShow && newGroup}
              disabled={!newShow}
              onChange={(event) => setNewGroup(event.target.checked)}
            />
            {t("groupByProject")}
          </label>
        </fieldset>
        <button type="submit" disabled={busy} className={primaryClass}>
          {t("create")}
        </button>
      </form>

      {active.map((status, index) => {
        const others = active.filter((other) => other.id !== status.id);
        const replacements = others.filter((other) => sameKind(status.category, other.category));
        return (
          <section
            key={status.id}
            aria-labelledby={`status-${status.id}`}
            className="flex flex-col gap-4 rounded-md border border-border p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-col gap-1">
                <h2 id={`status-${status.id}`} className="text-lg font-semibold">
                  {status.name}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {t(`categories.${status.category as Category}`)} ·{" "}
                  {t("taskCount", { count: status.task_count })}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy || index === 0}
                  onClick={() => move(index, -1)}
                  className={buttonClass}
                >
                  {t("moveUp")}
                </button>
                <button
                  type="button"
                  disabled={busy || index === active.length - 1}
                  onClick={() => move(index, 1)}
                  className={buttonClass}
                >
                  {t("moveDown")}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setRenaming(renaming === status.id ? null : status.id)}
                  className={buttonClass}
                >
                  {t("rename")}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setRetiring(retiring === status.id ? null : status.id)}
                  className={buttonClass}
                >
                  {t("retire")}
                </button>
              </div>
            </div>

            {renaming === status.id ? (
              <form
                onSubmit={(event) => rename(event, status)}
                className="flex flex-wrap items-end gap-3"
              >
                <label className="flex min-w-60 flex-1 flex-col gap-1 text-sm font-medium">
                  {t("nameLabel")}
                  <input
                    name="name"
                    required
                    maxLength={80}
                    defaultValue={status.name}
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

            {retiring === status.id ? (
              <form
                onSubmit={(event) => retire(event, status)}
                aria-label={t("retireTitle", { name: status.name })}
                className="flex flex-col gap-3 rounded-md border border-border bg-surface p-3"
              >
                <p className="text-sm">
                  {status.task_count > 0
                    ? t("retireUsed", { count: status.task_count })
                    : t("retireUnused")}
                </p>
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex min-w-60 flex-1 flex-col gap-1 text-sm font-medium">
                    {t("replacementLabel")}
                    <select
                      name="replacement_id"
                      defaultValue=""
                      required={status.task_count > 0}
                      className={fieldClass}
                    >
                      <option value="">{t("noReplacement")}</option>
                      {replacements.map((other) => (
                        <option key={other.id} value={other.id}>
                          {other.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="submit" disabled={busy} className={primaryClass}>
                    {t("retireConfirm")}
                  </button>
                  <button type="button" onClick={() => setRetiring(null)} className={buttonClass}>
                    {t("cancel")}
                  </button>
                </div>
              </form>
            ) : null}

            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-sm font-medium">{t("projectsTitle")}</legend>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={status.show_project}
                  onChange={(event) =>
                    // Without the project there is nothing to divide by.
                    void change(
                      pathOf(status),
                      "PATCH",
                      event.target.checked
                        ? { show_project: true }
                        : { show_project: false, group_by_project: false },
                    )
                  }
                />
                {t("showProject")}
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  disabled={busy || !status.show_project}
                  checked={status.group_by_project}
                  onChange={(event) =>
                    void change(pathOf(status), "PATCH", {
                      group_by_project: event.target.checked,
                    })
                  }
                />
                {t("groupByProject")}
              </label>
            </fieldset>

            {status.category === "completed" ? (
              <p className="text-sm text-muted-foreground">{t("completedHint")}</p>
            ) : (
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-2 text-sm font-medium">{t("movesTitle")}</legend>
                {others.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t("noOthers")}</p>
                ) : (
                  <div className="flex flex-wrap gap-x-5 gap-y-2">
                    {others.map((other) => (
                      <label key={other.id} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          disabled={busy}
                          checked={status.next_status_ids.includes(other.id)}
                          onChange={(event) => toggleMove(status, other.id, event.target.checked)}
                        />
                        {other.name}
                      </label>
                    ))}
                  </div>
                )}
              </fieldset>
            )}
          </section>
        );
      })}

      {retired.length > 0 ? (
        <section aria-labelledby="retired-statuses" className="flex flex-col gap-3">
          <h2 id="retired-statuses" className="text-lg font-semibold">
            {t("retiredTitle")}
          </h2>
          <ul className="flex flex-col gap-2">
            {retired.map((status) => (
              <li
                key={status.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
              >
                <span>
                  {status.name}{" "}
                  <span className="text-muted-foreground">
                    · {t(`categories.${status.category as Category}`)}
                  </span>
                </span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void change(`${pathOf(status)}/restore`, "POST")}
                  className={buttonClass}
                >
                  {t("restore")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
