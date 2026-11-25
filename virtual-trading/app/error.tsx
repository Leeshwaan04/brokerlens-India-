"use client";

import { buttonClass } from "@/components/ui";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-4 py-20 text-center">
      <h1 className="text-2xl font-semibold text-ink">Something went wrong</h1>
      <p className="text-muted">
        This page could not load just now. Your virtual cash, holdings and orders are unaffected. Please try again.
      </p>
      <button type="button" onClick={reset} className={buttonClass("primary")}>
        Try again
      </button>
    </main>
  );
}
