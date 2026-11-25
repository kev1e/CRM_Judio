import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { LoginForm } from "@/components/login-form";
import { ThemeToggle } from "@/components/theme-toggle";
import { fetchCurrentSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const t = await getTranslations("home");
  const session = await fetchCurrentSession((await cookies()).toString());
  if (session.state === "authenticated") {
    redirect("/");
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col px-4 py-6">
      <header className="flex items-center justify-between">
        <span className="text-lg font-semibold">{t("title")}</span>
        <ThemeToggle />
      </header>
      <main className="flex flex-1 flex-col justify-center py-12">
        <LoginForm />
      </main>
    </div>
  );
}
