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

function card(overrides: Partial<TaskCard> = {}): TaskCard {
  return {
    id: "t-1",
    title: "Подготовить предложение",
    task_type: "task",
    priority: "high",
    status_id: "todo",
    due_at: "2020-01-05T09:00:00Z",
    department: { id: "d", name: "Продажи" },
    project: null,
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
    attachments: [],
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
      attach: true,
      attachment_delete: false,
      comment: true,
      comment_delete: false,
      priority: false,
      project: false,
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
        Response.json(detail({ status_id: "done", is_completed: true, version: 2 })),
      )
      .mockResolvedValue(
        Response.json({ results: [card({ status_id: "done", is_completed: true, version: 2 })] }),
      );
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card()]} />);
    await user.click(screen.getByRole("button", { name: /Подготовить предложение/ }));
    const dialog = within(await screen.findByRole("dialog"));

    await user.selectOptions(dialog.getByRole("combobox", { name: "Статус" }), "Готово");

    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1/transitions");
    expect(JSON.parse(String(init?.body))).toEqual({ status_id: "done", version: 1 });
    // Completed: the status cannot be changed and the window says why.
    expect(await dialog.findByText(/задача завершена; вернуть её в работу/)).toBeInTheDocument();
    // The task did not leave the board: it lies in the column of completed tasks.
    await waitFor(() =>
      expect(
        column("Готово").getByRole("button", { name: /Подготовить предложение/ }),
      ).toBeInTheDocument(),
    );
    expect(column("Нужно сделать").queryByRole("button")).not.toBeInTheDocument();
  });

  it("lets a manager return a completed task to work or archive it at once", async () => {
    const user = userEvent.setup();
    const completed = detail({ status_id: "done", is_completed: true });
    const manager = { ...completed, actions: { ...completed.actions, archive: true } };
    fetchMock
      .mockResolvedValueOnce(Response.json(manager))
      .mockResolvedValueOnce(Response.json(detail()))
      .mockResolvedValue(Response.json({ results: [card()] }));
    renderWithIntl(
      <TaskBoard
        view="all"
        statuses={statuses}
        initialCards={[card({ status_id: "done", is_completed: true })]}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Подготовить предложение/ }));
    const dialog = within(await screen.findByRole("dialog"));

    // Read-only while completed; both ways out are offered.
    expect(dialog.queryByRole("button", { name: "Редактировать" })).not.toBeInTheDocument();
    expect(dialog.getByRole("button", { name: "В архив" })).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Вернуть в работу" }));

    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/tasks/t-1/reopen");
    await waitFor(() =>
      expect(dialog.queryByRole("button", { name: "Вернуть в работу" })).not.toBeInTheDocument(),
    );
  });

  it("offers a completed task's reader no way to reopen it", async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json(detail({ status_id: "done", is_completed: true })),
    );
    renderWithIntl(
      <TaskBoard
        view="mine"
        statuses={statuses}
        initialCards={[card({ status_id: "done", is_completed: true })]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Подготовить предложение/ }));
    const dialog = within(await screen.findByRole("dialog"));

    expect(dialog.queryByRole("button", { name: "Вернуть в работу" })).not.toBeInTheDocument();
    expect(dialog.queryByRole("button", { name: "В архив" })).not.toBeInTheDocument();
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

  const contract = {
    id: "f-1",
    name: "Договор.pdf",
    byte_size: 2 * 1024 * 1024,
    content_type: "application/pdf",
    uploader: { id: "u-anna", name: "Анна Петрова" },
    created_at: "2026-11-25T11:00:00Z",
  };

  it("lists files as download links and shows who attached them", async () => {
    const dialog = await openTask(detail({ comments: [], attachments: [contract] }));

    const link = dialog.getByRole("link", { name: "Договор.pdf" });
    expect(link).toHaveAttribute("href", "/api/v1/tasks/t-1/attachments/f-1");
    expect(link).toHaveAttribute("download");
    expect(dialog.getByText(/2,0 МБ · Анна Петрова/)).toBeInTheDocument();
    expect(dialog.queryByRole("button", { name: /Убрать файл/ })).toBeNull();
  });

  it("uploads a chosen file as multipart and shows it", async () => {
    const user = userEvent.setup();
    const dialog = await openTask(detail());
    fetchMock.mockResolvedValue(Response.json(detail({ attachments: [contract] })));

    const file = new File(["%PDF-1.7"], "Договор.pdf", { type: "application/pdf" });
    await user.upload(dialog.getByLabelText("Выберите файл"), file);
    await user.click(dialog.getByRole("button", { name: "Прикрепить" }));

    expect(await dialog.findByRole("link", { name: "Договор.pdf" })).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1/attachments");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
    // No JSON content type: the browser must write the multipart boundary itself.
    expect(new Headers(init?.headers).get("content-type")).toBeNull();
  });

  it("explains why a file was refused", async () => {
    const user = userEvent.setup();
    const dialog = await openTask(detail());
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "file_content_mismatch", message: "x" } }, { status: 400 }),
    );

    await user.upload(
      dialog.getByLabelText("Выберите файл"),
      new File(["MZ"], "счёт.pdf", { type: "application/pdf" }),
    );
    await user.click(dialog.getByRole("button", { name: "Прикрепить" }));

    expect(await dialog.findByRole("alert")).toHaveTextContent(
      "Содержимое файла не соответствует его расширению",
    );
    expect(dialog.getByText("Файлов пока нет.")).toBeInTheDocument();
  });

  it("lets a manager remove a file and hides the upload form from a reader", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const dialog = await openTask(
      detail({
        attachments: [contract],
        actions: { ...detail().actions, attach: false, attachment_delete: true },
      }),
    );
    fetchMock.mockResolvedValue(Response.json(detail()));

    expect(dialog.queryByLabelText("Выберите файл")).toBeNull();
    await user.click(dialog.getByRole("button", { name: "Убрать файл: Договор.pdf" }));

    expect(await dialog.findByText("Файлов пока нет.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1/attachments/f-1");
    expect(init?.method).toBe("DELETE");
    confirm.mockRestore();
  });

  it("offers a new task only to somebody who may create one", () => {
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[]} />);

    expect(screen.queryByRole("button", { name: "Новая задача" })).toBeNull();
    expect(screen.getByText(/Задачи ставит руководитель отдела/)).toBeInTheDocument();
  });

  it("lets a manager delete a comment after a confirmation", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const dialog = await openTask(
      detail({ comments: [theirs], actions: { ...detail().actions, comment_delete: true } }),
    );
    fetchMock.mockResolvedValue(Response.json(detail()));

    await user.click(dialog.getByRole("button", { name: "Удалить" }));

    expect(confirm).toHaveBeenCalled();
    expect(await dialog.findByText("Комментариев пока нет.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe("/api/v1/tasks/t-1/comments/m-2");
    expect(init?.method).toBe("DELETE");
    confirm.mockRestore();
  });

  it("shows no delete button to somebody who may not delete", async () => {
    const dialog = await openTask(detail({ comments: [mine, theirs] }));

    expect(dialog.queryByRole("button", { name: "Удалить" })).toBeNull();
  });

  it("shows the project on the card and in the task window", async () => {
    const inProject = { project: { id: "p", name: "Запуск" } };
    fetchMock.mockResolvedValueOnce(Response.json(detail(inProject)));
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card(inProject)]} />);

    expect(screen.getByText("Запуск · Продажи")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Подготовить предложение/ }));
    const dialog = within(await screen.findByRole("dialog"));

    expect(dialog.getByText("Проект")).toBeInTheDocument();
    expect(dialog.getByText("Запуск")).toBeInTheDocument();
  });

  it("groups work in progress by project in folded lists and leaves other statuses plain", async () => {
    const launch = { id: "p1", name: "Запуск" };
    const audit = { id: "p2", name: "Аудит" };
    const user = userEvent.setup();
    renderWithIntl(
      <TaskBoard
        view="all"
        statuses={statuses}
        initialCards={[
          card({ id: "a", title: "Новая без проекта" }),
          card({ id: "b", title: "Новая по запуску", project: launch }),
          card({ id: "c", title: "Аудит в работе", project: audit, status_id: "work" }),
          card({ id: "d", title: "Запуск в работе", project: launch, status_id: "work" }),
          card({ id: "e", title: "Ещё запуск в работе", project: launch, status_id: "work" }),
          card({ id: "f", title: "Отдел в работе", status_id: "work" }),
        ]}
      />,
    );

    // Not in work: one plain list, whatever the project.
    const todo = within(screen.getByRole("region", { name: /^Нужно сделать/ }));
    expect(todo.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
    expect(todo.getByRole("button", { name: /Новая без проекта/ })).toBeInTheDocument();
    expect(todo.getByRole("button", { name: /Новая по запуску/ })).toBeInTheDocument();

    // In work: the department first, then the projects by name, all folded.
    const work = within(screen.getByRole("region", { name: /^В работе/ }));
    const groups = work.getAllByRole("button", { expanded: false });
    expect(groups.map((group) => group.textContent)).toEqual([
      "▸ Отдел Продажи1",
      "▸ Проект Аудит1",
      "▸ Проект Запуск2",
    ]);
    expect(work.queryByRole("button", { name: /Запуск в работе/ })).not.toBeInTheDocument();

    await user.click(work.getByRole("button", { name: /Проект Запуск/ }));

    expect(work.getByRole("button", { name: /Проект Запуск/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(work.getByRole("button", { name: /^Запуск в работе/ })).toBeInTheDocument();
    expect(work.getByRole("button", { name: /^Ещё запуск в работе/ })).toBeInTheDocument();
    // The other groups stay folded.
    expect(work.queryByRole("button", { name: /^Аудит в работе/ })).not.toBeInTheDocument();

    await user.click(work.getByRole("button", { name: /Проект Запуск/ }));
    expect(work.queryByRole("button", { name: /^Запуск в работе/ })).not.toBeInTheDocument();
  });

  it("follows each status's own settings, whatever its type", async () => {
    const launch = { id: "p1", name: "Запуск" };
    const custom = statuses.map((status) =>
      status.id === "todo"
        ? { ...status, group_by_project: true }
        : status.id === "work"
          ? { ...status, group_by_project: false, show_project: false }
          : status,
    );
    renderWithIntl(
      <TaskBoard
        view="all"
        statuses={custom}
        initialCards={[
          card({ id: "a", title: "Новая по запуску", project: launch }),
          card({ id: "b", title: "В работе по запуску", project: launch, status_id: "work" }),
        ]}
      />,
    );

    // "Нужно сделать" is divided now, though it is not "in work".
    const todo = within(screen.getByRole("region", { name: /^Нужно сделать/ }));
    await userEvent.click(todo.getByRole("button", { name: /Проект Запуск/ }));
    expect(todo.getByRole("button", { name: /^Новая по запуску/ })).toHaveTextContent(
      "Запуск · Продажи",
    );

    // "В работе" is a plain list and its cards do not name the project.
    const work = within(screen.getByRole("region", { name: /^В работе/ }));
    expect(work.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
    const plain = work.getByRole("button", { name: /^В работе по запуску/ });
    expect(plain).toHaveTextContent("Продажи");
    expect(plain).not.toHaveTextContent("Запуск ·");
  });

  it("lists only what is in work and shows an empty column as empty", () => {
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[card()]} />);

    const work = within(screen.getByRole("region", { name: /^В работе/ }));
    expect(work.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
    expect(work.getByText("Пусто")).toBeInTheDocument();
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
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url === "/api/v1/task-departments") {
        return Promise.resolve(Response.json({ results: [{ id: "d", name: "Продажи" }] }));
      }
      if (url === "/api/v1/task-projects") {
        return Promise.resolve(Response.json({ results: [{ id: "p", name: "Запуск" }] }));
      }
      if (url.startsWith("/api/v1/task-assignees")) {
        return Promise.resolve(Response.json({ results: [{ id: "u", name: "Анна Петрова" }] }));
      }
      if (url === "/api/v1/tasks" && init?.method === "POST") {
        return Promise.resolve(
          Response.json({ id: "t-2", title: "Счёт для клиента", task: null }, { status: 201 }),
        );
      }
      return Promise.resolve(Response.json({ results: [] }));
    });
    renderWithIntl(<TaskBoard view="mine" statuses={statuses} initialCards={[]} canCreate />);

    await user.click(screen.getByRole("button", { name: "Новая задача" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Новая задача" }));
    await user.type(dialog.getByLabelText("Название"), "Счёт для клиента");
    await user.selectOptions(await dialog.findByLabelText("Исполнитель"), "Анна Петрова");
    await user.selectOptions(await dialog.findByLabelText("Проект (необязательно)"), "Запуск");
    await user.click(dialog.getByRole("button", { name: "Создать задачу" }));

    expect(
      await screen.findByText(/Задача «Счёт для клиента» создана и передана исполнителю\./),
    ).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls.find(([, options]) => options?.method === "POST") ?? [];
    expect(JSON.parse(String(init?.body))).toMatchObject({
      project_id: "p",
      title: "Счёт для клиента",
      department_id: "d",
      assignee_id: "u",
      priority: "normal",
      task_type: "task",
      due_at: null,
    });
  });
});
