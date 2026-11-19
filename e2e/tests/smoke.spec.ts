import { expect, test } from "@playwright/test";

const apiURL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";

test.describe("web placeholder", () => {
  test("opens in Russian and shows that the API is ready", async ({ page }) => {
    const response = await page.goto("/");

    expect(response?.status()).toBe(200);
    await expect(page).toHaveTitle("CRM");
    await expect(page.locator("html")).toHaveAttribute("lang", "ru");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Система разворачивается");
    await expect(page.getByRole("status", { name: "Состояние сервера" })).toHaveText(
      "Сервер работает",
    );
  });

  test("switches the theme and keeps it after a reload", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    const html = page.locator("html");
    await expect(html).not.toHaveClass(/dark/);

    await page.getByRole("button", { name: "Включить тёмную тему" }).click();
    await expect(html).toHaveClass(/dark/);

    await page.reload();
    await expect(html).toHaveClass(/dark/);

    await page.getByRole("button", { name: "Включить светлую тему" }).click();
    await expect(html).not.toHaveClass(/dark/);
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
