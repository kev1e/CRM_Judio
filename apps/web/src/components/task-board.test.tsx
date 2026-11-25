import type { Status, TaskCard, TaskDetail } from "@crm/contracts";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { TaskBoard } from "./task-board";

const fetchMock = vi.fn<typeof fetch>();

const statuses: Status[] = [
  {
    id: "todo",
    name: "Нужно сделать",
    category: "new",
    position: 10,
    next_status_ids: ["work", "done"],
  },
  {
    id: "work",
    name: "В работе",
    category: "active",
    position: 20,
    next_status_ids: ["todo", "done"],
  },
  { id: "done", name: "Готово", category: "completed", position: 30, next_status_ids: [] },
];

function card(overrides: Partial<TaskCard> = {}): TaskCard {
  return {
    id: "t-1",
    title: "Подготовить предложение",
    task_type: "task",
    priority: "high",
    status_id: "todo",
    due_at: "2020-01-05T09:00:00Z",
    department: { id: "d", name: "Продажи" },
    assignee: { id: "u", name: "Анна Петрова" },
    checkpoints_done: 1,
    checkpoints_total: 3,
    is_completed: false,
    is_archived: false,
    is_deleted: false,
    version: 1,
    ...overrides,
  };
}

function detail(overrides: Partial<TaskDetail> = {}): TaskDetail {
  return {
    ...card(),
    description: "Нужно до пятницы",
    author: { id: "a", name: "Ольга Смирнова" },
    created_at: "2026-11-25T10:00:00Z",
    completed_at: null,
    checkpoints: [{ id: "c-1", text: "Собрать данные", is_done: true }],
    comments: [],
    history: [
      { occurred_at: "2026-11-25T10:00:00Z", action: "task.created", actor_name: "Ольга Смирнова" },
    ],
    actions: {
      edit: true,
      status: true,
      deadline: true,
      checkpoints_use: true,
      checkpoints_manage: false,
      comment: true,
      priority: false,
      reassign: false,
      archive: false,
      delete: false,
    },
    ...overrides,
  };
}

function column(name: string) {
  return within(screen.getByRole("region", { name: new RegExp(`^${name}`) }));
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TaskBoard", () => {
  it("shows a column per status and the card with its six facts", () => {
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card()]} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Мои задачи");
    const todo = column("Нужно сделать");
    const button = todo.getByRole("button", { name: /Подготовить предложение/ });
    expect(button).toHaveTextContent("Высокий");
    expect(button).toHaveTextContent("просрочено");
    expect(button).toHaveTextContent("1 из 3");
    expect(button).toHaveTextContent("Продажи");
    expect(button).toHaveTextContent("Анна Петрова");
    expect(column("В работе").getByText("Пусто")).toBeInTheDocument();
    expect(column("Готово").getByText("Перетащите сюда, чтобы завершить")).toBeInTheDocument();
  });

  it("lists archived tasks without columns and without creating", () => {
    renderWithIntl(
      <TaskBoard
        view="archive"
        statuses={statuses}
        initialCards={[card({ is_archived: true, is_completed: true, status_id: "done" })]}
      />,
    );

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Архив");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Новая задача" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Подготовить предложение/ })).toHaveTextContent(
      "завершена",
    );
  });

  it("opens the task read-only, puts it into the address and edits only in edit mode", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(Response.json(detail()));
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card()]} />);

    await user.click(screen.getByRole("button", { name: /Подготовить предложение/ }));

    const dialog = within(await screen.findByRole("dialog", { name: "Подготовить предложение" }));
    expect(window.location.search).toBe("?task=t-1");
    expect(dialog.getByText("Нужно до пятницы")).toBeInTheDocument();
    expect(dialog.queryByLabelText("Название")).not.toBeInTheDocument();
    expect(dialog.getByText("Отметка всех пунктов не меняет статус задачи.")).toBeInTheDocument();
    // The assignee may not archive or delete: those controls are absent.
    expect(dialog.queryByRole("button", { name: "В архив" })).not.toBeInTheDocument();
    expect(dialog.queryByRole("button", { name: "В корзину" })).not.toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Редактировать" }));

    expect(dialog.getByLabelText("Название")).toHaveValue("Подготовить предложение");
    expect(dialog.getByLabelText("Приоритет")).toBeDisabled(); // the manager's field
    expect(dialog.getByLabelText("Исполнитель")).toBeDisabled();
    expect(dialog.getByLabelText("Срок")).toBeEnabled();
  });

  it("saves an edit with the version it was made on", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(Response.json(detail()))
      .mockResolvedValueOnce(Response.json(detail({ title: "Новое название", version: 2 })))
      .mockResolvedValue(
        Response.json({ results: [card({ title: "Новое название", version: 2 })] }),
      );
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card()]} />);
    await user.click(screen.getByRole("button", { name: /Подготовить предложение/ }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Редактировать" }));

    await user.clear(dialog.getByLabelText("Название"));
    await user.type(dialog.getByLabelText("Название"), "Новое название");
    await user.click(dialog.getByRole("button", { name: "Сохранить" }));

    expect(await dialog.findByRole("heading", { name: "Новое название" })).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ version: 1, title: "Новое название" });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Новое название/ })).toBeInTheDocument(),
    );
  });

  it("moves the task from the keyboard through the status list and reports completion", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(Response.json(detail()))
      .mockResolvedValueOnce(
        Response.json(
          detail({ status_id: "done", is_completed: true, is_archived: true, version: 2 }),
        ),
      )
      .mockResolvedValue(Response.json({ results: [] }));
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card()]} />);
    await user.click(screen.getByRole("button", { name: /Подготовить предложение/ }));
    const dialog = within(await screen.findByRole("dialog"));

    await user.selectOptions(dialog.getByRole("combobox", { name: "Статус" }), "Готово");

    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1/transitions");
    expect(JSON.parse(String(init?.body))).toEqual({ status_id: "done", version: 1 });
    // Archived now: the status cannot be changed and the window says why.
    expect(await dialog.findByText(/задача в архиве/)).toBeInTheDocument();
    await waitFor(() =>
      expect(column("Нужно сделать").queryByRole("button")).not.toBeInTheDocument(),
    );
  });

  it("ticks a checkpoint without touching the status", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(
        Response.json(
          detail({ checkpoints: [{ id: "c-1", text: "Собрать данные", is_done: false }] }),
        ),
      )
      .mockResolvedValueOnce(Response.json(detail()))
      .mockResolvedValue(Response.json({ results: [card()] }));
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card()]} />);
    await user.click(screen.getByRole("button", { name: /Подготовить предложение/ }));
    const dialog = within(await screen.findByRole("dialog"));

    await user.click(dialog.getByRole("checkbox", { name: "Собрать данные" }));

    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1/checkpoints/c-1");
    expect(JSON.parse(String(init?.body))).toEqual({ is_done: true });
    expect(await dialog.findByRole("checkbox", { name: "Собрать данные" })).toBeChecked();
    expect(dialog.getByRole("combobox", { name: "Статус" })).toHaveValue("todo");
  });

  const mine = {
    id: "m-1",
    author: { id: "u-anna", name: "Анна Петрова" },
    text: "Клиент ждёт ответа",
    created_at: "2026-11-25T11:00:00Z",
    edited_at: null,
    is_own: true,
  };
  const theirs = {
    ...mine,
    id: "m-2",
    author: { id: "u-olga", name: "Ольга Смирнова" },
    text: "Согласовано",
    is_own: false,
  };

  async function openTask(first: TaskDetail) {
    fetchMock.mockResolvedValueOnce(Response.json(first));
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card()]} />);
    await userEvent.click(screen.getByRole("button", { name: /Подготовить предложение/ }));
    return within(await screen.findByRole("dialog"));
  }

  it("sends a comment and shows it", async () => {
    const user = userEvent.setup();
    const dialog = await openTask(detail());
    expect(dialog.getByText("Комментариев пока нет.")).toBeInTheDocument();
    fetchMock.mockResolvedValue(Response.json(detail({ comments: [mine] })));

    await user.type(dialog.getByRole("textbox", { name: "Новый комментарий" }), mine.text);
    await user.click(dialog.getByRole("button", { name: "Отправить" }));

    expect(await dialog.findByText(mine.text)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1/comments");
    expect(JSON.parse(String(init?.body))).toEqual({ text: mine.text });
    expect(dialog.getByRole("textbox", { name: "Новый комментарий" })).toHaveValue("");
  });

  it("lets the viewer edit only their own comment", async () => {
    const user = userEvent.setup();
    const dialog = await openTask(detail({ comments: [mine, theirs] }));
    fetchMock.mockResolvedValue(
      Response.json(
        detail({
          comments: [{ ...mine, text: "Исправлено", edited_at: "2026-11-25T12:00:00Z" }, theirs],
        }),
      ),
    );

    expect(dialog.getAllByRole("button", { name: "Изменить" })).toHaveLength(1);
    await user.click(dialog.getByRole("button", { name: "Изменить" }));
    const field = dialog.getByRole("textbox", { name: "Текст комментария" });
    expect(field).toHaveValue(mine.text);
    await user.clear(field);
    await user.type(field, "Исправлено");
    await user.click(
      within(field.closest("form") as HTMLElement).getByRole("button", { name: "Сохранить" }),
    );

    expect(await dialog.findByText("Исправлено")).toBeInTheDocument();
    expect(dialog.getByText("· изменён")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1/comments/m-1");
    expect(init?.method).toBe("PATCH");
  });

  it("shows comments read-only to somebody who may not comment", async () => {
    const dialog = await openTask(
      detail({ comments: [mine], actions: { ...detail().actions, comment: false } }),
    );

    expect(dialog.getByText(mine.text)).toBeInTheDocument();
    expect(dialog.queryByRole("textbox", { name: "Новый комментарий" })).toBeNull();
    expect(dialog.queryByRole("button", { name: "Изменить" })).toBeNull();
  });

  it("explains a task the viewer cannot open", async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json({ error: { code: "task_not_found", message: "x" } }, { status: 404 }),
    );
    renderWithIntl(
      <TaskBoard view="mine" statuses={statuses} initialCards={[]} initialTaskId="t-404" />,
    );

    expect(
      await screen.findByRole("heading", {
        name: "Задача не найдена или у вас нет к ней доступа.",
      }),
    ).toBeInTheDocument();
  });

  it("creates a task and tells the author when it is not theirs to see", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(Response.json({ results: [{ id: "d", name: "Продажи" }] }))
      .mockResolvedValueOnce(Response.json({ results: [{ id: "u", name: "Анна Петрова" }] }))
      .mockResolvedValueOnce(
        Response.json({ id: "t-2", title: "Счёт для клиента", task: null }, { status: 201 }),
      )
      .mockResolvedValue(Response.json({ results: [] }));
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[]} />);

    await user.click(screen.getByRole("button", { name: "Новая задача" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Новая задача" }));
    await user.type(dialog.getByLabelText("Название"), "Счёт для клиента");
    await user.selectOptions(await dialog.findByLabelText("Исполнитель"), "Анна Петрова");
    await user.click(dialog.getByRole("button", { name: "Создать задачу" }));

    expect(
      await screen.findByText(/Задача «Счёт для клиента» создана и передана исполнителю\./),
    ).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[2] ?? [];
    expect(url).toBe("/api/v1/tasks");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      title: "Счёт для клиента",
      department_id: "d",
      assignee_id: "u",
      priority: "normal",
      task_type: "task",
      due_at: null,
    });
  });
});
