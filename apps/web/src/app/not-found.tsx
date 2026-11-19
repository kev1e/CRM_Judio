import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("notFound");

  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-4 px-4">
      <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
      <p className="text-muted-foreground">{t("description")}</p>
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- full reload re-checks the API state */}
      <a href="/" className="w-fit underline underline-offset-4">
        {t("home")}
      </a>
    </main>
  );
}
