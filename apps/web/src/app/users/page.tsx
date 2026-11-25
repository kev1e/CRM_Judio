import { API_PATHS, type DepartmentList, type UserList } from "@crm/contracts";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { AppShell } from "@/components/app-shell";
import { UsersPanel } from "@/components/users-panel";
import { getApiInternalUrl } from "@/lib/env";
import { fetchCurrentSession } from "@/lib/session";

export const dynamic = "force-dynamic";

async function fetchUsers(cookieHeader: string): Promise<UserList | null> {
  try {
    const response = await fetch(new URL(API_PATHS.users, getApiInternalUrl()), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: { Accept: "application/json", Cookie: cookieHeader },
    });
    return response.ok ? ((await response.json()) as UserList) : null;
  } catch {
    return null;
  }
}

async function fetchDepartments(cookieHeader: string): Promise<DepartmentList["results"]> {
  try {
    const response = await fetch(new URL(API_PATHS.departments, getApiInternalUrl()), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: { Accept: "application/json", Cookie: cookieHeader },
    });
    return response.ok ? ((await response.json()) as DepartmentList).results : [];
  } catch {
    return [];
  }
}

export default async function UsersPage() {
  const t = await getTranslations("users");
  const cookieHeader = (await cookies()).toString();
  const session = await fetchCurrentSession(cookieHeader);
  if (session.state === "anonymous") {
    redirect("/login");
  }
  // The API decides who may see accounts; without the right the page does not exist.
  const list = session.state === "authenticated" ? await fetchUsers(cookieHeader) : null;
  if (session.state !== "authenticated" || list === null) {
    notFound();
  }
  const { permissions, user } = session.me;
  // Open departments the viewer may see; for a manager these are the managed ones.
  const departments = permissions["department.read"]
    ? (await fetchDepartments(cookieHeader)).filter((department) => department.is_active)
    : [];

  return (
    <AppShell me={session.me} active="users">
      <main className="mx-auto flex max-w-4xl flex-col gap-6 p-4">
        <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
        <UsersPanel
          initialUsers={list.results}
          currentUserId={user.id}
          permissions={{
            create: Boolean(permissions["user.create"]),
            deactivate: permissions["user.deactivate"] === "company",
          }}
          departments={departments.map(({ id, name }) => ({ id, name }))}
          departmentRequired={permissions["user.create"] === "managed_departments"}
        />
      </main>
    </AppShell>
  );
}
