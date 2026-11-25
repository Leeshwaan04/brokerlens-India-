import { AffiliateDisclosure } from "./ui";

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-sub">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-xs text-muted sm:px-6">
        <p>
          A simulation for investor education. Orders here are never sent to an exchange and no real money moves.
          Prices are official NSE closing prices, delayed by at least a day, in line with SEBI&apos;s rules on
          real-time price data for investor-education platforms. Nothing here is investment advice or a
          recommendation to buy or sell any security.
        </p>
        <p>
          Broker fees come from the published schedules BrokerLens holds on{" "}
          <a href="https://www.brokerlens.in" className="text-accent-ink underline-offset-2 hover:underline">
            brokerlens.in
          </a>
          . Confirm current charges on the broker&apos;s own site before opening an account.
        </p>
        <AffiliateDisclosure />
      </div>
    </footer>
  );
}
