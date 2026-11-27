"use client";

import { API_PATHS, type CompanyHead, type Department, type User } from "@crm/contracts";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { callApi } from "@/lib/api-client";
import {
  buildTree,
  type DepartmentNode,
  type TreePerson,
  withoutDepartment,
} from "@/lib/structure";

const ERROR_KEYS = [
  "invalid_responsibility",
  "invalid_head_title",
  "user_inactive",
  "department_closed",
  "primary_department_required",
  "designated_manager_required",
  "permission_denied",
  "unavailable",
] as const;
type ErrorKey = (typeof ERROR_KEYS)[number];

function toErrorKey(code: string): ErrorKey {
  return (ERROR_KEYS as readonly string[]).includes(code) ? (code as ErrorKey) : "unavailable";
}

const buttonClass =
  "min-h-8 rounded-md border border-border px-2 py-1 text-xs hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";
const fieldClass =
  "h-8 w-full rounded-md border border-border bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const boxClass = "w-60 rounded-md border border-border bg-surface px-3 py-2 text-center";

type Role = "designated" | "manager" | "employee" | "none";
type Step = { path: string; method: "POST" | "DELETE"; body?: unknown };

/**
 * The company structure drawn as a tree: the top, the departments, their
 * managers and the employees under them. The links follow from the departments,
 * so a person gets into the tree by being put into a department; whoever may
 * manage departments changes those links right here.
 */
export function StructureTree({
  initialDepartments,
  users,
  canEdit,
  canManage,
  initialHead,
}: {
  initialDepartments: Department[];
  /** Every account; `null` when the viewer does not see all of them. */
  users: User[] | null;
  /** May write what a person answers for. */
  canEdit: boolean;
  /** May change who is in which department and who manages it. */
  canManage: boolean;
  /** What stands at the top: a caption and, optionally, an account. */
  initialHead: CompanyHead;
}) {
  const t = useTranslations("structure");
  const [departments, setDepartments] = useState(initialDepartments);
  // One person can stand in several places; the note is kept once, by person.
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [head, setHead] = useState(initialHead);
  const [editingHead, setEditingHead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);

  const tree = buildTree(departments);
  const unplaced = users ? withoutDepartment(departments, users) : null;
  const people = canManage && users ? users.filter((user) => user.is_active) : [];

  /** Runs changes of departments one after another; stops at the first refusal. */
  async function change(steps: Step[]): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      for (const step of steps) {
        const result = await callApi<Department>(step.path, {
          method: step.method,
          body: step.body,
        });
        if (!result.ok) {
          setError(toErrorKey(result.code));
          return false;
        }
        const updated = result.data;
        setDepartments((current) =>
          current.map((department) => (department.id === updated.id ? updated : department)),
        );
      }
      setEditing(null);
      return true;
    } finally {
      setBusy(false);
    }
  }

  const base = (departmentId: string) => `${API_PATHS.departments}/${departmentId}`;

  function saveNote(event: FormEvent<HTMLFormElement>, target: TreePerson) {
    event.preventDefault();
    const responsibility = String(new FormData(event.currentTarget).get("responsibility") ?? "");
    setBusy(true);
    setError(null);
    void callApi<User>(`${API_PATHS.users}/${target.id}`, {
      method: "PATCH",
      body: { responsibility },
    })
      .then((result) => {
        if (!result.ok) {
          setError(toErrorKey(result.code));
          return;
        }
        setNotes((current) => ({ ...current, [target.id]: result.data.responsibility }));
        setEditing(null);
      })
      .finally(() => setBusy(false));
  }

  function saveHead(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    void callApi<CompanyHead>(API_PATHS.structureHead, {
      method: "PATCH",
      body: {
        title: String(data.get("title") ?? ""),
        user_id: String(data.get("user_id") ?? "") || null,
      },
    })
      .then((result) => {
        if (!result.ok) {
          setError(toErrorKey(result.code));
          return;
        }
        setHead(result.data);
        setEditingHead(false);
      })
      .finally(() => setBusy(false));
  }

  /** Puts the person into another department; out of `from`, if they stand in one. */
  function move(event: FormEvent<HTMLFormElement>, one: TreePerson, from: DepartmentNode | null) {
    event.preventDefault();
    const target = String(new FormData(event.currentTarget).get("department_id") ?? "");
    if (!target) {
      return;
    }
    const steps: Step[] = [
      {
        path: `${base(target)}/members`,
        method: "POST",
        // The new department becomes the primary one, so the old one can be left.
        body: { user_id: one.id, is_primary: true },
      },
    ];
    if (from) {
      steps.push({ path: `${base(from.id)}/members/${one.id}`, method: "DELETE" });
    }
    void change(steps);
  }

  function links(one: TreePerson, role: Role, node: DepartmentNode | null) {
    const others = tree.filter((other) => other.id !== node?.id);
    return (
      <div className="flex w-full flex-col gap-2 border-t border-border pt-2">
        {others.length > 0 ? (
          <form onSubmit={(event) => move(event, one, node)} className="flex flex-col gap-1">
            <select
              name="department_id"
              defaultValue=""
              aria-label={`${node ? t("moveTo") : t("putInto")}: ${one.display_name}`}
              className={fieldClass}
            >
              <option value="">{node ? t("moveTo") : t("putInto")}</option>
              {others.map((other) => (
                <option key={other.id} value={other.id}>
                  {other.name}
                </option>
              ))}
            </select>
            <button type="submit" disabled={busy} className={buttonClass}>
              {node ? t("move") : t("put")}
            </button>
          </form>
        ) : null}
        {node && role === "employee" ? (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void change([
                  { path: `${base(node.id)}/managers`, method: "POST", body: { user_id: one.id } },
                ])
              }
              className={buttonClass}
            >
              {t("makeManager")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void change([{ path: `${base(node.id)}/members/${one.id}`, method: "DELETE" }])
              }
              className={buttonClass}
            >
              {t("removeFromDepartment")}
            </button>
          </>
        ) : null}
        {node && role === "manager" ? (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void change([
                {
                  path: `${base(node.id)}/managers`,
                  method: "POST",
                  body: { user_id: one.id, is_designated: true },
                },
              ])
            }
            className={buttonClass}
          >
            {t("makeDesignated")}
          </button>
        ) : null}
        {node && (role === "manager" || role === "designated") ? (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void change([{ path: `${base(node.id)}/managers/${one.id}`, method: "DELETE" }])
            }
            className={buttonClass}
          >
            {t("removeManager")}
          </button>
        ) : null}
      </div>
    );
  }

  function card(one: TreePerson, role: Role, node: DepartmentNode | null) {
    const note = notes[one.id] ?? one.responsibility;
    const key = `${node?.id ?? "unplaced"}:${one.id}`;
    const open = editing === key;
    return (
      <div className={`${boxClass} flex flex-col items-center gap-1`}>
        <div className="flex flex-col">
          <span className="font-medium">{one.display_name}</span>
          {role === "none" ? null : (
            <span className="text-xs text-muted-foreground">{t(`roles.${role}`)}</span>
          )}
        </div>
        {open && canEdit ? (
          <form
            onSubmit={(event) => saveNote(event, one)}
            className="flex w-full flex-wrap justify-center gap-2"
          >
            <input
              name="responsibility"
              defaultValue={note}
              maxLength={300}
              autoComplete="off"
              autoFocus
              aria-label={`${t("responsibility")}: ${one.display_name}`}
              placeholder={t("responsibility")}
              className={fieldClass}
            />
            <button type="submit" disabled={busy} className={buttonClass}>
              {t("save")}
            </button>
          </form>
        ) : (
          <span className={`text-sm ${note ? "" : "text-muted-foreground"}`}>
            {note ? `${t("responsibility")}: ${note}` : t("noResponsibility")}
          </span>
        )}
        {open && canManage ? links(one, role, node) : null}
        {canEdit || canManage ? (
          <button
            type="button"
            aria-label={`${open ? t("close") : t("edit")}: ${one.display_name}`}
            onClick={() => {
              setError(null);
              setEditing(open ? null : key);
            }}
            className={buttonClass}
          >
            {open ? t("close") : t("edit")}
          </button>
        ) : null}
      </div>
    );
  }

  function top() {
    if (editingHead) {
      return (
        <form onSubmit={saveHead} className={`${boxClass} flex flex-col gap-2`}>
          <input
            name="title"
            defaultValue={head.title}
            maxLength={150}
            autoComplete="off"
            autoFocus
            aria-label={t("headTitle")}
            placeholder={t("headTitle")}
            className={fieldClass}
          />
          <select
            name="user_id"
            defaultValue={head.user?.id ?? ""}
            aria-label={t("headAccount")}
            className={fieldClass}
          >
            <option value="">{t("headNoAccount")}</option>
            {people.map((one) => (
              <option key={one.id} value={one.id}>
                {one.display_name}
              </option>
            ))}
          </select>
          <div className="flex justify-center gap-2">
            <button type="submit" disabled={busy} className={buttonClass}>
              {t("save")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditingHead(false)}
              className={buttonClass}
            >
              {t("cancel")}
            </button>
          </div>
        </form>
      );
    }
    const note = head.user ? (notes[head.user.id] ?? head.user.responsibility) : "";
    return (
      <div className={`${boxClass} flex flex-col items-center gap-1`}>
        <span className="font-semibold">{head.title || t("company")}</span>
        {head.user ? (
          <>
            <span className="text-sm">{head.user.display_name}</span>
            {note ? <span className="text-sm">{`${t("responsibility")}: ${note}`}</span> : null}
          </>
        ) : null}
        {canManage ? (
          <button
            type="button"
            aria-label={t("editHead")}
            onClick={() => {
              setError(null);
              setEditingHead(true);
            }}
            className={buttonClass}
          >
            {t("edit")}
          </button>
        ) : null}
      </div>
    );
  }

  function departmentBox(node: DepartmentNode) {
    const inside = new Set([...node.managers, ...node.employees].map((one) => one.id));
    const candidates = people.filter((one) => !inside.has(one.id));
    return (
      <div className={`${boxClass} flex flex-col gap-1`}>
        <span className="text-xs text-muted-foreground">{t("department")}</span>
        <span className="font-semibold">{node.name}</span>
        {canManage && candidates.length > 0 ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const userId = String(new FormData(form).get("user_id") ?? "");
              if (userId) {
                void change([
                  { path: `${base(node.id)}/members`, method: "POST", body: { user_id: userId } },
                ]).then((ok) => {
                  if (ok) {
                    form.reset();
                  }
                });
              }
            }}
            className="flex flex-col gap-1"
          >
            <select
              name="user_id"
              defaultValue=""
              aria-label={`${t("addEmployee")}: ${node.name}`}
              className={fieldClass}
            >
              <option value="">{t("addEmployee")}</option>
              {candidates.map((one) => (
                <option key={one.id} value={one.id}>
                  {one.display_name}
                </option>
              ))}
            </select>
            <button type="submit" disabled={busy} className={buttonClass}>
              {t("add")}
            </button>
          </form>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {error ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}

      {/* A wide company does not fit a screen: the tree scrolls sideways. */}
      <div className="overflow-x-auto pb-4">
        <ul className="org-tree w-max min-w-full">
          <li>
            {top()}
            {tree.length > 0 ? (
              <ul aria-label={t("departments")}>
                {tree.map((node) => {
                  const [first, ...others] = node.managers;
                  return (
                    <li key={node.id}>
                      {departmentBox(node)}
                      <ul aria-label={`${t("managers")}: ${node.name}`}>
                        <li>
                          {first ? (
                            card(first, first.is_designated ? "designated" : "manager", node)
                          ) : (
                            <p
                              className={`${boxClass} border-dashed text-sm text-muted-foreground`}
                            >
                              {t("noManager")}
                            </p>
                          )}
                          {node.employees.length > 0 ? (
                            <ul aria-label={`${t("employees")}: ${node.name}`}>
                              {node.employees.map((employee) => (
                                <li key={employee.id}>{card(employee, "employee", node)}</li>
                              ))}
                            </ul>
                          ) : null}
                        </li>
                        {others.map((manager) => (
                          <li key={manager.id}>{card(manager, "manager", node)}</li>
                        ))}
                      </ul>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </li>
        </ul>
      </div>

      {tree.length === 0 ? <p className="text-muted-foreground">{t("empty")}</p> : null}

      {unplaced && unplaced.length > 0 ? (
        <section aria-labelledby="structure-unplaced" className="flex flex-col gap-2">
          <h2 id="structure-unplaced" className="text-lg font-semibold">
            {t("unplaced")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("unplacedHint")}</p>
          <ul className="flex flex-wrap items-start gap-3">
            {unplaced.map((one) => (
              <li key={one.id}>{card(one, "none", null)}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="text-sm text-muted-foreground">{t("autoHint")}</p>
    </div>
  );
}
