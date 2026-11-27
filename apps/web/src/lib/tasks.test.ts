import type { Status, TaskCard } from "@crm/contracts";
import { describe, expect, it } from "vitest";

import {
  canMove,
  fromLocalInput,
  groupCards,
  groupKey,
  isOverdue,
  moveCard,
  toBoardView,
  toLocalInput,
} from "./tasks";

const statuses: Status[] = [
  {
    id: "todo",
    name: "Нужно сделать",
    category: "new",
    position: 10,
    next_status_ids: ["work", "done"],
    show_project: true,
    group_by_project: false,
  },
  {
    id: "work",
    name: "В работе",
    category: "active",
    position: 20,
    next_status_ids: ["todo", "done"],
    show_project: true,
    group_by_project: true,
  },
  {
    id: "done",
    name: "Готово",
    category: "completed",
    position: 30,
    next_status_ids: [],
    show_project: true,
    group_by_project: false,
  },
];

function card(id: string, statusId: string): TaskCard {
  return {
    id,
    title: id,
    task_type: "task",
    priority: "normal",
    status_id: statusId,
    due_at: null,
    department: { id: "d", name: "Продажи" },
    project: null,
    assignee: { id: "u", name: "Анна" },
    checkpoints_done: 0,
    checkpoints_total: 0,
    is_completed: false,
    is_archived: false,
    is_deleted: false,
    version: 1,
  };
}

describe("canMove", () => {
  it("follows the configured moves only", () => {
    expect(canMove(statuses, "todo", "work")).toBe(true);
    expect(canMove(statuses, "done", "todo")).toBe(false);
    expect(canMove(statuses, "todo", "todo")).toBe(false);
    expect(canMove(statuses, "unknown", "todo")).toBe(false);
  });
});

describe("moveCard", () => {
  it("moves the card to the new column", () => {
    const moved = moveCard([card("a", "todo"), card("b", "todo")], statuses, "a", "work");

    expect(moved.map((item) => [item.id, item.status_id])).toEqual([
      ["a", "work"],
      ["b", "todo"],
    ]);
  });

  it("removes a completed task from the board: it goes to the archive", () => {
    const moved = moveCard([card("a", "work"), card("b", "todo")], statuses, "a", "done");

    expect(moved.map((item) => item.id)).toEqual(["b"]);
  });
});

describe("isOverdue", () => {
  const now = new Date("2026-11-25T12:00:00Z");

  it("is true only for an unfinished task past its deadline", () => {
    expect(isOverdue({ due_at: "2026-11-25T11:59:00Z", is_completed: false }, now)).toBe(true);
    expect(isOverdue({ due_at: "2026-11-25T12:01:00Z", is_completed: false }, now)).toBe(false);
    expect(isOverdue({ due_at: "2026-11-20T00:00:00Z", is_completed: true }, now)).toBe(false);
    expect(isOverdue({ due_at: null, is_completed: false }, now)).toBe(false);
  });
});

describe("toBoardView", () => {
  it("accepts known views and falls back to the personal board", () => {
    expect(toBoardView("archive")).toBe("archive");
    expect(toBoardView("everything")).toBe("mine");
    expect(toBoardView(undefined)).toBe("mine");
  });
});

describe("local date input", () => {
  it("round-trips an instant through the browser's time zone", () => {
    const iso = "2026-12-01T09:30:00.000Z";

    expect(fromLocalInput(toLocalInput(iso))).toBe(iso);
    expect(toLocalInput(null)).toBe("");
    expect(fromLocalInput("")).toBeNull();
  });
});

describe("groupCards", () => {
  const sales = { id: "d1", name: "Продажи" };
  const support = { id: "d2", name: "Поддержка" };
  const launch = { id: "p1", name: "Запуск" };
  const card = (id: string, department: typeof sales, project: typeof launch | null = null) => ({
    id,
    department,
    project,
  });

  it("puts departments' own tasks first, then projects, each by name", () => {
    const groups = groupCards([
      card("1", sales, launch),
      card("2", sales),
      card("3", support),
      card("4", support, launch),
      card("5", sales, { id: "p0", name: "Аудит" }),
    ]);

    expect(
      groups.map((group) => [group.name, group.isProject, group.cards.map((c) => c.id)]),
    ).toEqual([
      ["Поддержка", false, ["3"]],
      ["Продажи", false, ["2"]],
      ["Аудит", true, ["5"]],
      // One project gathers its tasks from every department.
      ["Запуск", true, ["1", "4"]],
    ]);
  });

  it("tells a project from a department with the same identifier", () => {
    expect(groupKey(card("1", sales))).toBe("department:d1");
    expect(groupKey(card("2", sales, { id: "d1", name: "X" }))).toBe("project:d1");
    expect(groupCards([])).toEqual([]);
  });
});
