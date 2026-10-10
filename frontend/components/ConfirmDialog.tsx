"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui";

/**
 * The app's own "Are you sure?" modal, used instead of the browser's confirm() pop-up
 * (eslint's no-alert rule keeps those out). Any component can ask:
 *
 *   const confirm = useConfirm();
 *   if (!(await confirm({ title: "Delete this job?", message: "...", confirmLabel: "Delete job", danger: true }))) return;
 *
 * It resolves true for the confirm button and false for Cancel, Esc or a click outside
 * the card. Risky actions (danger) put the focus on Cancel, so pressing Enter by habit
 * never deletes anything.
 */

export type ConfirmOptions = {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

type Ask = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<Ask | null>(null);

export function useConfirm(): Ask {
  const ask = useContext(ConfirmContext);
  if (ask === null) throw new Error("useConfirm must be used inside <ConfirmProvider>.");
  return ask;
}

type Pending = ConfirmOptions & { resolve: (answer: boolean) => void };

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const returnFocusTo = useRef<HTMLElement | null>(null);

  const ask = useCallback<Ask>(
    (options) =>
      new Promise<boolean>((resolve) => {
        returnFocusTo.current = document.activeElement as HTMLElement | null;
        setPending({ ...options, resolve });
      }),
    [],
  );

  const close = useCallback(
    (answer: boolean) => {
      pending?.resolve(answer);
      setPending(null);
      returnFocusTo.current?.focus();
    },
    [pending],
  );

  // While open: Esc cancels, Tab stays inside the dialog, and the safe button has focus.
  useEffect(() => {
    if (pending === null) return;
    (pending.danger ? cancelRef : confirmRef).current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(false);
      } else if (event.key === "Tab") {
        const buttons = [cancelRef.current, confirmRef.current].filter(Boolean) as HTMLElement[];
        const index = buttons.indexOf(document.activeElement as HTMLElement);
        event.preventDefault();
        buttons[(index + (event.shiftKey ? buttons.length - 1 : 1)) % buttons.length]?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [pending, close]);

  return (
    <ConfirmContext.Provider value={ask}>
      {children}
      {pending && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4 backdrop-blur-[1px] print:hidden"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) close(false); // click outside the card
          }}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby={pending.message ? "confirm-message" : undefined}
            className={`w-full max-w-md rounded-lg border bg-surface p-6 shadow-xl ${
              pending.danger ? "border-not-verified/40" : "border-line"
            }`}
          >
            <h2 id="confirm-title" className="font-display text-xl text-ink">
              {pending.title}
            </h2>
            {pending.message && (
              <div id="confirm-message" className="mt-2 text-sm leading-relaxed text-ink-soft">
                {pending.message}
              </div>
            )}
            <div className="mt-6 flex justify-end gap-2">
              <Button ref={cancelRef} onClick={() => close(false)}>
                {pending.cancelLabel ?? "Cancel"}
              </Button>
              <Button
                ref={confirmRef}
                variant={pending.danger ? "danger" : "primary"}
                onClick={() => close(true)}
                className={pending.danger ? "bg-not-verified text-surface hover:bg-not-verified hover:opacity-90" : ""}
              >
                {pending.confirmLabel ?? "Continue"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
