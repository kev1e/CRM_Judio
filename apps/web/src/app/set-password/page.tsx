import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SetPasswordForm } from "@/components/set-password-form";
import { ThemeToggle } from "@/components/theme-toggle";

// The address carries a one-time secret in its fragment: send no Referer anywhere.
export const metadata: Metadata = { referrer: "no-referrer" };

export default async function SetPasswordPage() {
  const t = await getTranslations("home");

  return (
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col px-4 py-6">
      <header className="flex items-center justify-between">
        <span className="text-lg font-semibold">{t("title")}</span>
        <ThemeToggle />
      </header>
      <main className="flex flex-1 flex-col justify-center py-12">
        <SetPasswordForm />
      </main>
    </div>
  );
}
