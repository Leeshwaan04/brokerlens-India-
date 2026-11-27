// India time (IST, UTC+5:30, no daylight saving). Bars carry epoch seconds;
// everything calendar-shaped (which day, which week, which minute of the
// session) is computed in IST, because that is the exchange's clock.
export const IST_OFFSET_SEC = 5.5 * 3600;

const pad = (n: number) => String(n).padStart(2, "0");

/** Epoch seconds shifted so that UTC getters read India time. */
const istShift = (t: number) => new Date((t + IST_OFFSET_SEC) * 1000);

/** "YYYY-MM-DD" of an instant, in India time. */
export function istDate(t: number): string {
  const d = istShift(t);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** Minutes after midnight, India time. */
export function istMinuteOfDay(t: number): number {
  const d = istShift(t);
  return d.getUTCHours() * 60 + d.getUTCMinutes();
}

/** Epoch seconds of 00:00 IST on a "YYYY-MM-DD" date. */
export function istMidnight(date: string): number {
  const [y, m, d] = date.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 1000 - IST_OFFSET_SEC;
}

/** The Monday of the week containing a "YYYY-MM-DD" date. */
export function mondayOf(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const back = (dt.getUTCDay() + 6) % 7; // Monday = 0
  dt.setUTCDate(dt.getUTCDate() - back);
  return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
}
