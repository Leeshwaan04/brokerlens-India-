import { MIS_MARGIN_PCT } from "@/lib/fills";

// The rules every practice order is filled by. One source, shown on the
// Orders page and on the public How it works page, so they cannot drift.
export function FillRules() {
  return (
    <>
          <p className="mt-2 text-sm text-muted">
            This practice market has each session&apos;s official open, high, low and close, not every trade during the day,
            so these rules never assume prices moved in your favour.
          </p>
          <ul className="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted">
            <li>An order placed before the session opens (the evening before, over a weekend, or before 9:15) can fill at the open. Placed during the session, a market order fills at the close.</li>
            <li>A limit order fills only if the price traded through your limit, not if it merely touched it, and never at a worse price than your limit.</li>
            <li>A stop-loss order turns into a market order when its trigger trades. If the session opens beyond the trigger, it fills at that worse opening price.</li>
            <li>Placed during the session, a limit or stop order that was already executable fills at the close; otherwise at its limit or trigger.</li>
            <li>A day order that does not fill ends with its session. A GTT order is checked every session for up to a year.</li>
            <li>Open orders are cancelled on a split or bonus ex-date, as brokers do when the share count changes.</li>
            <li>
              Intraday (MIS) positions open and close in one session on {Math.round(MIS_MARGIN_PCT * 100)}% margin. An intraday
              market order must be in before the session opens and enters at the open. A stop-loss or target exits the position
              if the day&apos;s range reached it, and if it reached both, the stop is assumed to have come first. Anything still
              open is squared off at the close. Intraday charges apply: STT 0.025% on the sell leg, stamp duty 0.003% on the buy leg.
            </li>
          </ul>
    </>
  );
}
