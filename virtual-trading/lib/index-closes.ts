// NSE's daily index closes (Nifty 50, Nifty Bank, India VIX and a few more),
// from the same public archive as the price files: one CSV per trading day,
// https://nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv.
//
// Used as market context in the app (the strip under the header, the
// benchmark line on Performance). Indices are not tradable here: they are
// shown for the practice market's date, like every other price.

const ARCH = "https://nsearchives.nseindia.com";
const USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36";

/** Indices kept, by stable key. Matching is on NSE's name, case-insensitive. */
export const TRACKED_INDICES = [
  { key: "nifty50", nseName: "Nifty 50", label: "Nifty 50" },
  { key: "niftybank", nseName: "Nifty Bank", label: "Nifty Bank" },
  { key: "finnifty", nseName: "Nifty Financial Services", label: "Fin Nifty" },
  { key: "midcpnifty", nseName: "Nifty Midcap Select", label: "Midcap Select" },
  { key: "niftynext50", nseName: "Nifty Next 50", label: "Nifty Next 50" },
  { key: "nifty500", nseName: "Nifty 500", label: "Nifty 500" },
  { key: "niftymidcap100", nseName: "Nifty Midcap 100", label: "Midcap 100" },
  { key: "niftysmallcap100", nseName: "Nifty Smallcap 100", label: "Smallcap 100" },
  { key: "indiavix", nseName: "India VIX", label: "India VIX" },
] as const;

export type IndexKey = (typeof TRACKED_INDICES)[number]["key"];

export interface IndexCloseRow {
  indexKey: IndexKey;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  changePct: number | null;
}

const BY_NAME = new Map<string, IndexKey>(TRACKED_INDICES.map((i) => [i.nseName.toLowerCase(), i.key]));

export function indexCloseUrl(date: Date): string {
  const d = String(date.getUTCDate()).padStart(2, "0");
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  return `${ARCH}/content/indices/ind_close_all_${d}${m}${date.getUTCFullYear()}.csv`;
}

function num(value: string | undefined): number | null {
  const t = (value ?? "").trim();
  if (t === "" || t === "-") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** Parses one day's file into the tracked indices only. Pure, for tests. */
export function parseIndexCloseCsv(csvText: string): IndexCloseRow[] {
  const lines = csvText.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  const col = (name: string) => headers.indexOf(name);
  const iName = col("Index Name");
  const iOpen = col("Open Index Value");
  const iHigh = col("High Index Value");
  const iLow = col("Low Index Value");
  const iClose = col("Closing Index Value");
  const iChg = col("Change(%)");
  if (iName < 0 || iClose < 0) return [];
  const out: IndexCloseRow[] = [];
  for (const line of lines.slice(1)) {
    const cells = line.split(",");
    const key = BY_NAME.get((cells[iName] ?? "").trim().toLowerCase());
    const close = num(cells[iClose]);
    if (!key || close === null) continue;
    out.push({ indexKey: key, open: num(cells[iOpen]), high: num(cells[iHigh]), low: num(cells[iLow]), close, changePct: num(cells[iChg]) });
  }
  return out;
}

export type IndexFetchResult =
  | { status: "ok"; rows: IndexCloseRow[] }
  | { status: "not_published" }
  | { status: "error"; error: string };

export async function fetchIndexCloses(date: Date): Promise<IndexFetchResult> {
  const url = indexCloseUrl(date);
  let res: Response;
  try {
    res = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
  } catch (err) {
    return { status: "error", error: err instanceof Error ? err.message : String(err) };
  }
  if (res.status === 404) return { status: "not_published" };
  if (!res.ok) return { status: "error", error: `HTTP ${res.status} from ${url}` };
  const rows = parseIndexCloseCsv(await res.text());
  return rows.length > 0 ? { status: "ok", rows } : { status: "not_published" };
}
