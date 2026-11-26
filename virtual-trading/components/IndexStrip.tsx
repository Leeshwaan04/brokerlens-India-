import { getIndexStrip } from "@/lib/index-data";
import { longDate } from "@/lib/market-clock";
import { signedPct, pnlTone } from "@/lib/format";
import { cx } from "./ui";

const LEVEL = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// The market's mood on the practice date: Nifty 50, Nifty Bank and a few
// more, so a user can tell whether a stock moved with the market or against
// it. Context only (indices cannot be traded here). Scrolls sideways on a
// phone instead of wrapping into a tall block.
export async function IndexStrip() {
  const strip = await getIndexStrip();
  if (!strip) return null;
  return (
    <div className="border-b border-line bg-sub/60">
      <div
        role="group"
        aria-label={`Index closes on ${longDate(strip.date)}`}
        className="mx-auto flex max-w-6xl items-center gap-x-6 overflow-x-auto px-4 py-1.5 text-xs sm:px-6"
      >
        {strip.items.map((i) => (
          <span key={i.key} className="flex shrink-0 items-baseline gap-1.5 whitespace-nowrap">
            <span className="text-muted">{i.label}</span>
            <span className="num font-medium text-ink">{LEVEL.format(i.close)}</span>
            {i.changePct !== null && (
              // A rise in the volatility index is fear, not good news: no green or red for it.
              <span className={cx("num", i.key === "indiavix" ? "text-muted" : pnlTone(i.changePct))}>{signedPct(i.changePct)}</span>
            )}
          </span>
        ))}
        <span className="ml-auto hidden shrink-0 text-faint sm:inline">NSE close, {longDate(strip.date)}</span>
      </div>
    </div>
  );
}
