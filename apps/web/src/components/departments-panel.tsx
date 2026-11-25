"use client";

import { API_PATHS, type Department } from "@crm/contracts";
import { useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";

import { callApi } from "@/lib/api-client";

const ERROR_KEYS = [
  "invalid_department_name",
  "department_name_taken",
  "department_closed",
  "department_is_primary",
  "primary_department_required",
  "designated_manager_required",
  "not_a_member",
  "user_inactive",
  "permission_denied",
  "unavailable",
] as const;
type ErrorKey = (typeof ERROR_KEYS)[number];

function toErrorKey(code: string): ErrorKey {
  return (ERROR_KEYS as readonly string[]).includes(code) ? (code as ErrorKey) : "unavailable";
}

export type Person = { id: string; display_name: string; crm_login: string };

const fieldClass =
  "h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const buttonClass =
  "h-9 rounded-md border border-border px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";

export function DepartmentsPanel({
  initialDepartments,
  people,
  canManage,
}: {
  initialDepartments: Department[];
  /** Active employees who can be added; empty when the viewer cannot manage. */
  people: Person[];
  canManage: boolean;
}) {
  const t = useTranslations("departments");
  const [departments, setDepartments] = useState(initialDepartments);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const createRef = useRef<HTMLFormElement>(null);

  async function change(
    path: string,
    method: "POST" | "PATCH" | "DELETE",
    body?: unknown,
  ): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      const result = await callApi<Department>(path, { method, body });
      if (!result.ok) {
        setError(toErrorKey(result.code));
        return false;
      }
      const updated = result.data;
      setDepartments((current) =>
        current.some((department) => department.id === updated.id)
          ? current.map((department) => (department.id === updated.id ? updated : department))
          : [...current, updated].sort((a, b) => a.name.localeCompare(b.name, "ru")),
      );
      return true;
    } finally {
      setBusy(false);
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "");
    void change(API_PATHS.departments, "POST", { name }).then((ok) => {
      if (ok) {
        createRef.current?.reset();
      }
    });
  }

  function add(
    event: FormEvent<HTMLFormElement>,
    department: Department,
    kind: "members" | "managers",
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const userId = String(new FormData(form).get("user_id") ?? "");
    if (!userId) {
      return;
    }
    void change(`${API_PATHS.departments}/${department.id}/${kind}`, "POST", {
      user_id: userId,
    }).then((ok) => {
      if (ok) {
        form.reset();
      }
    });
  }

  return (
    <div className="flex flex-col gap-8">
      {error ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}

      {canManage ? (
        <form ref={createRef} onSubmit={create} className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-60 flex-1 flex-col gap-1 text-sm font-medium">
            {t("nameLabel")}
            <input name="name" required maxLength={150} autoComplete="off" className={fieldClass} />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
          >
            {t("create")}
          </button>
        </form>
      ) : null}

      {departments.length === 0 ? <p className="text-muted-foreground">{t("empty")}</p> : null}

      {departments.map((department) => {
        const base = `${API_PATHS.departments}/${department.id}`;
        const memberIds = new Set(department.members.map((member) => member.id));
        const managerIds = new Set(department.managers.map((manager) => manager.id));
        const editable = canManage && department.is_active;
        return (
          <section
            key={department.id}
            aria-labelledby={`department-${department.id}`}
            className="flex flex-col gap-4 rounded-md border border-border p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id={`department-${department.id}`} className="text-lg font-semibold">
                {department.name}
                {department.is_active ? null : (
                  <span className="font-normal text-muted-foreground"> ({t("closed")})</span>
                )}
              </h2>
              {canManage ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void change(base, "PATCH", { is_active: !department.is_active })}
                  className={buttonClass}
                >
                  {department.is_active ? t("close") : t("reopen")}
                </button>
              ) : null}
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="flex flex-col gap-2">
                <h3 className="text-sm font-medium text-muted-foreground">{t("managers")}</h3>
                {department.managers.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t("nobody")}</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {department.managers.map((manager) => (
                      <li key={manager.id} className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="flex-1">
                          {manager.display_name}
                          {manager.is_designated ? (
                            <span className="text-muted-foreground"> ({t("designatedMark")})</span>
                          ) : null}
                          {manager.is_active ? null : (
                            <span className="text-muted-foreground"> ({t("inactiveMark")})</span>
                          )}
                        </span>
                        {editable && !manager.is_designated ? (
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={`${t("makeDesignated")}: ${manager.display_name}`}
                            onClick={() =>
                              void change(`${base}/managers`, "POST", {
                                user_id: manager.id,
                                is_designated: true,
                              })
                            }
                            className={buttonClass}
                          >
                            {t("makeDesignated")}
                          </button>
                        ) : null}
                        {canManage ? (
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={`${t("remove")}: ${manager.display_name}`}
                            onClick={() => void change(`${base}/managers/${manager.id}`, "DELETE")}
                            className={buttonClass}
                          >
                            {t("remove")}
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
                {editable ? (
                  <form
                    onSubmit={(event) => add(event, department, "managers")}
                    className="flex gap-2"
                  >
                    <select
                      name="user_id"
                      defaultValue=""
                      aria-label={t("addManager")}
                      className={fieldClass}
                    >
                      <option value="">{t("addManager")}</option>
                      {people
                        .filter((person) => !managerIds.has(person.id))
                        .map((person) => (
                          <option key={person.id} value={person.id}>
                            {person.display_name}
                          </option>
                        ))}
                    </select>
                    <button type="submit" disabled={busy} className={buttonClass}>
                      {t("add")}
                    </button>
                  </form>
                ) : null}
              </div>

              <div className="flex flex-col gap-2">
                <h3 className="text-sm font-medium text-muted-foreground">{t("members")}</h3>
                {department.members.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t("nobody")}</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {department.members.map((member) => (
                      <li key={member.id} className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="flex-1">
                          {member.display_name}
                          {member.is_primary ? (
                            <span className="text-muted-foreground"> ({t("primaryMark")})</span>
                          ) : null}
                          {member.is_active ? null : (
                            <span className="text-muted-foreground"> ({t("inactiveMark")})</span>
                          )}
                        </span>
                        {editable && !member.is_primary && member.is_active ? (
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={`${t("makePrimary")}: ${member.display_name}`}
                            onClick={() =>
                              void change(`${base}/members`, "POST", {
                                user_id: member.id,
                                is_primary: true,
                              })
                            }
                            className={buttonClass}
                          >
                            {t("makePrimary")}
                          </button>
                        ) : null}
                        {canManage ? (
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={`${t("remove")}: ${member.display_name}`}
                            onClick={() => void change(`${base}/members/${member.id}`, "DELETE")}
                            className={buttonClass}
                          >
                            {t("remove")}
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
                {editable ? (
                  <form
                    onSubmit={(event) => add(event, department, "members")}
                    className="flex gap-2"
                  >
                    <select
                      name="user_id"
                      defaultValue=""
                      aria-label={t("addMember")}
                      className={fieldClass}
                    >
                      <option value="">{t("addMember")}</option>
                      {people
                        .filter((person) => !memberIds.has(person.id))
                        .map((person) => (
                          <option key={person.id} value={person.id}>
                            {person.display_name}
                          </option>
                        ))}
                    </select>
                    <button type="submit" disabled={busy} className={buttonClass}>
                      {t("add")}
                    </button>
                  </form>
                ) : null}
              </div>
            </div>
          </section>
        );
      })}

      {canManage ? <p className="text-sm text-muted-foreground">{t("designatedHint")}</p> : null}
    </div>
  );
}
