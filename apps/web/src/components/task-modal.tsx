"use client";

import { API_PATHS, type Options, type Status, type TaskDetail } from "@crm/contracts";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { Modal } from "@/components/modal";
import { callApi, uploadFile } from "@/lib/api-client";
import { fromLocalInput, toLocalInput } from "@/lib/tasks";

const ERRORS = [
  "permission_denied",
  "transition_not_allowed",
  "task_changed",
  "task_not_found",
  "task_archived",
  "task_deleted",
  "invalid_title",
  "assignee_not_eligible",
  "previous_status_unavailable",
  "invalid_checkpoint",
  "invalid_comment",
  "file_too_large",
  "file_type_not_allowed",
  "file_content_mismatch",
  "file_archive_unsafe",
  "file_empty",
  "file_missing",
  "storage_unavailable",
  "attachment_not_found",
  "comment_not_found",
  "validation_error",
  "unavailable",
] as const;
type ErrorKey = (typeof ERRORS)[number];
const HISTORY_KEYS = [
  "created",
  "content_changed",
  "deadline_changed",
  "priority_changed",
  "reassigned",
  "status_changed",
  "status_remapped",
  "completed",
  "archived",
  "reopened",
  "trashed",
  "restored",
  "checkpoint_added",
  "checkpoint_done",
  "checkpoint_undone",
  "checkpoint_removed",
  "comment_added",
  "comment_edited",
  "comment_deleted",
  "attachment_added",
  "attachment_deleted",
] as const;
type HistoryKey = (typeof HISTORY_KEYS)[number] | "other";

function toHistoryKey(action: string): HistoryKey {
  const key = action.replace(/^task\./, "");
  return (HISTORY_KEYS as readonly string[]).includes(key) ? (key as HistoryKey) : "other";
}

function toError(code: string): ErrorKey {
  return (ERRORS as readonly string[]).includes(code) ? (code as ErrorKey) : "unavailable";
}

const MAX_FILE_BYTES = 100 * 1024 * 1024;
const FILE_ACCEPT = ".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.webp,.zip";

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} Б`;
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} КБ`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} МБ`;
}

const fieldClass =
  "h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const buttonClass =
  "h-10 rounded-md border border-border px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";
const primaryClass =
  "h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";

/**
 * The task window: read-only by default, with a separate edit mode. Controls for
 * what the viewer may not do are absent or disabled with a reason; the server
 * checks every operation again whatever the interface shows.
 */
export function TaskModal({
  taskId,
  statuses,
  onClose,
  onChanged,
}: {
  taskId: string;
  statuses: readonly Status[];
  onClose: () => void;
  /** The task changed on the server (or left the viewer's reach): refresh the board. */
  onChanged: () => void;
}) {
  const t = useTranslations("task");
  const tBoard = useTranslations("board");
  const format = useFormatter();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [assignees, setAssignees] = useState<Options["results"]>([]);
  const checkpointRef = useRef<HTMLFormElement>(null);
  const commentRef = useRef<HTMLFormElement>(null);
  const fileRef = useRef<HTMLFormElement>(null);
  const [uploading, setUploading] = useState(false);
  const [editingComment, setEditingComment] = useState<string | null>(null);
  const base = `${API_PATHS.tasks}/${taskId}`;

  useEffect(() => {
    let active = true;
    void callApi<TaskDetail>(base, { method: "GET" }).then((result) => {
      if (!active) {
        return;
      }
      if (result.ok) {
        setTask(result.data);
      } else {
        setError(toError(result.code));
      }
    });
    return () => {
      active = false;
    };
  }, [base]);

  const canReassign = task?.actions.reassign ?? false;
  const departmentId = task?.department.id;
  useEffect(() => {
    if (!editing || !canReassign || !departmentId) {
      return;
    }
    let active = true;
    void callApi<Options>(`${API_PATHS.taskAssignees}?department_id=${departmentId}`, {
      method: "GET",
    }).then((result) => {
      if (active && result.ok) {
        setAssignees(result.data.results);
      }
    });
    return () => {
      active = false;
    };
  }, [editing, canReassign, departmentId]);

  function requestClose(): boolean {
    if (editing && dirty && !window.confirm(t("unsaved"))) {
      return false;
    }
    onClose();
    return true;
  }

  /** Run a change and show the task the server returns. Returns whether it worked. */
  async function run(
    path: string,
    method: "POST" | "PATCH" | "DELETE",
    body?: unknown,
  ): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      const result = await callApi<TaskDetail | undefined>(path, { method, body });
      if (!result.ok) {
        setError(toError(result.code));
        return false;
      }
      onChanged();
      if (result.data === undefined) {
        // The task left the viewer's reach (for example, it went to the trash).
        onClose();
      } else {
        setTask(result.data);
      }
      return true;
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!task) {
      return;
    }
    const data = new FormData(event.currentTarget);
    const body: Record<string, unknown> = { version: task.version };
    const title = String(data.get("title") ?? "").trim();
    const description = String(data.get("description") ?? "").trim();
    if (task.actions.edit && title !== task.title) {
      body.title = title;
    }
    if (task.actions.edit && description !== task.description) {
      body.description = description;
    }
    if (task.actions.deadline) {
      const due = fromLocalInput(String(data.get("due_at") ?? ""));
      if (due !== (task.due_at ? new Date(task.due_at).toISOString() : null)) {
        body.due_at = due;
      }
    }
    const priority = data.get("priority");
    if (task.actions.priority && priority && priority !== task.priority) {
      body.priority = priority;
    }
    const assignee = data.get("assignee_id");
    if (task.actions.reassign && assignee && assignee !== task.assignee.id) {
      body.assignee_id = assignee;
    }
    if (Object.keys(body).length === 1 || (await run(base, "PATCH", body))) {
      setEditing(false);
      setDirty(false);
    }
  }

  if (!task) {
    return (
      <Modal labelledBy="task-title" onClose={onClose}>
        <h2 id="task-title" className="text-xl font-semibold">
          {error ? t(`errors.${error}`) : t("loading")}
        </h2>
        <button type="button" onClick={onClose} className={`${buttonClass} w-fit`}>
          {t("close")}
        </button>
      </Modal>
    );
  }

  const locked = task.is_deleted || task.is_archived;
  const current = statuses.find((status) => status.id === task.status_id);
  const nextStatuses = statuses.filter((status) => current?.next_status_ids.includes(status.id));
  const statusReason = task.is_deleted
    ? "deleted"
    : task.is_archived
      ? "archived"
      : !task.actions.status
        ? "noRight"
        : nextStatuses.length === 0
          ? "noMoves"
          : null;
  const canEditAnything =
    !locked &&
    (task.actions.edit || task.actions.deadline || task.actions.priority || task.actions.reassign);
  const dateTime = (iso: string) =>
    format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" });

  return (
    <Modal labelledBy="task-title" onClose={requestClose}>
      {error ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}

      {editing ? (
        <form
          onSubmit={(event) => void save(event)}
          onChange={() => setDirty(true)}
          className="flex flex-col gap-4"
        >
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("fields.title")}
            <input
              id="task-title"
              name="title"
              defaultValue={task.title}
              required
              maxLength={200}
              readOnly={!task.actions.edit}
              autoFocus
              className={fieldClass}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("fields.description")}
            <textarea
              name="description"
              defaultValue={task.description}
              rows={5}
              maxLength={20000}
              readOnly={!task.actions.edit}
              className={`${fieldClass} h-auto py-2`}
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("fields.due")}
              <input
                name="due_at"
                type="datetime-local"
                defaultValue={toLocalInput(task.due_at)}
                disabled={!task.actions.deadline}
                className={fieldClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("fields.priority")}
              <select
                name="priority"
                defaultValue={task.priority}
                disabled={!task.actions.priority}
                className={fieldClass}
              >
                {(["low", "normal", "high", "urgent"] as const).map((priority) => (
                  <option key={priority} value={priority}>
                    {tBoard(`priority.${priority}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("fields.assignee")}
              <select
                name="assignee_id"
                defaultValue={task.assignee.id}
                disabled={!task.actions.reassign}
                className={fieldClass}
              >
                <option value={task.assignee.id}>{task.assignee.name}</option>
                {assignees
                  .filter((person) => person.id !== task.assignee.id)
                  .map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={busy} className={primaryClass}>
              {busy ? t("saving") : t("save")}
            </button>
            <button
              type="button"
              onClick={() => {
                if (!dirty || window.confirm(t("unsaved"))) {
                  setEditing(false);
                  setDirty(false);
                  setError(null);
                }
              }}
              className={buttonClass}
            >
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : (
        <>
          <div className="flex items-start justify-between gap-3">
            <h2 id="task-title" className="text-xl font-semibold break-words">
              {task.title}
            </h2>
            <button type="button" onClick={() => requestClose()} className={buttonClass}>
              {t("close")}
            </button>
          </div>

          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">{t("fields.status")}</dt>
            <dd>
              {statusReason ? (
                <span title={t("statusReadOnly", { reason: t(`reasons.${statusReason}`) })}>
                  {current?.name}
                  <span className="text-muted-foreground">
                    {" "}
                    — {t("statusReadOnly", { reason: t(`reasons.${statusReason}`) })}
                  </span>
                </span>
              ) : (
                <select
                  aria-label={t("fields.status")}
                  value={task.status_id}
                  disabled={busy}
                  onChange={(event) =>
                    void run(`${base}/transitions`, "POST", {
                      status_id: event.target.value,
                      version: task.version,
                    })
                  }
                  className={`${fieldClass} w-auto`}
                >
                  <option value={task.status_id}>{current?.name}</option>
                  {nextStatuses.map((status) => (
                    <option key={status.id} value={status.id}>
                      {status.name}
                    </option>
                  ))}
                </select>
              )}
            </dd>
            <dt className="text-muted-foreground">{t("fields.assignee")}</dt>
            <dd>{task.assignee.name}</dd>
            <dt className="text-muted-foreground">{t("fields.priority")}</dt>
            <dd>{tBoard(`priority.${task.priority}`)}</dd>
            <dt className="text-muted-foreground">{t("fields.due")}</dt>
            <dd>{task.due_at ? dateTime(task.due_at) : t("noDue")}</dd>
            <dt className="text-muted-foreground">{t("fields.department")}</dt>
            <dd>{task.department.name}</dd>
            <dt className="text-muted-foreground">{t("fields.author")}</dt>
            <dd>
              {task.author.name}, {dateTime(task.created_at)}
            </dd>
          </dl>

          <p className="text-sm whitespace-pre-wrap">
            {task.description || (
              <span className="text-muted-foreground">{t("noDescription")}</span>
            )}
          </p>

          <div className="flex flex-wrap gap-2">
            {canEditAnything ? (
              <button type="button" onClick={() => setEditing(true)} className={primaryClass}>
                {t("edit")}
              </button>
            ) : null}
            {task.actions.archive && !task.is_deleted ? (
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(`${base}/${task.is_archived ? "reopen" : "archive"}`, "POST")
                }
                className={buttonClass}
              >
                {task.is_archived ? t("reopen") : t("archive")}
              </button>
            ) : null}
            {task.actions.delete ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  if (task.is_deleted || window.confirm(t("confirmTrash"))) {
                    void run(`${base}/${task.is_deleted ? "restore" : "trash"}`, "POST");
                  }
                }}
                className={buttonClass}
              >
                {task.is_deleted ? t("restore") : t("trash")}
              </button>
            ) : null}
          </div>

          <details
            open={task.checkpoints.length > 0}
            className="rounded-md border border-border p-3"
          >
            <summary className="cursor-pointer text-sm font-medium">
              {t("checkpointsTitle")}
              {task.checkpoints_total > 0 ? (
                <span className="text-muted-foreground">
                  {" "}
                  {tBoard("checkpoints", {
                    done: task.checkpoints_done,
                    total: task.checkpoints_total,
                  })}
                </span>
              ) : null}
            </summary>
            <div className="mt-3 flex flex-col gap-2">
              {task.checkpoints.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("noCheckpoints")}</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {task.checkpoints.map((checkpoint) => (
                    <li key={checkpoint.id} className="flex items-center gap-2 text-sm">
                      <label className="flex flex-1 items-center gap-2">
                        <input
                          type="checkbox"
                          checked={checkpoint.is_done}
                          disabled={busy || locked || !task.actions.checkpoints_use}
                          onChange={(event) =>
                            void run(`${base}/checkpoints/${checkpoint.id}`, "PATCH", {
                              is_done: event.target.checked,
                            })
                          }
                          className="size-4"
                        />
                        <span
                          className={checkpoint.is_done ? "text-muted-foreground line-through" : ""}
                        >
                          {checkpoint.text}
                        </span>
                      </label>
                      {task.actions.checkpoints_manage && !locked ? (
                        <button
                          type="button"
                          disabled={busy}
                          aria-label={t("checkpointRemove", { text: checkpoint.text })}
                          onClick={() => void run(`${base}/checkpoints/${checkpoint.id}`, "DELETE")}
                          className="rounded px-2 text-muted-foreground hover:bg-muted"
                        >
                          ×
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
              {task.actions.checkpoints_use && !locked ? (
                <form
                  ref={checkpointRef}
                  onSubmit={(event) => {
                    event.preventDefault();
                    const text = String(new FormData(event.currentTarget).get("text") ?? "");
                    void run(`${base}/checkpoints`, "POST", { text }).then((ok) => {
                      if (ok) {
                        checkpointRef.current?.reset();
                      }
                    });
                  }}
                  className="flex gap-2"
                >
                  <input
                    name="text"
                    required
                    maxLength={200}
                    aria-label={t("checkpointPlaceholder")}
                    placeholder={t("checkpointPlaceholder")}
                    className={fieldClass}
                  />
                  <button type="submit" disabled={busy} className={buttonClass}>
                    {t("checkpointAdd")}
                  </button>
                </form>
              ) : null}
              <p className="text-xs text-muted-foreground">{t("checkpointsNote")}</p>
            </div>
          </details>

          <section aria-labelledby="task-files" className="flex flex-col gap-3">
            <h3 id="task-files" className="text-sm font-medium">
              {t("filesTitle")}
              {task.attachments.length > 0 ? (
                <span className="text-muted-foreground">
                  {" "}
                  {t("commentsCount", { count: task.attachments.length })}
                </span>
              ) : null}
            </h3>
            {task.attachments.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noFiles")}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {task.attachments.map((file) => (
                  <li
                    key={file.id}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border px-3 py-2 text-sm"
                  >
                    {/* A plain link: the API answers with "attachment", so the browser saves the file. */}
                    <a
                      href={`${base}/attachments/${file.id}`}
                      download={file.name}
                      className="font-medium break-all underline"
                    >
                      {file.name}
                    </a>
                    <span className="text-xs text-muted-foreground">
                      {t("fileMeta", {
                        size: formatBytes(file.byte_size),
                        author: file.uploader.name,
                        date: dateTime(file.created_at),
                      })}
                    </span>
                    {task.actions.attachment_delete && !locked ? (
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={t("fileDelete", { name: file.name })}
                        onClick={() => {
                          if (window.confirm(t("confirmFileDelete", { name: file.name }))) {
                            void run(`${base}/attachments/${file.id}`, "DELETE");
                          }
                        }}
                        className="ml-auto rounded px-2 text-muted-foreground hover:bg-muted"
                      >
                        ×
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
            {task.actions.attach && !locked ? (
              <form
                ref={fileRef}
                onSubmit={(event) => {
                  event.preventDefault();
                  const input = event.currentTarget.elements.namedItem("file");
                  const file = input instanceof HTMLInputElement ? input.files?.[0] : undefined;
                  if (!file || file.size === 0) {
                    setError("file_missing");
                    return;
                  }
                  if (file.size > MAX_FILE_BYTES) {
                    setError("file_too_large");
                    return;
                  }
                  setUploading(true);
                  setBusy(true);
                  setError(null);
                  void uploadFile<TaskDetail>(`${base}/attachments`, file)
                    .then((result) => {
                      if (result.ok) {
                        setTask(result.data);
                        fileRef.current?.reset();
                        onChanged();
                      } else {
                        setError(toError(result.code));
                      }
                    })
                    .finally(() => {
                      setUploading(false);
                      setBusy(false);
                    });
                }}
                className="flex flex-wrap items-center gap-2"
              >
                <input
                  type="file"
                  name="file"
                  accept={FILE_ACCEPT}
                  aria-label={t("fileChoose")}
                  className="min-w-0 flex-1 text-sm file:mr-3 file:h-9 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:text-sm"
                />
                <button type="submit" disabled={busy} className={buttonClass}>
                  {uploading ? t("fileUploading") : t("fileAttach")}
                </button>
              </form>
            ) : null}
            <p className="text-xs text-muted-foreground">{t("filesNote")}</p>
          </section>

          <section aria-labelledby="task-comments" className="flex flex-col gap-3">
            <h3 id="task-comments" className="text-sm font-medium">
              {t("commentsTitle")}
              {task.comments.length > 0 ? (
                <span className="text-muted-foreground">
                  {" "}
                  {t("commentsCount", { count: task.comments.length })}
                </span>
              ) : null}
            </h3>
            {task.comments.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noComments")}</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {task.comments.map((comment) => (
                  <li key={comment.id} className="rounded-md border border-border p-3 text-sm">
                    <div className="mb-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{comment.author.name}</span>
                      <span>{dateTime(comment.created_at)}</span>
                      {comment.edited_at ? <span>· {t("commentEdited")}</span> : null}
                      <span className="ml-auto flex gap-1">
                        {comment.is_own &&
                        task.actions.comment &&
                        !locked &&
                        editingComment !== comment.id ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => setEditingComment(comment.id)}
                            className="rounded px-2 underline hover:bg-muted"
                          >
                            {t("commentEdit")}
                          </button>
                        ) : null}
                        {task.actions.comment_delete && !locked ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              if (window.confirm(t("confirmCommentDelete"))) {
                                void run(`${base}/comments/${comment.id}`, "DELETE");
                              }
                            }}
                            className="rounded px-2 underline hover:bg-muted"
                          >
                            {t("commentDelete")}
                          </button>
                        ) : null}
                      </span>
                    </div>
                    {editingComment === comment.id ? (
                      <form
                        onSubmit={(event) => {
                          event.preventDefault();
                          const text = String(new FormData(event.currentTarget).get("text") ?? "");
                          void run(`${base}/comments/${comment.id}`, "PATCH", { text }).then(
                            (ok) => {
                              if (ok) {
                                setEditingComment(null);
                              }
                            },
                          );
                        }}
                        className="flex flex-col gap-2"
                      >
                        <textarea
                          name="text"
                          required
                          maxLength={5000}
                          rows={3}
                          defaultValue={comment.text}
                          aria-label={t("commentEditLabel")}
                          className={`${fieldClass} h-auto py-2`}
                        />
                        <div className="flex gap-2">
                          <button type="submit" disabled={busy} className={buttonClass}>
                            {t("save")}
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingComment(null)}
                            className={buttonClass}
                          >
                            {t("cancel")}
                          </button>
                        </div>
                      </form>
                    ) : (
                      <p className="break-words whitespace-pre-wrap">{comment.text}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {task.actions.comment && !locked ? (
              <form
                ref={commentRef}
                onSubmit={(event) => {
                  event.preventDefault();
                  const text = String(new FormData(event.currentTarget).get("text") ?? "");
                  void run(`${base}/comments`, "POST", { text }).then((ok) => {
                    if (ok) {
                      commentRef.current?.reset();
                    }
                  });
                }}
                className="flex flex-col gap-2"
              >
                <textarea
                  name="text"
                  required
                  maxLength={5000}
                  rows={2}
                  aria-label={t("commentPlaceholder")}
                  placeholder={t("commentPlaceholder")}
                  className={`${fieldClass} h-auto py-2`}
                />
                <button type="submit" disabled={busy} className={`${buttonClass} self-start`}>
                  {t("commentAdd")}
                </button>
              </form>
            ) : null}
            <p className="text-xs text-muted-foreground">{t("commentsNote")}</p>
          </section>

          <details className="rounded-md border border-border p-3">
            <summary className="cursor-pointer text-sm font-medium">{t("historyTitle")}</summary>
            <ul className="mt-3 flex flex-col gap-1 text-sm">
              {task.history.map((entry, index) => (
                <li key={index} className="flex flex-wrap gap-x-2">
                  <span className="text-muted-foreground">{dateTime(entry.occurred_at)}</span>
                  <span>{t(`history.${toHistoryKey(entry.action)}`)}</span>
                  {entry.actor_name ? (
                    <span className="text-muted-foreground">{entry.actor_name}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </Modal>
  );
}
