// Health of the practice market's price supply, for /api/health and the
// uptime workflow.
//
// The practice market shows closes VT_PRICE_LAG_DAYS behind the real date, so
// closes already stored are a buffer: with the newest close on file from
// `latestClose`, the practice market reaches it in `lag - (today -
// latestClose)` days. New closes are fetched from a machine NSE serves
// normally (NSE refuses GitHub's runners; see LAUNCH.md step 10), so this
// buffer shrinking is the early warning that fetching has stopped.

/** Below this many days of stored closes ahead of the practice market, warn. */
export const MIN_PRICE_RUNWAY_DAYS = 10;

const DAY_MS = 86_400_000;

function utcMidnight(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

/** Calendar days until the practice market reaches the newest stored close (negative once past it). */
export function priceRunwayDays(latestClose: string, todayIst: string, lagDays: number): number {
  return lagDays - Math.round((utcMidnight(todayIst) - utcMidnight(latestClose)) / DAY_MS);
}

export function priceSupplyStatus(runway: number | null): "ok" | "low" {
  return runway !== null && runway >= MIN_PRICE_RUNWAY_DAYS ? "ok" : "low";
}
