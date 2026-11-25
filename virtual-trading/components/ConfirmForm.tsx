"use client";

import { useActionState, useId } from "react";
import type { ConfirmActionState } from "@/app/(app)/actions";
import { buttonClass, cx } from "./ui";

// A destructive action that only runs after the user types a word. The
// server action checks the word too; this just makes the intent explicit.
export function ConfirmForm({
  action,
  word,
  buttonLabel,
  danger = false,
}: {
  action: (prev: ConfirmActionState, fd: FormData) => Promise<ConfirmActionState>;
  word: string;
  buttonLabel: string;
  danger?: boolean;
}) {
  const id = useId();
  const initial: ConfirmActionState = { status: "idle", message: "" };
  const [state, formAction, pending] = useActionState(action, initial);
  return (
    <form action={formAction} className="flex flex-wrap items-end gap-3">
      <label htmlFor={id} className="flex flex-col gap-1 text-sm">
        <span className="text-muted">
          Type <span className="font-mono font-semibold text-ink">{word}</span> to confirm
        </span>
        <input
          id={id}
          name="confirm"
          autoComplete="off"
          className="w-40 rounded-lg border border-line-strong bg-raised px-3 py-2 text-ink focus:border-accent focus:outline-none"
        />
      </label>
      <button type="submit" disabled={pending} className={cx(buttonClass(danger ? "danger" : "secondary"))}>
        {pending ? "Working" : buttonLabel}
      </button>
      {state.status === "error" && (
        <p role="alert" className="w-full text-sm text-down">
          {state.message}
        </p>
      )}
    </form>
  );
}
