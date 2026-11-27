// NSE's older end-of-day file format, served for dates up to 5 Jul 2024 (the
// newer UDiFF format that lib/bhavcopy.ts reads takes over from 2 Jan 2024).
// Together they cover five years of daily history from the same public
// archive. Plain requests, same host and manners as lib/bhavcopy.ts.
//
// https://nsearchives.nseindia.com/content/historical/EQUITIES/2021/JAN/cm04JAN2021bhav.csv.zip
// SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,

import { unzipSync } from "fflate";
import type { DailyPriceRow } from "../bhavcopy";

const ARCH = "https://nsearchives.nseindia.com";
const USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36";
const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

/** Last date this format is published for; later dates use the new format. */
export const OLD_FORMAT_LAST_DATE = "2024-07-05";

export function oldBhavcopyUrl(date: Date): string {
  const y = date.getUTCFullYear();
  const mon = MONTHS[date.getUTCMonth()];
  const dd = String(date.getUTCDate()).padStart(2, "0");
  return `${ARCH}/content/historical/EQUITIES/${y}/${mon}/cm${dd}${mon}${y}bhav.csv.zip`;
}

function num(v: string | undefined): number | null {
  const t = (v ?? "").trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** Equity (EQ) rows of one day's old-format CSV, for the allowed symbols. Pure, for tests. */
export function parseOldBhavcopyCsv(csvText: string, allowedSymbols?: ReadonlySet<string>): DailyPriceRow[] {
  const lines = csvText.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  const col = (n: string) => headers.indexOf(n);
  const [iSym, iSeries, iOpen, iHigh, iLow, iClose, iPrev, iQty] = ["SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE", "TOTTRDQTY"].map(col);
  if (iSym < 0 || iSeries < 0 || iClose < 0) return [];
  const out: DailyPriceRow[] = [];
  for (const line of lines.slice(1)) {
    const c = line.split(",");
    if ((c[iSeries] ?? "").trim() !== "EQ") continue;
    const symbol = (c[iSym] ?? "").trim();
    if (!symbol || (allowedSymbols && !allowedSymbols.has(symbol))) continue;
    const close = num(c[iClose]);
    if (close === null || close <= 0) continue;
    out.push({
      symbol,
      open: num(c[iOpen]),
      high: num(c[iHigh]),
      low: num(c[iLow]),
      close,
      volume: num(c[iQty]),
      prevClose: num(c[iPrev]),
    });
  }
  return out;
}

export type OldFetchResult =
  | { status: "ok"; rows: DailyPriceRow[] }
  | { status: "not_published" }
  | { status: "error"; error: string };

export async function fetchOldBhavcopy(date: Date, allowedSymbols?: ReadonlySet<string>): Promise<OldFetchResult> {
  const url = oldBhavcopyUrl(date);
  let res: Response;
  try {
    res = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
  } catch (err) {
    return { status: "error", error: err instanceof Error ? err.message : String(err) };
  }
  if (res.status === 404) return { status: "not_published" };
  if (!res.ok) return { status: "error", error: `HTTP ${res.status} from ${url}` };
  const buf = new Uint8Array(await res.arrayBuffer());
  if (buf.byteLength === 0) return { status: "not_published" };
  let files: Record<string, Uint8Array>;
  try {
    files = unzipSync(buf);
  } catch (err) {
    return { status: "error", error: `failed to unzip ${url}: ${err instanceof Error ? err.message : String(err)}` };
  }
  const first = Object.values(files)[0];
  if (!first) return { status: "not_published" };
  const rows = parseOldBhavcopyCsv(new TextDecoder("utf-8").decode(first), allowedSymbols);
  return rows.length > 0 ? { status: "ok", rows } : { status: "not_published" };
}
