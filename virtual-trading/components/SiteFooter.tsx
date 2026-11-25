import Link from "next/link";
import { AffiliateDisclosure } from "./ui";

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-sub">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-xs text-muted sm:px-6">
        <p>
          A simulation for investor education. Orders here are never sent to an exchange and no real money moves.
          Prices are official NSE closing prices published after the market closes, never live or intraday prices.
          Nothing here is investment advice or a recommendation to buy or sell any security.
        </p>
        <p>
          Broker fees come from the published schedules BrokerLens holds on{" "}
          <a href="https://www.brokerlens.in" className="text-accent-ink underline-offset-2 hover:underline">
            brokerlens.in
          </a>
          . Confirm current charges on the broker&apos;s own site before opening an account.
        </p>
        <AffiliateDisclosure />
        <nav aria-label="Legal" className="flex flex-wrap gap-x-4 gap-y-1">
          <Link href="/privacy" className="text-accent-ink underline-offset-2 hover:underline">
            Privacy notice
          </Link>
          <a href="https://www.brokerlens.in/terms-of-service/" className="text-accent-ink underline-offset-2 hover:underline">
            Terms of service
          </a>
          <a href="https://www.brokerlens.in/" className="text-accent-ink underline-offset-2 hover:underline">
            brokerlens.in
          </a>
        </nav>
      </div>
    </footer>
  );
}
