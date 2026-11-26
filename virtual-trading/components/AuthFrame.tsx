import Link from "next/link";
import type { ReactNode } from "react";
import { AppHeader } from "./AppHeader";
import { SiteFooter } from "./SiteFooter";

const POINTS = [
  "₹10 lakh of virtual cash, Nifty 500 stocks",
  "Every charge shown before you place an order",
  "Replay your trades at every broker to see who is cheapest for you",
];

export function AuthFrame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <AppHeader signedIn={false} />
      <main className="mx-auto grid w-full max-w-5xl flex-1 items-center gap-10 px-4 py-12 sm:px-6 md:grid-cols-2">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-ink">{title}</h1>
          <ul className="mt-5 flex flex-col gap-3">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-3 text-muted">
                <span aria-hidden="true" className="mt-1 h-2 w-2 shrink-0 rounded-full bg-up" />
                {p}
              </li>
            ))}
          </ul>
          <p className="mt-6 text-xs text-faint">
            A simulation for investor education. No real money moves. By creating an account you agree to the{" "}
            <a href="https://www.brokerlens.in/terms-of-service/" className="underline underline-offset-2">
              terms of service
            </a>{" "}
            and the{" "}
            <Link href="/privacy" className="underline underline-offset-2">
              privacy notice
            </Link>
            .
          </p>
        </div>
        <div className="flex justify-center md:justify-end">{children}</div>
      </main>
      <SiteFooter />
    </>
  );
}
