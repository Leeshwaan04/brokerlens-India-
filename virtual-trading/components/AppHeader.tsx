import Link from "next/link";
import { UserButton } from "@clerk/nextjs";
import { isDevAuth } from "@/lib/session";
import { LensMark } from "./LensMark";
import { MarketClock } from "./MarketClock";
import { NavLinks } from "./NavLinks";
import { buttonClass, Pill } from "./ui";

export function AppHeader({
  signedIn,
  brokerBrand,
  showNav = true,
}: {
  signedIn: boolean;
  brokerBrand?: string | null;
  showNav?: boolean;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-raised/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href={signedIn ? "/dashboard" : "/"} className="flex items-center gap-2.5 text-ink">
          <LensMark />
          <span className="font-semibold tracking-tight">BrokerLens</span>
          <span className="hidden text-sm text-muted md:inline">Virtual Trading</span>
        </Link>

        <div className="ml-auto flex items-center gap-3 md:order-last">
          {signedIn ? (
            <>
              <MarketClock />
              {brokerBrand && (
                <Link href="/broker" className="hidden text-sm text-muted hover:text-ink sm:inline" title="Change practice broker">
                  Practising with <span className="font-medium text-ink">{brokerBrand}</span>
                </Link>
              )}
              <Link href="/account" className="text-sm text-muted hover:text-ink">
                Account
              </Link>
              {isDevAuth() ? <Pill tone="warn">Local dev mode</Pill> : <UserButton />}
            </>
          ) : (
            <>
              <Link href="/sign-in" className={buttonClass("ghost", "sm")}>
                Sign in
              </Link>
              <Link href="/sign-up" className={buttonClass("primary", "sm")}>
                Start practising
              </Link>
            </>
          )}
        </div>

        {signedIn && showNav && (
          <div className="order-last w-full md:order-none md:w-auto md:flex-1">
            <NavLinks />
          </div>
        )}
      </div>
    </header>
  );
}
