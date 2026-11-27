import { API_PATHS, type CompanyHead, type DepartmentList, type UserList } from "@crm/contracts";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { AppShell } from "@/components/app-shell";
import { StructureTree } from "@/components/structure-tree";
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

export default async function StructurePage() {
  const t = await getTranslations("structure");
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
  const { permissions } = session.me;
  // Only somebody who sees every account can tell who is in no department.
  const users =
    permissions["user.read"] === "company"
      ? await fetchJson<UserList>(API_PATHS.users, cookieHeader)
      : null;

  const head = await fetchJson<CompanyHead>(API_PATHS.structureHead, cookieHeader);
  const canManage = permissions["department.manage"] === "company";

  return (
    <AppShell me={session.me} active="structure">
      <main className="flex flex-col gap-6 p-4">
        <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
        <StructureTree
          initialDepartments={list.results}
          users={users?.results ?? null}
          canEdit={permissions["user.update"] === "company"}
          canManage={canManage}
          initialHead={head ?? { title: "", user: null }}
        />
      </main>
    </AppShell>
  );
}
