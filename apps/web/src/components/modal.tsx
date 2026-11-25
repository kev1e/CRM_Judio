"use client";

import { type ReactNode, useEffect, useRef } from "react";

/**
 * A modal window on the native <dialog>: the browser traps focus inside it,
 * closes it on Escape and returns focus to where it was.
 */
export function Modal({
  labelledBy,
  onClose,
  children,
}: {
  labelledBy: string;
  /** Called when the user asks to close (Escape, backdrop). Return false to keep it open. */
  onClose: () => boolean | void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || dialog.open) {
      return;
    }
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby={labelledBy}
      onCancel={(event) => {
        // A file field inside the window sends its own "cancel" when the file
        // chooser is dismissed; only the window's own Escape closes it.
        if (event.target !== ref.current) {
          return;
        }
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) {
          onClose();
        }
      }}
      className="m-auto max-h-[calc(100dvh-2rem)] w-[min(44rem,calc(100vw-2rem))] overflow-y-auto rounded-lg border border-border bg-background p-0 text-foreground backdrop:bg-black/50"
    >
      <div className="flex flex-col gap-5 p-5">{children}</div>
    </dialog>
  );
}
