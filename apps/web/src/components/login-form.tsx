"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  formatRemaining,
  type LoginFailure,
  logout,
  pollLogin,
  startLogin,
} from "@/lib/login-client";

const POLL_INTERVAL_MS = 2000;

type Phase =
  | { name: "form"; failure?: LoginFailure; retryAfter?: number }
  | { name: "submitting" }
  | { name: "waiting"; expiresAt: number };

const fieldClass =
  "h-11 w-full rounded-md border border-border bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

export function LoginForm() {
  const t = useTranslations("login");
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>({ name: "form" });
  const [now, setNow] = useState(() => Date.now());
  const errorRef = useRef<HTMLParagraphElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const waitingUntil = phase.name === "waiting" ? phase.expiresAt : null;

  // While waiting: ask the server every two seconds and tick the countdown.
  useEffect(() => {
    if (waitingUntil === null) {
      return;
    }
    let active = true;
    const poll = window.setInterval(() => {
      void pollLogin().then((result) => {
        if (!active) {
          return;
        }
        if (result.state === "authenticated") {
          router.replace("/");
          router.refresh();
        } else if (result.state === "failed") {
          setPhase({ name: "form", failure: result.failure });
        }
      });
    }, POLL_INTERVAL_MS);
    const tick = window.setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= waitingUntil) {
        setPhase({ name: "form", failure: "expired" });
      }
    }, 1000);
    return () => {
      active = false;
      window.clearInterval(poll);
      window.clearInterval(tick);
    };
  }, [waitingUntil, router]);

  const failure = phase.name === "form" ? phase.failure : undefined;
  useEffect(() => {
    if (failure) {
      errorRef.current?.focus();
    }
  }, [failure]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const login = String(data.get("login") ?? "");
    const password = String(data.get("password") ?? "");
    setPhase({ name: "submitting" });
    const result = await startLogin(login, password);
    if (result.ok) {
      setNow(Date.now());
      setPhase({ name: "waiting", expiresAt: result.expiresAt.getTime() });
    } else {
      // The login stays for a retry; the password has to be typed again.
      if (passwordRef.current) {
        passwordRef.current.value = "";
      }
      setPhase({ name: "form", failure: result.failure, retryAfter: result.retryAfter });
    }
  }

  if (phase.name === "waiting") {
    return (
      <section aria-labelledby="login-waiting" className="flex flex-col gap-4">
        <h1 id="login-waiting" className="text-2xl font-semibold tracking-tight">
          {t("waitingTitle")}
        </h1>
        <p className="text-muted-foreground">{t("waitingDescription")}</p>
        <p role="timer" aria-live="off" className="text-sm tabular-nums">
          {t("waitingRemaining", { time: formatRemaining((phase.expiresAt - now) / 1000) })}
        </p>
        <button
          type="button"
          onClick={() => {
            // Giving up also disarms the prompt that is waiting in Telegram.
            void logout();
            setPhase({ name: "form" });
          }}
          className="h-11 w-fit rounded-md border border-border px-4 hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {t("cancel")}
        </button>
      </section>
    );
  }

  const submitting = phase.name === "submitting";
  return (
    // method="post": if the page scripts fail to load and the browser submits the
    // form by itself, the password must never end up in the address bar.
    <form
      method="post"
      action="/login"
      onSubmit={(event) => void submit(event)}
      className="flex flex-col gap-4"
      noValidate
    >
      <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
      {failure ? (
        <p
          ref={errorRef}
          role="alert"
          tabIndex={-1}
          className="rounded-md border border-danger px-3 py-2 text-sm text-danger"
        >
          {t(`errors.${failure}`, {
            seconds: phase.name === "form" ? (phase.retryAfter ?? 0) : 0,
          })}
        </p>
      ) : null}
      <label className="flex flex-col gap-1 text-sm font-medium">
        {t("loginLabel")}
        <input
          name="login"
          type="text"
          required
          maxLength={64}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          autoFocus
          readOnly={submitting}
          className={fieldClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        {t("passwordLabel")}
        <input
          ref={passwordRef}
          name="password"
          type="password"
          required
          maxLength={128}
          autoComplete="current-password"
          readOnly={submitting}
          className={fieldClass}
        />
      </label>
      <button
        type="submit"
        disabled={submitting}
        className="h-11 rounded-md bg-primary px-4 font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
      >
        {submitting ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}
