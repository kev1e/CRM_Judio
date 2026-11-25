import { API_PATHS, type DepartmentList, type UserList } from "@crm/contracts";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { AppShell } from "@/components/app-shell";
import { DepartmentsPanel } from "@/components/departments-panel";
import { getApiInternalUrl } from "@/lib/env";
import { fetchCurrentSession } from "@/lib/session";

export const dynamic = "force-dynamic";

async function fetchJson<T>(path: string, cookieHeader: string): Promise<T | null> {
  try {
    const response = await fetch(new URL(path, getApiInternalUrl()), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: { Accept: "application/json", Cookie: cookieHeader },
    });
    return response.ok ? ((await response.json()) as T) : null;
  } catch {
    return null;
  }
}

export default async function DepartmentsPage() {
  const t = await getTranslations("departments");
  const cookieHeader = (await cookies()).toString();
  const session = await fetchCurrentSession(cookieHeader);
  if (session.state === "anonymous") {
    redirect("/login");
  }
  // The API decides who may see departments; without the right the page does not exist.
  const list =
    session.state === "authenticated"
      ? await fetchJson<DepartmentList>(API_PATHS.departments, cookieHeader)
      : null;
  if (session.state !== "authenticated" || list === null) {
    notFound();
  }
  const canManage = session.me.permissions["department.manage"] === "company";
  const users = canManage ? await fetchJson<UserList>(API_PATHS.users, cookieHeader) : null;

  return (
    <AppShell me={session.me} active="departments">
      <main className="mx-auto flex max-w-4xl flex-col gap-6 p-4">
        <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
        <DepartmentsPanel
          initialDepartments={list.results}
          canManage={canManage}
          people={(users?.results ?? [])
            .filter((user) => user.is_active)
            .map(({ id, display_name, crm_login }) => ({ id, display_name, crm_login }))}
        />
      </main>
    </AppShell>
  );
}
