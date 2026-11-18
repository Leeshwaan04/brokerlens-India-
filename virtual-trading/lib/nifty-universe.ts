// Fetches and parses NSE's own public Nifty 100 constituent list, the
// starter stock universe for this MVP (plan section "Stock universe").
// Same archive host and INDEX_FILES pattern as
// /Users/sumitbagewadi/Documents/Brokerlens-India/pipeline/sources/nse.py's
// index_universe(), but fetched independently, not via pipeline/.

const ARCH = "https://nsearchives.nseindia.com";
const USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36";

export const NIFTY_100_URL = `${ARCH}/content/indices/ind_nifty100list.csv`;

export interface UniverseRow {
  symbol: string;
  name: string;
  isin: string | null;
}

// Minimal CSV parser for this file's shape. The real file has no embedded
// commas (company names use "&" and "." but never ","), confirmed against
// a real downloaded copy before writing this.
function parseCsv(text: string): Record<string, string>[] {
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length === 0) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows: Record<string, string>[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split(",");
    const row: Record<string, string> = {};
    for (let c = 0; c < headers.length; c++) {
      row[headers[c]] = (cells[c] ?? "").trim();
    }
    rows.push(row);
  }
  return rows;
}

/**
 * Parses NSE's "Company Name,Industry,Symbol,Series,ISIN Code" constituent
 * CSV into stock_universe rows. Pure and synchronous so it can be
 * unit-tested against a real saved fixture without a network call.
 */
export function parseNifty100Csv(csvText: string): UniverseRow[] {
  const rows = parseCsv(csvText);
  const out: UniverseRow[] = [];
  for (const r of rows) {
    const symbol = r["Symbol"];
    if (!symbol) continue;
    out.push({
      symbol,
      name: r["Company Name"] || symbol,
      isin: r["ISIN Code"] || null,
    });
  }
  return out;
}

export async function fetchNifty100(): Promise<UniverseRow[]> {
  const res = await fetch(NIFTY_100_URL, { headers: { "User-Agent": USER_AGENT } });
  if (!res.ok) {
    throw new Error(`Failed to fetch Nifty 100 constituent list: HTTP ${res.status} from ${NIFTY_100_URL}`);
  }
  const text = await res.text();
  return parseNifty100Csv(text);
}
