import type { Status, TaskCard } from "@crm/contracts";

export type BoardView = "mine" | "all" | "archive" | "trash";
export const BOARD_VIEWS: readonly BoardView[] = ["mine", "all", "archive", "trash"];

export function toBoardView(value: string | undefined): BoardView {
  return (BOARD_VIEWS as readonly string[]).includes(value ?? "") ? (value as BoardView) : "mine";
}

/** Whether the board lets a task go from one status to another (the server decides in the end). */
export function canMove(statuses: readonly Status[], fromId: string, toId: string): boolean {
  if (fromId === toId) {
    return false;
  }
  return statuses.find((status) => status.id === fromId)?.next_status_ids.includes(toId) ?? false;
}

/** The board after a task was moved; a task that entered a completed status leaves the board. */
export function moveCard(
  cards: readonly TaskCard[],
  statuses: readonly Status[],
  taskId: string,
  toStatusId: string,
): TaskCard[] {
  const target = statuses.find((status) => status.id === toStatusId);
  if (target?.category === "completed") {
    return cards.filter((card) => card.id !== taskId);
  }
  return cards.map((card) => (card.id === taskId ? { ...card, status_id: toStatusId } : card));
}

export function isOverdue(card: Pick<TaskCard, "due_at" | "is_completed">, now: Date): boolean {
  return (
    !card.is_completed && card.due_at !== null && new Date(card.due_at).getTime() < now.getTime()
  );
}

/** `<input type="datetime-local">` value for an ISO instant, in the browser's time zone. */
export function toLocalInput(iso: string | null): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fromLocalInput(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

type Grouped = {
  department: { id: string; name: string };
  project: { id: string; name: string } | null;
};

export type CardGroup<C> = { key: string; name: string; isProject: boolean; cards: C[] };

/** Which sub-column of a status a card belongs to: its project, or — for a
 *  task without a project — its department. */
export function groupKey(card: Grouped): string {
  return card.project ? `project:${card.project.id}` : `department:${card.department.id}`;
}

/**
 * Sub-columns for a set of cards: tasks without a project by department first,
 * then one per project, each by name. Built only from the given cards, so it
 * shows no project and no department the viewer has no task in.
 */
export function groupCards<C extends Grouped>(cards: readonly C[]): CardGroup<C>[] {
  const groups = new Map<string, CardGroup<C>>();
  for (const card of cards) {
    const key = groupKey(card);
    const group = groups.get(key) ?? {
      key,
      name: (card.project ?? card.department).name,
      isProject: card.project !== null,
      cards: [],
    };
    group.cards.push(card);
    groups.set(key, group);
  }
  return [...groups.values()].sort(
    (a, b) => Number(a.isProject) - Number(b.isProject) || a.name.localeCompare(b.name, "ru"),
  );
}
