"use client";

import {
  API_PATHS,
  type BindingCode,
  type User,
  type UserCreated,
  type UserList,
} from "@crm/contracts";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";

import { callApi } from "@/lib/api-client";

const ERROR_KEYS = [
  "invalid_login",
  "login_or_email_taken",
  "validation_error",
  "invalid_email",
  "telegram_already_bound",
  "user_inactive",
  "cannot_deactivate_self",
  "last_administrator",
  "permission_denied",
  "department_closed",
  "department_not_found",
  "unavailable",
] as const;
type ErrorKey = (typeof ERROR_KEYS)[number];

function toErrorKey(code: string): ErrorKey {
  return (ERROR_KEYS as readonly string[]).includes(code) ? (code as ErrorKey) : "unavailable";
}

type Permissions = { create: boolean; deactivate: boolean };
type DepartmentOption = { id: string; name: string };
type ShownCode = { name: string; binding: BindingCode };

const fieldClass =
  "h-11 w-full rounded-md border border-border bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const buttonClass =
  "h-10 rounded-md border border-border px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";

export function UsersPanel({
  initialUsers,
  permissions,
  currentUserId,
  departments = [],
  departmentRequired = false,
}: {
  initialUsers: User[];
  permissions: Permissions;
  currentUserId: string;
  /** Departments a new employee may be placed into. */
  departments?: DepartmentOption[];
  /** A manager must place the employee into one of their departments. */
  departmentRequired?: boolean;
}) {
  const t = useTranslations("users");
  const format = useFormatter();
  const [users, setUsers] = useState(initialUsers);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [shownCode, setShownCode] = useState<ShownCode | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  function fail(code: string) {
    setError(toErrorKey(code));
  }

  async function reload() {
    const list = await callApi<UserList>(API_PATHS.users, { method: "GET" });
    if (list.ok) {
      setUsers(list.data.results);
    }
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const displayName = String(data.get("display_name") ?? "").trim();
    void run(async () => {
      const result = await callApi<UserCreated>(API_PATHS.users, {
        method: "POST",
        body: {
          crm_login: String(data.get("crm_login") ?? "").trim(),
          display_name: displayName,
          email: String(data.get("email") ?? "").trim() || null,
          department_id: String(data.get("department_id") ?? "") || null,
        },
      });
      if (!result.ok) {
        fail(result.code);
        return;
      }
      formRef.current?.reset();
      setShownCode({ name: result.data.user.display_name, binding: result.data.binding });
      await reload();
    });
  }

  function newCode(user: User) {
    void run(async () => {
      const result = await callApi<BindingCode>(`${API_PATHS.users}/${user.id}/binding-code`, {
        method: "POST",
      });
      if (result.ok) {
        setShownCode({ name: user.display_name, binding: result.data });
      } else {
        fail(result.code);
      }
    });
  }

  function setActive(user: User, active: boolean) {
    if (!active && !window.confirm(t("confirmDeactivate", { name: user.display_name }))) {
      return;
    }
    void run(async () => {
      const result = await callApi<User>(
        `${API_PATHS.users}/${user.id}/${active ? "reactivate" : "deactivate"}`,
        { method: "POST" },
      );
      if (!result.ok) {
        fail(result.code);
      }
      await reload();
    });
  }

  return (
    <div className="flex flex-col gap-8">
      {error ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}

      {shownCode ? (
        <section
          aria-labelledby="binding-code-title"
          className="flex flex-col gap-3 rounded-md border border-border bg-muted p-4"
        >
          <h2 id="binding-code-title" className="text-lg font-semibold">
            {t("codeTitle", { name: shownCode.name })}
          </h2>
          <p className="text-sm text-muted-foreground">{t("codeDescription")}</p>
          <code className="block overflow-x-auto rounded-md border border-border bg-background px-3 py-2 text-sm whitespace-nowrap select-all">
            {shownCode.binding.command}
          </code>
          <p className="text-sm">
            {t("codeOnce", {
              time: format.dateTime(new Date(shownCode.binding.expires_at), {
                hour: "2-digit",
                minute: "2-digit",
              }),
            })}
          </p>
          <button
            type="button"
            onClick={() => setShownCode(null)}
            className={`${buttonClass} w-fit`}
          >
            {t("codeClose")}
          </button>
        </section>
      ) : null}

      {permissions.create ? (
        <form
          ref={formRef}
          onSubmit={create}
          aria-labelledby="add-user-title"
          className="flex flex-col gap-4"
        >
          <h2 id="add-user-title" className="text-lg font-semibold">
            {t("addTitle")}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("nameLabel")}
              <input
                name="display_name"
                required
                maxLength={150}
                autoComplete="off"
                className={fieldClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("loginLabel")}
              <input
                name="crm_login"
                required
                maxLength={64}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                aria-describedby="login-hint"
                className={fieldClass}
              />
              <span id="login-hint" className="font-normal text-muted-foreground">
                {t("loginHint")}
              </span>
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium sm:col-span-2">
              {t("emailLabel")}
              <input
                name="email"
                type="email"
                maxLength={254}
                autoComplete="off"
                className={fieldClass}
              />
            </label>
            {departments.length > 0 ? (
              <label className="flex flex-col gap-1 text-sm font-medium sm:col-span-2">
                {t("departmentLabel")}
                <select
                  name="department_id"
                  required={departmentRequired}
                  defaultValue={departmentRequired ? departments[0]?.id : ""}
                  className={fieldClass}
                >
                  {departmentRequired ? null : <option value="">{t("departmentNone")}</option>}
                  {departments.map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
          <button
            type="submit"
            disabled={busy}
            className="h-11 w-fit rounded-md bg-primary px-4 font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
          >
            {busy ? t("creating") : t("create")}
          </button>
        </form>
      ) : null}

      {users.length === 0 ? (
        <p className="text-muted-foreground">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th scope="col" className="py-2 pr-4 font-medium">
                  {t("columns.name")}
                </th>
                <th scope="col" className="py-2 pr-4 font-medium">
                  {t("columns.login")}
                </th>
                <th scope="col" className="py-2 pr-4 font-medium">
                  {t("columns.departments")}
                </th>
                <th scope="col" className="py-2 pr-4 font-medium">
                  {t("columns.state")}
                </th>
                <th scope="col" className="py-2 font-medium">
                  {t("columns.actions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-b border-border align-top">
                  <th scope="row" className="py-3 pr-4 font-medium">
                    {user.display_name}
                  </th>
                  <td className="py-3 pr-4">{user.crm_login}</td>
                  <td className="py-3 pr-4">
                    {user.departments.length === 0 ? (
                      <span className="text-muted-foreground">{t("noDepartment")}</span>
                    ) : (
                      <ul className="flex flex-col gap-1">
                        {user.departments.map((department) => (
                          <li key={department.id}>
                            {department.name}
                            {department.is_primary || department.is_manager ? (
                              <span className="text-muted-foreground">
                                {" "}
                                (
                                {[
                                  department.is_primary ? t("primaryMark") : null,
                                  department.is_manager ? t("managerMark") : null,
                                ]
                                  .filter(Boolean)
                                  .join(", ")}
                                )
                              </span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    <ul className="flex flex-col gap-1">
                      <li>{user.is_active ? t("state.active") : t("state.inactive")}</li>
                      {user.telegram_bound ? null : <li>{t("state.noTelegram")}</li>}
                      {user.has_password ? null : <li>{t("state.noPassword")}</li>}
                    </ul>
                  </td>
                  <td className="py-3">
                    <div className="flex flex-wrap gap-2">
                      {permissions.create && user.is_active && !user.telegram_bound ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => newCode(user)}
                          className={buttonClass}
                        >
                          {t("actions.newCode")}
                        </button>
                      ) : null}
                      {permissions.deactivate && user.id !== currentUserId ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => setActive(user, !user.is_active)}
                          className={buttonClass}
                        >
                          {user.is_active ? t("actions.deactivate") : t("actions.reactivate")}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
