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
