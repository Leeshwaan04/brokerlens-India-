import { getHolidaySet, longDate, marketMoment, PHASE_LABEL } from "@/lib/market-clock";
import { cx } from "./ui";

// The practice market's date and session, always in view: with a lag, the
// date here is weeks behind the real one, and that must never be a surprise.
export async function MarketClock({ className }: { className?: string }) {
  const m = marketMoment(await getHolidaySet());
  const title =
    m.lagDays > 0
      ? `The practice market runs ${m.lagDays} days behind the real one, so every price here is at least ${m.lagDays} days old.`
      : "The practice market follows the real calendar, with official closes published each evening.";
  return (
    <span
      title={title}
      className={cx("inline-flex items-center gap-1.5 rounded-full border border-line bg-sub px-2.5 py-1 text-xs text-muted", className)}
    >
      <span
        aria-hidden
        className={cx("h-1.5 w-1.5 rounded-full", m.phase === "open" ? "bg-up" : m.phase === "pre_open" ? "bg-warn" : "bg-faint")}
      />
      <span>
        {m.lagDays > 0 ? "Practice market" : "Market"}: <span className="font-medium text-ink">{longDate(m.date)}</span>,{" "}
        {PHASE_LABEL[m.phase]}
      </span>
    </span>
  );
}
