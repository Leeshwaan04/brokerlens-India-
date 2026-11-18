// One-off manual seed for Slice 1 local testing only. Run with
// `npm run seed:slice1` against a real DATABASE_URL. Inserts:
//   - the 3 sample brokers in seed/broker-rates.sample.json (real, published
//     BrokerLens figures for Zerodha, 5paisa and Upstox, copied by hand from
//     pipeline/trade_cost_engine.py's BROKER_RATES)
//   - 5 real NSE symbols with ONE manually-set sample closing price each,
//     clearly not a real market feed (Slice 2 replaces this with the real
//     NSE bhavcopy sync)
//   - the 2026 NSE trading holiday list is NOT seeded here; add real dates
//     to market_holidays before relying on cutoff/target-date logic for
//     anything beyond a same-day manual test.
import { getDb } from "../lib/db";
import { brokerCatalog, stockUniverse, dailyPrices } from "../lib/schema";
import sampleBrokers from "../seed/broker-rates.sample.json";

// SAMPLE PRICES for Slice 1 manual testing only. Slice 2 replaces this table
// entirely with real closes ingested from NSE's own public bhavcopy archive.
// Real company names and real symbols; the price figures below are not from
// any market data source and must never be shown to an end user as real.
const SAMPLE_STOCKS = [
  { symbol: "RELIANCE", name: "Reliance Industries Ltd", isin: "INE002A01018", samplePrice: 1400.0 },
  { symbol: "TCS", name: "Tata Consultancy Services Ltd", isin: "INE467B01029", samplePrice: 4100.0 },
  { symbol: "INFY", name: "Infosys Ltd", isin: "INE009A01021", samplePrice: 1850.0 },
  { symbol: "HDFCBANK", name: "HDFC Bank Ltd", isin: "INE040A01034", samplePrice: 1750.0 },
  { symbol: "ICICIBANK", name: "ICICI Bank Ltd", isin: "INE090A01021", samplePrice: 1280.0 },
];

async function main() {
  const db = getDb();
  const today = new Date().toISOString().slice(0, 10);

  for (const b of sampleBrokers) {
    await db
      .insert(brokerCatalog)
      .values({
        id: b.id,
        brand: b.brand,
        tagline: b.tagline,
        deliveryFlat: String(b.delivery_flat),
        deliveryPct: String(b.delivery_pct),
        intradayFlat: String(b.intraday_flat),
        intradayPct: String(b.intraday_pct),
        dpCharge: String(b.dp_charge),
        dematAmc: String(b.demat_amc),
        accountOpen: String(b.account_open),
        ctaUrl: b.cta_url,
        partnerBadge: b.partner_badge,
        syncedAt: new Date(),
      })
      .onConflictDoUpdate({
        target: brokerCatalog.id,
        set: { syncedAt: new Date() },
      });
  }

  for (const s of SAMPLE_STOCKS) {
    await db
      .insert(stockUniverse)
      .values({ symbol: s.symbol, name: s.name, isin: s.isin, indexMembership: ["NIFTY100"] })
      .onConflictDoNothing({ target: stockUniverse.symbol });

    await db
      .insert(dailyPrices)
      .values({ symbol: s.symbol, tradeDate: today, close: String(s.samplePrice) })
      .onConflictDoNothing();
  }

  console.log(`Seeded ${sampleBrokers.length} brokers and ${SAMPLE_STOCKS.length} sample stocks/prices for ${today}.`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
