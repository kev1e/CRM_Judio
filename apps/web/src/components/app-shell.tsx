import type { Me } from "@crm/contracts";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { LogoutButton } from "@/components/logout-button";
import { ThemeToggle } from "@/components/theme-toggle";

export type NavKey =
  "mine" | "all" | "archive" | "trash" | "projects" | "users" | "departments" | "workflow";

const linkClass =
  "block rounded-md px-3 py-2 text-sm whitespace-nowrap hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/**
 * The frame of every signed-in screen: sections on the left (on a phone, a
 * scrollable row on top), the page on the right. A section is listed only if the
 * API says the viewer may use it; the API enforces that again on every request.
 */
export async function AppShell({
  me,
  active,
  children,
}: {
  me: Me;
  active: NavKey;
  children: ReactNode;
}) {
  const t = await getTranslations("nav");
  const { permissions } = me;
  const items: { key: NavKey; href: string; show: boolean }[] = [
    { key: "mine", href: "/", show: true },
    { key: "all", href: "/?view=all", show: permissions["task.read"] !== "own" },
    { key: "archive", href: "/?view=archive", show: true },
    { key: "trash", href: "/?view=trash", show: Boolean(permissions["task.delete"]) },
    { key: "projects", href: "/projects", show: true },
    { key: "users", href: "/users", show: Boolean(permissions["user.read"]) },
    { key: "departments", href: "/departments", show: Boolean(permissions["department.read"]) },
    { key: "workflow", href: "/statuses", show: Boolean(permissions["workflow.manage"]) },
  ];

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col gap-3 border-b border-border bg-surface p-3 md:w-56 md:border-r md:border-b-0">
        <div className="flex items-center justify-between gap-2 px-1">
          <span className="truncate text-sm font-semibold" title={me.user.crm_login}>
            {me.user.display_name}
          </span>
          <ThemeToggle />
        </div>
        <nav aria-label={t("label")} className="overflow-x-auto">
          <ul className="flex gap-1 md:flex-col">
            {items
              .filter((item) => item.show)
              .map((item) => (
                <li key={item.key}>
                  {/* A full page load on purpose: every screen re-reads the session and the data. */}
                  <a
                    href={item.href}
                    aria-current={item.key === active ? "page" : undefined}
                    className={`${linkClass} ${item.key === active ? "bg-muted font-medium" : ""}`}
                  >
                    {t(item.key)}
                  </a>
                </li>
              ))}
          </ul>
        </nav>
        <div className="md:mt-auto">
          <LogoutButton />
        </div>
      </aside>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
