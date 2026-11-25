import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "./modal";

describe("Modal", () => {
  it("closes on its own cancel (Escape)", () => {
    const onClose = vi.fn();
    render(
      <Modal labelledBy="title" onClose={onClose}>
        <h2 id="title">Задача</h2>
      </Modal>,
    );

    fireEvent(screen.getByRole("dialog", { hidden: true }), new Event("cancel", { bubbles: true }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stays open when a file field inside it reports a dismissed file chooser", () => {
    const onClose = vi.fn();
    render(
      <Modal labelledBy="title" onClose={onClose}>
        <h2 id="title">Задача</h2>
        <input type="file" aria-label="Файл" />
      </Modal>,
    );

    fireEvent(screen.getByLabelText("Файл"), new Event("cancel", { bubbles: true }));

    expect(onClose).not.toHaveBeenCalled();
  });
});
