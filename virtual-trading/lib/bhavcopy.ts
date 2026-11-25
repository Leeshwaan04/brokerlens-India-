// Fetches and parses NSE's own public, ungated cash-market bhavcopy, the
// EOD price source for this app's order settlement. Independent of
// pipeline/ at runtime: this hits the same public archive host
// pipeline/sources/nse.py's _bhavcopy_day() already uses
// (nsearchives.nseindia.com, confirmed ungated by that file's own
// docstring), but does not call into pipeline code.
//
// URL pattern, parsing, and the walk-back-a-day-at-a-time behavior for a
// not-yet-published day all mirror _bhavcopy_day() in
// /Users/sumitbagewadi/Documents/Brokerlens-India/pipeline/sources/nse.py.

import { unzipSync } from "fflate";

const ARCH = "https://nsearchives.nseindia.com";
const USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36";

export interface DailyPriceRow {
  symbol: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
  // NSE's previous close (PrvsClsgPric), adjusted on a split or bonus ex-date.
  prevClose: number | null;
}

function dateStamp(date: Date): string {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

export function bhavcopyUrl(date: Date): string {
  return `${ARCH}/content/cm/BhavCopy_NSE_CM_0_0_0_${dateStamp(date)}_F_0000.csv.zip`;
}

function toNum(value: string | undefined): number | null {
  if (value === undefined || value === null || value.trim() === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

// Minimal CSV parser for this specific, well-formed, comma-delimited,
// non-quoted-field bhavcopy format (confirmed against a real downloaded
// file: no embedded commas or quoted fields in any column used here).
function parseCsv(text: string): Record<string, string>[] {
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length === 0) return [];
  const headers = lines[0].split(",");
  const rows: Record<string, string>[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split(",");
    const row: Record<string, string> = {};
    for (let c = 0; c < headers.length; c++) {
      row[headers[c]] = cells[c] ?? "";
    }
    rows.push(row);
  }
  return rows;
}

/**
 * Parses one day's bhavcopy CSV text into equity (SctySrs=='EQ') daily price
 * rows, restricted to symbols in allowedSymbols (if given). Pure and
 * synchronous so it can be unit-tested against a real saved fixture without
 * a network call.
 */
export function parseBhavcopyCsv(csvText: string, allowedSymbols?: ReadonlySet<string>): DailyPriceRow[] {
  const rows = parseCsv(csvText);
  const out: DailyPriceRow[] = [];
  for (const r of rows) {
    if ((r.SctySrs || "").trim() !== "EQ") continue;
    const symbol = (r.TckrSymb || "").trim();
    if (!symbol) continue;
    if (allowedSymbols && !allowedSymbols.has(symbol)) continue;
    const close = toNum(r.ClsPric);
    if (close === null) continue;
    out.push({
      symbol,
      open: toNum(r.OpnPric),
      high: toNum(r.HghPric),
      low: toNum(r.LwPric),
      close,
      volume: toNum(r.TtlTradgVol),
      prevClose: toNum(r.PrvsClsgPric),
    });
  }
  return out;
}

export type BhavcopyFetchResult =
  | { status: "ok"; rows: DailyPriceRow[] }
  | { status: "not_published" }
  | { status: "error"; error: string };

/**
 * Fetches and unzips one day's real bhavcopy from NSE's public archive.
 * Returns {status: "not_published"} on a 404/empty response (non-trading
 * day, or today's close not yet published) rather than throwing, so the
 * caller can walk back a day at a time.
 */
export async function fetchBhavcopy(
  date: Date,
  allowedSymbols?: ReadonlySet<string>,
): Promise<BhavcopyFetchResult> {
  const url = bhavcopyUrl(date);
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

  let unzipped: Record<string, Uint8Array>;
  try {
    unzipped = unzipSync(buf);
  } catch (err) {
    return { status: "error", error: `failed to unzip ${url}: ${err instanceof Error ? err.message : String(err)}` };
  }
  const names = Object.keys(unzipped);
  if (names.length === 0) return { status: "not_published" };
  const csvBytes = unzipped[names[0]];
  const csvText = new TextDecoder("utf-8").decode(csvBytes);
  return { status: "ok", rows: parseBhavcopyCsv(csvText, allowedSymbols) };
}
