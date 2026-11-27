import { istDate, istMidnight, istMinuteOfDay, mondayOf } from "./time";
import { Bar, NSE_EQUITY_SESSION, SessionSpec, TIMEFRAME_MINUTES, Timeframe, isIntraday } from "./types";

/** Merge consecutive bars that share a key into one OHLCV bar. Input must be ascending. */
function aggregate(bars: Bar[], keyOf: (b: Bar) => string, startOf: (b: Bar, key: string) => number): Bar[] {
  const out: Bar[] = [];
  let key = "";
  for (const b of bars) {
    const k = keyOf(b);
    const last = out[out.length - 1];
    if (last && k === key) {
      last.h = Math.max(last.h, b.h);
      last.l = Math.min(last.l, b.l);
      last.c = b.c;
      last.v += b.v;
    } else {
      out.push({ t: startOf(b, k), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v });
      key = k;
    }
  }
  return out;
}

/** Daily bars to weekly (Monday to Friday of each IST week) or monthly. A bar opens at its first session. */
export function resampleDaily(daily: Bar[], to: "D" | "W" | "M"): Bar[] {
  if (to === "D") return daily.map((b) => ({ ...b }));
  if (to === "W") return aggregate(daily, (b) => mondayOf(istDate(b.t)), (b) => b.t);
  return aggregate(daily, (b) => istDate(b.t).slice(0, 7), (b) => b.t);
}

/**
 * One-minute bars to any timeframe. Intraday buckets are aligned to the
 * session open (09:15), the way Indian terminals draw them: 1H bars start
 * 09:15, 10:15 ... and the last one runs only 15 minutes; 4H bars are
 * 09:15 to 13:15 and 13:15 to the close. Bars outside the session
 * (pre-open, post-close) are dropped.
 */
export function resampleIntraday(oneMinute: Bar[], to: Timeframe, session: SessionSpec = NSE_EQUITY_SESSION): Bar[] {
  const inSession = oneMinute.filter((b) => {
    const m = istMinuteOfDay(b.t);
    return m >= session.openMin && m < session.closeMin;
  });
  if (!isIntraday(to)) return resampleDaily(aggregate(inSession, (b) => istDate(b.t), (b) => istMidnight(istDate(b.t))), to as "D" | "W" | "M");
  const n = TIMEFRAME_MINUTES[to];
  if (n === 1) return inSession.map((b) => ({ ...b }));
  const bucketStartMin = (b: Bar) => session.openMin + Math.floor((istMinuteOfDay(b.t) - session.openMin) / n) * n;
  return aggregate(
    inSession,
    (b) => `${istDate(b.t)}#${bucketStartMin(b)}`,
    (b) => istMidnight(istDate(b.t)) + bucketStartMin(b) * 60,
  );
}
