"use client";

import { API_PATHS, type User } from "@crm/contracts";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { callApi } from "@/lib/api-client";
import type { DepartmentNode, TreePerson } from "@/lib/structure";

const ERROR_KEYS = ["invalid_responsibility", "permission_denied", "unavailable"] as const;
type ErrorKey = (typeof ERROR_KEYS)[number];

function toErrorKey(code: string): ErrorKey {
  return (ERROR_KEYS as readonly string[]).includes(code) ? (code as ErrorKey) : "unavailable";
}

const buttonClass =
  "h-8 rounded-md border border-border px-2 text-xs hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";
const boxClass = "w-56 rounded-md border border-border bg-surface px-3 py-2 text-center";

type Role = "designated" | "manager" | "employee" | "none";

/**
 * The company structure: departments, their managers and the employees under
 * them. It is built from the departments, so it needs no upkeep of its own; what
 * is edited here is only the note on what each person answers for.
 */
export function StructureTree({
  initialTree,
  initialUnplaced,
  canEdit,
  canManage,
}: {
  initialTree: DepartmentNode[];
  /** Employees in no department; `null` when the viewer does not see all accounts. */
  initialUnplaced: TreePerson[] | null;
  /** May write what a person answers for. */
  canEdit: boolean;
  /** May change who is in which department (done on the Departments screen). */
  canManage: boolean;
}) {
  const t = useTranslations("structure");
  // One person can stand in several places; the note is kept once, by person.
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);

  function save(event: FormEvent<HTMLFormElement>, target: TreePerson) {
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

  function row(one: TreePerson, role: Role, place: string) {
    const note = notes[one.id] ?? one.responsibility;
    const key = `${place}:${one.id}`;
    return (
      <div className={`${boxClass} flex flex-col items-center gap-1`}>
        <div className="flex flex-col">
          <span className="font-medium">{one.display_name}</span>
          {role === "none" ? null : (
            <span className="text-xs text-muted-foreground">{t(`roles.${role}`)}</span>
          )}
        </div>
        {editing === key ? (
          <form
            onSubmit={(event) => save(event, one)}
            className="flex w-full flex-wrap justify-center gap-2"
          >
            <input
              name="responsibility"
              defaultValue={note}
              maxLength={300}
              autoComplete="off"
              autoFocus
              aria-label={`${t("responsibility")}: ${one.display_name}`}
              className="h-8 w-full rounded-md border border-border bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            />
            <button type="submit" disabled={busy} className={buttonClass}>
              {t("save")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditing(null)}
              className={buttonClass}
            >
              {t("cancel")}
            </button>
          </form>
        ) : (
          <div className="flex flex-col items-center gap-1 text-sm">
            <span className={note ? "" : "text-muted-foreground"}>
              {note ? `${t("responsibility")}: ${note}` : t("noResponsibility")}
            </span>
            {canEdit ? (
              <button
                type="button"
                aria-label={`${t("edit")}: ${one.display_name}`}
                onClick={() => {
                  setError(null);
                  setEditing(key);
                }}
                className={buttonClass}
              >
                {t("edit")}
              </button>
            ) : null}
          </div>
        )}
      </div>
    );
  }

  function employees(node: DepartmentNode) {
    if (node.employees.length === 0) {
      return null;
    }
    return (
      <ul aria-label={`${t("employees")}: ${node.name}`}>
        {node.employees.map((employee) => (
          <li key={employee.id}>{row(employee, "employee", node.id)}</li>
        ))}
      </ul>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {error ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}

      {initialTree.length === 0 ? (
        <p className="text-muted-foreground">{t("empty")}</p>
      ) : (
        // A wide company does not fit a screen: the tree scrolls sideways.
        <div className="overflow-x-auto pb-4">
          <ul className="org-tree w-max min-w-full">
            <li>
              <div className={`${boxClass} font-semibold`}>{t("company")}</div>
              <ul aria-label={t("departments")}>
                {initialTree.map((node) => {
                  const [head, ...others] = node.managers;
                  return (
                    <li key={node.id}>
                      <div className={`${boxClass} flex flex-col gap-1`}>
                        <span className="text-xs text-muted-foreground">{t("department")}</span>
                        <span className="font-semibold">{node.name}</span>
                        {canManage ? (
                          <a
                            href={`/departments#department-${node.id}`}
                            aria-label={`${t("changeStaff")}: ${node.name}`}
                            className="text-xs underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                          >
                            {t("changeStaff")}
                          </a>
                        ) : null}
                      </div>
                      <ul aria-label={`${t("managers")}: ${node.name}`}>
                        <li>
                          {head ? (
                            row(head, head.is_designated ? "designated" : "manager", node.id)
                          ) : (
                            <p
                              className={`${boxClass} border-dashed text-sm text-muted-foreground`}
                            >
                              {t("noManager")}
                            </p>
                          )}
                          {employees(node)}
                        </li>
                        {others.map((manager) => (
                          <li key={manager.id}>{row(manager, "manager", node.id)}</li>
                        ))}
                      </ul>
                    </li>
                  );
                })}
              </ul>
            </li>
          </ul>
        </div>
      )}

      {initialUnplaced && initialUnplaced.length > 0 ? (
        <section aria-labelledby="structure-unplaced" className="flex flex-col gap-2">
          <h2 id="structure-unplaced" className="text-lg font-semibold">
            {t("unplaced")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("unplacedHint")}</p>
          <ul className="flex flex-wrap gap-3">
            {initialUnplaced.map((one) => (
              <li key={one.id}>{row(one, "none", "unplaced")}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="text-sm text-muted-foreground">{t("autoHint")}</p>
    </div>
  );
}
