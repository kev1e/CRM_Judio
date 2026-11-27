"use client";

import type { TaskCard as Card } from "@crm/contracts";
import { useFormatter, useTranslations } from "next-intl";

import { isOverdue } from "@/lib/tasks";

const priorityClass: Record<Card["priority"], string> = {
  low: "border-border text-muted-foreground",
  normal: "border-border text-foreground",
  high: "border-warning text-warning",
  urgent: "border-danger text-danger",
};

/**
 * The card on the board shows exactly: title, priority, deadline, checkpoint
 * progress, department and assignee (D005). It is a button: opening the task is
 * the only action on it.
 */
export function TaskCardView({
  card,
  onOpen,
  now,
  showProject = true,
}: {
  card: Card;
  onOpen: (taskId: string) => void;
  now: Date;
  /** False in a column whose status is set not to show projects. */
  showProject?: boolean;
}) {
  const t = useTranslations("board");
  const format = useFormatter();
  const overdue = isOverdue(card, now);
  const due = card.due_at
    ? format.dateTime(new Date(card.due_at), { day: "numeric", month: "short" })
    : null;

  return (
    <button
      type="button"
      onClick={() => onOpen(card.id)}
      className="flex w-full flex-col gap-2 rounded-md border border-border bg-card p-3 text-left text-sm shadow-xs hover:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <span className="font-medium break-words">{card.title}</span>
      <span className="flex flex-wrap items-center gap-1.5 text-xs">
        {card.task_type === "request" ? (
          <span className="rounded border border-border px-1.5 py-0.5 text-muted-foreground">
            {t("request")}
          </span>
        ) : null}
        {card.priority === "normal" ? null : (
          <span className={`rounded border px-1.5 py-0.5 ${priorityClass[card.priority]}`}>
            {t(`priority.${card.priority}`)}
          </span>
        )}
        {due ? (
          <span
            className={`rounded border px-1.5 py-0.5 ${overdue ? "border-danger text-danger" : "border-border text-muted-foreground"}`}
          >
            {overdue ? t("overdue", { date: due }) : t("due", { date: due })}
          </span>
        ) : null}
        {card.is_deleted ? (
          <span className="text-muted-foreground">{t("deleted")}</span>
        ) : card.is_archived ? (
          <span className="text-muted-foreground">
            {card.is_completed ? t("archivedCompleted") : t("archivedManual")}
          </span>
        ) : null}
      </span>
      {card.checkpoints_total > 0 ? (
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <span
            role="progressbar"
            aria-label={t("checkpointsLabel", {
              done: card.checkpoints_done,
              total: card.checkpoints_total,
            })}
            aria-valuemin={0}
            aria-valuemax={card.checkpoints_total}
            aria-valuenow={card.checkpoints_done}
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
          >
            <span
              className="block h-full rounded-full bg-success"
              style={{ width: `${(card.checkpoints_done / card.checkpoints_total) * 100}%` }}
            />
          </span>
          {t("checkpoints", { done: card.checkpoints_done, total: card.checkpoints_total })}
        </span>
      ) : null}
      <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="truncate">
          {card.project && showProject
            ? `${card.project.name} · ${card.department.name}`
            : card.department.name}
        </span>
        <span className="truncate">{card.assignee.name}</span>
      </span>
    </button>
  );
}
