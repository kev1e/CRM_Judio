import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithIntl } from "@/test/render";

import { ThemeProvider } from "./theme-provider";
import { ThemeToggle } from "./theme-toggle";

function renderToggle() {
  return renderWithIntl(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
}

describe("ThemeToggle", () => {
  it("switches to the dark theme and back, updating its label", async () => {
    const user = userEvent.setup();
    renderToggle();

    await user.click(await screen.findByRole("button", { name: "Включить тёмную тему" }));
    expect(document.documentElement).toHaveClass("dark");

    await user.click(await screen.findByRole("button", { name: "Включить светлую тему" }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(screen.getByRole("button", { name: "Включить тёмную тему" })).toBeInTheDocument();
  });

  it("remembers the chosen theme in the browser", async () => {
    const user = userEvent.setup();
    renderToggle();

    await user.click(await screen.findByRole("button", { name: "Включить тёмную тему" }));

    expect(window.localStorage.getItem("theme")).toBe("dark");
  });
});
