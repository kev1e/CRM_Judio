import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithIntl } from "@/test/render";

import { ApiStatus } from "./api-status";

describe("ApiStatus", () => {
  it.each([
    ["ok", "Сервер работает"],
    ["degraded", "Сервер работает с ошибками"],
    ["unreachable", "Сервер недоступен"],
  ] as const)("shows the Russian text for state %s", (state, text) => {
    renderWithIntl(<ApiStatus state={state} />);

    const status = screen.getByRole("status", { name: "Состояние сервера" });
    expect(status).toHaveTextContent(text);
    expect(status).toHaveAttribute("data-state", state);
  });
});
