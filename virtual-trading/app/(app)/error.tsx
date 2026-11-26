"use client";

import Link from "next/link";
import { buttonClass } from "@/components/ui";

// A signed-in page that failed to load keeps the app's header and footer, and
// offers a retry and a way back, instead of replacing the whole app.
export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-4 py-16 text-center">
      <h1 className="text-2xl font-semibold text-ink">This page did not load</h1>
      <p className="text-muted">
        Usually a dropped connection. Your virtual cash, holdings and orders are unaffected.
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        <button type="button" onClick={reset} className={buttonClass("primary")}>
          Try again
        </button>
        <Link href="/dashboard" className={buttonClass("secondary")}>
          Go to the dashboard
        </Link>
      </div>
    </div>
  );
}
