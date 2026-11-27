"use client";

import Link from "next/link";
import { useActionState, useEffect, type ReactNode } from "react";
import { buttonClass, cx } from "./ui";

export type OnboardingState = { status: "idle" } | { status: "done" } | { status: "error"; message: string };

// The broker choice that opens a practice account. The server action only
// creates the account and answers; this form then loads the dashboard as a
// full page, so arriving there never depends on an in-app redirect finishing
// over a slow connection. While it works the button says so and cannot be
// pressed again.
export function OnboardingForm({
  action,
  nextPath,
  children,
}: {
  action: (prev: OnboardingState, fd: FormData) => Promise<OnboardingState>;
  /** Already checked server-side (lib/next-path.ts): a path inside this app. */
  nextPath: string;
  children: ReactNode;
}) {
  const [state, formAction, pending] = useActionState(action, { status: "idle" } as OnboardingState);
  const done = state.status === "done";

  useEffect(() => {
    // Deliberately a full page load, not router.push: the in-app redirect is
    // what failed for a real user on a slow connection (26 Nov 2026).
    if (done) window.location.assign(nextPath);
  }, [done, nextPath]);

  return (
    <form action={formAction} className="mt-8 flex flex-col gap-8">
      {children}
      <div className="sticky bottom-0 -mx-4 flex flex-col gap-2 border-t border-line bg-bg/95 px-4 py-4 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
        <button
          type="submit"
          disabled={pending || done}
          aria-busy={pending || done}
          className={cx(buttonClass("primary"), "w-full py-3 text-base sm:w-auto sm:self-start")}
        >
          {done ? "Opening your account…" : pending ? "Setting up your account…" : "Start with ₹10,00,000 of virtual cash"}
        </button>
        {state.status === "error" && (
          <p role="alert" className="text-sm text-down">
            {state.message}
          </p>
        )}
        {done && (
          <p className="text-sm text-muted">
            Your account is ready. If the next page does not open, <Link className="text-accent-ink underline" href={nextPath}>continue here</Link>.
          </p>
        )}
      </div>
    </form>
  );
}
