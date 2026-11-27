"use client";

import {
  API_PATHS,
  type Status,
  type TaskCard,
  type TaskCreated,
  type TaskList,
} from "@crm/contracts";
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useState } from "react";

import { NewRequestDialog } from "@/components/new-request-dialog";
import { NewTaskDialog } from "@/components/new-task-dialog";
import { TaskCardView } from "@/components/task-card";
import { TaskModal } from "@/components/task-modal";
import { callApi } from "@/lib/api-client";
import { type BoardView, canMove, groupCards, groupKey, moveCard } from "@/lib/tasks";

const BOARD_ERRORS = [
  "permission_denied",
  "transition_not_allowed",
  "task_changed",
  "task_not_found",
  "task_archived",
  "task_deleted",
  "unavailable",
] as const;
type BoardError = (typeof BOARD_ERRORS)[number];

type Notice = { kind: "completed" } | { kind: "createdForOther"; title: string };

const columnTone: Record<Status["category"], string> = {
  new: "border-t-warning",
  active: "border-t-ring",
  completed: "border-t-success",
  cancelled: "border-t-border",
};

function Draggable({
  id,
  disabled,
  children,
}: {
  id: string;
  disabled: boolean;
  children: ReactNode;
}) {
  const { setNodeRef, listeners, transform, isDragging } = useDraggable({ id, disabled });
  return (
    <div
      ref={setNodeRef}
      // Pointer listeners only: the card inside stays the single keyboard stop,
      // and the keyboard way to move a task is the status list in its window.
      {...listeners}
      style={
        transform
          ? {
              transform: `translate(${transform.x}px, ${transform.y}px)`,
              zIndex: 10,
              position: "relative",
            }
          : undefined
      }
      className={isDragging ? "opacity-80" : undefined}
    >
      {children}
    </div>
  );
}

function Column({
  status,
  count,
  highlight,
  children,
}: {
  status: Status;
  count: number;
  highlight: boolean;
  children: ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status.id });
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={`column-${status.id}`}
      className={`flex w-72 shrink-0 flex-col gap-2 rounded-lg border border-t-4 border-border bg-surface p-2 ${columnTone[status.category]} ${isOver && highlight ? "outline-2 outline-ring" : ""}`}
    >
      <h2
        id={`column-${status.id}`}
        className="flex items-center justify-between px-1 text-sm font-semibold"
      >
        {status.name}
        <span className="font-normal text-muted-foreground">{count}</span>
      </h2>
      {children}
    </section>
  );
}

export function TaskBoard({
  view,
  statuses,
  initialCards,
  initialTaskId,
  canCreate = false,
}: {
  /** Whether to offer "Новая задача" (D037: managers). The API checks again. */
  canCreate?: boolean;
  view: BoardView;
  statuses: Status[];
  initialCards: TaskCard[];
  /** A task to open at once (from a link). */
  initialTaskId?: string;
}) {
  const t = useTranslations("board");
  const [cards, setCards] = useState(initialCards);
  const [openId, setOpenId] = useState<string | null>(initialTaskId ?? null);
  const [creating, setCreating] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<BoardError | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [draggingFrom, setDraggingFrom] = useState<string | null>(null);
  const [now] = useState(() => new Date());
  // A small movement starts a drag; a plain click still opens the card.
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const isBoard = view === "mine" || view === "all";
  // Groups of the "in work" statuses the viewer has unfolded (project or department).
  const [unfolded, setUnfolded] = useState<ReadonlySet<string>>(new Set());

  function toggleGroup(key: string) {
    setUnfolded((current) => {
      const next = new Set(current);
      if (!next.delete(key)) {
        next.add(key);
      }
      return next;
    });
  }

  // The open task is part of the address, so it can be bookmarked and sent as a link.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (openId) {
      url.searchParams.set("task", openId);
    } else {
      url.searchParams.delete("task");
    }
    window.history.replaceState(null, "", url);
  }, [openId]);

  async function reload() {
    const result = await callApi<TaskList>(`${API_PATHS.tasks}?view=${view}`, { method: "GET" });
    if (result.ok) {
      setCards(result.data.results);
    }
  }

  async function move(taskId: string, toStatusId: string) {
    const card = cards.find((item) => item.id === taskId);
    if (!card) {
      return;
    }
    if (!canMove(statuses, card.status_id, toStatusId)) {
      if (card.status_id !== toStatusId) {
        setError("transition_not_allowed");
      }
      return;
    }
    const before = cards;
    setError(null);
    setCards(moveCard(cards, statuses, taskId, toStatusId)); // optimistic
    const result = await callApi(`${API_PATHS.tasks}/${taskId}/transitions`, {
      method: "POST",
      body: { status_id: toStatusId, version: card.version },
    });
    if (!result.ok) {
      setCards(before); // the server refused: put the card back
      setError(
        (BOARD_ERRORS as readonly string[]).includes(result.code)
          ? (result.code as BoardError)
          : "unavailable",
      );
      return;
    }
    const target = statuses.find((status) => status.id === toStatusId);
    if (target?.category === "completed") {
      setNotice({ kind: "completed" });
    }
    if (target?.category === "active") {
      // The moved card must not seem to vanish into a folded group.
      setUnfolded((current) => new Set(current).add(`${toStatusId}:${groupKey(card)}`));
    }
    await reload();
  }

  function onDragEnd(event: DragEndEvent) {
    setDraggingFrom(null);
    if (event.over) {
      void move(String(event.active.id), String(event.over.id));
    }
  }

  function onCreated(created: TaskCreated) {
    setCreating(false);
    setRequesting(false);
    setNotice(created.task ? null : { kind: "createdForOther", title: created.title });
    void reload();
  }

  return (
    <div className="flex min-h-dvh flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t(`titles.${view}`)}</h1>
        {isBoard && canCreate ? (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setRequesting(true)}
              className="h-10 rounded-md border border-border px-4 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {t("newRequest")}
            </button>
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {t("newTask")}
            </button>
          </div>
        ) : null}
      </header>

      {error ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="rounded-md border border-border bg-muted px-3 py-2 text-sm">
          {notice.kind === "completed" ? (
            <>
              {t("completedNotice")}{" "}
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- a full load re-reads the archive */}
              <a href="/?view=archive" className="underline underline-offset-4">
                {t("openArchive")}
              </a>
            </>
          ) : (
            t("createdForOther", { title: notice.title })
          )}
        </p>
      ) : null}

      {isBoard ? (
        statuses.length === 0 ? (
          <p className="text-muted-foreground">{t("noStatuses")}</p>
        ) : (
          <>
            {cards.length === 0 ? (
              <p className="text-muted-foreground">
                {t(canCreate ? "emptyBoard" : "emptyBoardReadOnly")}
              </p>
            ) : null}
            <DndContext
              sensors={sensors}
              onDragStart={(event) =>
                setDraggingFrom(
                  cards.find((card) => card.id === String(event.active.id))?.status_id ?? null,
                )
              }
              onDragCancel={() => setDraggingFrom(null)}
              onDragEnd={onDragEnd}
            >
              <div className="flex flex-1 items-start gap-3 overflow-x-auto pb-2">
                {statuses.map((status) => {
                  const inColumn = cards.filter((card) => card.status_id === status.id);
                  const allowed =
                    draggingFrom !== null && canMove(statuses, draggingFrom, status.id);
                  return (
                    <Column
                      key={status.id}
                      status={status}
                      count={inColumn.length}
                      highlight={allowed}
                    >
                      {status.category === "active"
                        ? // Work in progress is shown by project: a folded list of
                          // the projects (and the department's own tasks) that
                          // have something in work; a click unfolds the tasks.
                          groupCards(inColumn).map((group) => {
                            const key = `${status.id}:${group.key}`;
                            const open = unfolded.has(key);
                            return (
                              <section
                                key={group.key}
                                className="flex flex-col gap-2 rounded-md bg-muted/40 p-1.5"
                              >
                                <h3>
                                  <button
                                    type="button"
                                    aria-expanded={open}
                                    onClick={() => toggleGroup(key)}
                                    className="flex min-h-9 w-full items-center justify-between gap-2 rounded px-1 text-left text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                                  >
                                    <span className="break-words">
                                      <span aria-hidden="true" className="text-muted-foreground">
                                        {open ? "▾" : "▸"}{" "}
                                      </span>
                                      <span className="font-normal text-muted-foreground">
                                        {t(group.isProject ? "projectPrefix" : "departmentPrefix")}
                                      </span>{" "}
                                      {group.name}
                                    </span>
                                    <span className="font-normal text-muted-foreground">
                                      {group.cards.length}
                                    </span>
                                  </button>
                                </h3>
                                {open
                                  ? group.cards.map((card) => (
                                      <Draggable key={card.id} id={card.id} disabled={false}>
                                        <TaskCardView card={card} onOpen={setOpenId} now={now} />
                                      </Draggable>
                                    ))
                                  : null}
                              </section>
                            );
                          })
                        : inColumn.map((card) => (
                            <Draggable key={card.id} id={card.id} disabled={false}>
                              <TaskCardView card={card} onOpen={setOpenId} now={now} />
                            </Draggable>
                          ))}
                      {inColumn.length === 0 ? (
                        <p className="px-1 py-3 text-xs text-muted-foreground">
                          {status.category === "completed" ? t("dropToComplete") : t("emptyColumn")}
                        </p>
                      ) : null}
                    </Column>
                  );
                })}
              </div>
            </DndContext>
            <p className="text-xs text-muted-foreground">{t("dragHint")}</p>
          </>
        )
      ) : cards.length === 0 ? (
        <p className="text-muted-foreground">{t("emptyList")}</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {cards.map((card) => (
            <li key={card.id}>
              <TaskCardView card={card} onOpen={setOpenId} now={now} />
            </li>
          ))}
        </ul>
      )}

      {openId ? (
        <TaskModal
          key={openId}
          taskId={openId}
          statuses={statuses}
          onClose={() => setOpenId(null)}
          onChanged={() => void reload()}
        />
      ) : null}
      {creating ? <NewTaskDialog onClose={() => setCreating(false)} onCreated={onCreated} /> : null}
      {requesting ? (
        <NewRequestDialog onClose={() => setRequesting(false)} onCreated={onCreated} />
      ) : null}
    </div>
  );
}
