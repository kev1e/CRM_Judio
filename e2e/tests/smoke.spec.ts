import { expect, test } from "@playwright/test";

const apiURL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";

test.describe("sign-in page", () => {
  test("an anonymous visitor is sent to the Russian login page", async ({ page }) => {
    const response = await page.goto("/");

    expect(response?.status()).toBe(200);
    await expect(page).toHaveURL(/\/login$/);
    await expect(page).toHaveTitle("CRM");
    await expect(page.locator("html")).toHaveAttribute("lang", "ru");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Вход в CRM");
    await expect(page.getByLabel("Логин")).toBeFocused();
  });

  test("wrong credentials get one generic message and stay out of the address", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByLabel("Логин").fill("no.such.user");
    await page.getByLabel("Пароль").fill("definitely-not-the-password");
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(page.locator("p[role=alert]")).toHaveText("Неверный логин или пароль.");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByLabel("Пароль")).toHaveValue("");
    expect((await page.context().cookies()).map((cookie) => cookie.name)).toEqual([]);
  });

  test("the form can be submitted from the keyboard", async ({ page }) => {
    await page.goto("/login");
    await page.keyboard.type("no.such.user.keyboard");
    await page.keyboard.press("Tab");
    await page.keyboard.type("definitely-not-the-password");
    await page.keyboard.press("Enter");

    await expect(page.locator("p[role=alert]")).toBeFocused();
  });

  test("switches the theme and keeps it after a reload", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/login");
    const html = page.locator("html");
    await expect(html).not.toHaveClass(/dark/);

    await page.getByRole("button", { name: "Включить тёмную тему" }).click();
    await expect(html).toHaveClass(/dark/);

    await page.reload();
    await expect(html).toHaveClass(/dark/);

    await page.getByRole("button", { name: "Включить светлую тему" }).click();
    await expect(html).not.toHaveClass(/dark/);
  });

  test("fits a phone screen without sideways scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 640 });
    await page.goto("/login");

    const overflows = await page.evaluate<boolean>(
      "document.documentElement.scrollWidth > window.innerWidth",
    );
    expect(overflows).toBe(false);
    await expect(page.getByRole("button", { name: "Войти" })).toBeInViewport();
  });

  test("sends security headers and does not advertise the framework", async ({ request }) => {
    const response = await request.get("/");
    const headers = response.headers();

    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["x-powered-by"]).toBeUndefined();
  });

  test("web liveness endpoint answers", async ({ request }) => {
    const response = await request.get("/healthz");

    expect(response.status()).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
  });
});

test.describe("api through the web origin", () => {
  test("refuses requests without a session", async ({ request }) => {
    const response = await request.get("/api/v1/auth/me");

    expect(response.status()).toBe(401);
    expect((await response.json()).error.code).toBe("not_authenticated");
  });

  test("refuses a state-changing request that claims another origin", async ({ request }) => {
    const response = await request.post("/api/v1/auth/login", {
      headers: { Origin: "https://evil.example" },
      data: { login: "no.such.user", password: "definitely-not-the-password" },
    });

    expect(response.status()).toBe(403);
    expect((await response.json()).error.code).toBe("csrf_failed");
  });

  test("does not relay paths outside the API", async ({ request }) => {
    const response = await request.get("/api/v1/..%2F..%2Fadmin");

    expect(response.status()).toBe(404);
  });
});

test.describe("api", () => {
  test("is ready with PostgreSQL and Redis", async ({ request }) => {
    const response = await request.get(`${apiURL}/api/v1/ready`);

    expect(response.status()).toBe(200);
    expect(await response.json()).toEqual({
      status: "ok",
      checks: { database: "ok", redis: "ok" },
    });
  });

  test("answers unknown routes with the error envelope and no internals", async ({ request }) => {
    const response = await request.get(`${apiURL}/api/v1/does-not-exist`);

    expect(response.status()).toBe(404);
    expect(await response.json()).toEqual({
      error: { code: "not_found", message: "Not found.", details: null },
    });
  });
});

test("unknown page answers 404 in Russian", async ({ page }) => {
  const response = await page.goto("/no-such-page");

  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Страница не найдена");
});
