import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { and, asc, desc, eq, inArray, lte } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getAccountSummary } from "@/lib/account-summary";
import { getDb } from "@/lib/db";
import { dailyPrices, marketHolidays, stockUniverse, watchlistItems } from "@/lib/schema";
import { closesWithChange } from "@/lib/prices";
import { getRankableBrokers, toReplayBroker } from "@/lib/brokers";
import { targetTradeDateFor } from "@/lib/market-calendar";
import { marketMoment, marketNow } from "@/lib/market-clock";
import { inr, shortDate, signedPct, pnlTone } from "@/lib/format";
import { StockSearch } from "@/components/StockSearch";
import { OrderTicket } from "@/components/OrderTicket";
import { PendingOrders } from "@/components/PendingOrders";
import { PriceChart } from "@/components/PriceChart";
import { TradeHotkeys } from "@/components/TradeHotkeys";
import { buttonClass, Card, CardTitle, cx, PageHeader, Pill } from "@/components/ui";
import { toggleWatchlistAction } from "../actions";

export const metadata: Metadata = { title: "Trade" };

// Well-known large caps to start from, shown only if present in the synced
// Nifty 100 universe. Symbols, not prices: every figure shown is from the
// ingested NSE closes.
const POPULAR = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC", "LT", "HINDUNILVR", "KOTAKBANK", "AXISBANK"];

function Change({ close, prevClose }: { close: number; prevClose: number | null }) {
  if (prevClose === null || prevClose <= 0) return null;
  const pct = ((close - prevClose) / prevClose) * 100;
  return <span className={cx("num text-xs", pnlTone(pct))}>{signedPct(pct)}</span>;
}

export default async function TradePage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string; side?: string }>;
}) {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");
  const summary = await getAccountSummary(current.account);
  if (!summary) redirect("/onboarding/broker");

  const { symbol: rawSymbol, side } = await searchParams;
  const symbol = rawSymbol?.trim().toUpperCase().slice(0, 20);
  const db = getDb();

  const [stockRows, popularRows, holidayRows, rankable, watchRows] = await Promise.all([
    symbol ? db.select().from(stockUniverse).where(eq(stockUniverse.symbol, symbol)).limit(1) : Promise.resolve([]),
    db
      .select({ symbol: stockUniverse.symbol, name: stockUniverse.name })
      .from(stockUniverse)
      .where(inArray(stockUniverse.symbol, POPULAR)),
    db.select({ holidayDate: marketHolidays.holidayDate }).from(marketHolidays),
    getRankableBrokers(),
    db
      .select({ symbol: stockUniverse.symbol, name: stockUniverse.name })
      .from(watchlistItems)
      .innerJoin(stockUniverse, eq(watchlistItems.symbol, stockUniverse.symbol))
      .where(eq(watchlistItems.accountId, current.account.id))
      .orderBy(asc(watchlistItems.addedAt)),
  ]);
  const stock = stockRows[0];
  const popular = POPULAR.map((s) => popularRows.find((r) => r.symbol === s)).filter((r) => r !== undefined);
  const closes = await closesWithChange([
    ...popular.map((p) => p.symbol),
    ...watchRows.map((w) => w.symbol),
    ...(stock ? [stock.symbol] : []),
  ]);
  const watching = stock ? watchRows.some((w) => w.symbol === stock.symbol) : false;
  const stockClose = stock ? closes.get(stock.symbol) : undefined;
  const targetTradeDate = targetTradeDateFor(marketNow(), new Set(holidayRows.map((h) => h.holidayDate)));

  const holding = stock ? summary.holdings.find((h) => h.symbol === stock.symbol) : undefined;
  const pendingSells = stock
    ? summary.pending.filter((o) => o.symbol === stock.symbol && o.side === "SELL").reduce((n, o) => n + o.qty, 0)
    : 0;
  const freeShares = Math.max(0, (holding?.qty ?? 0) - pendingSells);
  const pendingForStock = stock ? summary.pending.filter((o) => o.symbol === stock.symbol) : [];
  const anyClose = [...closes.values()][0];
  const ticketSide: "BUY" | "SELL" = side === "SELL" && freeShares > 0 ? "SELL" : "BUY";
  const beforeOpen = marketMoment(new Set(holidayRows.map((h) => h.holidayDate))).phase !== "open";

  // The selected stock's last session and its recent closes, never past the
  // practice market's date (stockClose is already bounded by it).
  const [bar, history] =
    stock && stockClose
      ? await Promise.all([
          db
            .select({ open: dailyPrices.open, high: dailyPrices.high, low: dailyPrices.low, volume: dailyPrices.volume })
            .from(dailyPrices)
            .where(and(eq(dailyPrices.symbol, stock.symbol), eq(dailyPrices.tradeDate, stockClose.tradeDate)))
            .limit(1)
            .then((r) => r[0]),
          db
            .select({ date: dailyPrices.tradeDate, close: dailyPrices.close })
            .from(dailyPrices)
            .where(and(eq(dailyPrices.symbol, stock.symbol), lte(dailyPrices.tradeDate, stockClose.tradeDate)))
            .orderBy(desc(dailyPrices.tradeDate))
            .limit(60)
            .then((r) => r.map((x) => ({ date: x.date, close: Number(x.close) })).reverse()),
        ])
      : [undefined, []];

  // Market watch: your watchlist first, then popular names you do not watch.
  const watchSymbols = new Set(watchRows.map((w) => w.symbol));
  const popularRest = popular.filter((p) => !watchSymbols.has(p.symbol));
  const watchOrder = [...watchRows, ...popularRest].map((r) => r.symbol);

  const watchRow = (r: { symbol: string; name: string }) => {
    const c = closes.get(r.symbol);
    const selected = stock?.symbol === r.symbol;
    return (
      <li key={r.symbol} className="group relative">
        <Link
          href={`/trade?symbol=${r.symbol}`}
          scroll={false}
          aria-current={selected ? "true" : undefined}
          className={cx(
            "flex items-center justify-between gap-3 rounded-lg px-3 py-2 transition-colors",
            selected ? "bg-accent-soft" : "hover:bg-hover",
          )}
        >
          <div className="min-w-0">
            <div className="text-sm font-semibold text-ink">{r.symbol}</div>
            <div className="truncate text-xs text-muted">{r.name}</div>
          </div>
          {c && (
            <div className="text-right">
              <div className="num text-sm text-ink">{inr(c.close)}</div>
              <Change close={c.close} prevClose={c.prevClose} />
            </div>
          )}
        </Link>
        <div className="absolute inset-y-0 right-2 hidden items-center gap-1 group-hover:flex">
          <Link
            href={`/trade?symbol=${r.symbol}&side=BUY`}
            scroll={false}
            className="rounded-md bg-up px-2.5 py-1 text-xs font-semibold text-invert"
            aria-label={`Buy ${r.symbol}`}
          >
            B
          </Link>
          <Link
            href={`/trade?symbol=${r.symbol}&side=SELL`}
            scroll={false}
            className="rounded-md bg-down px-2.5 py-1 text-xs font-semibold text-invert"
            aria-label={`Sell ${r.symbol}`}
          >
            S
          </Link>
        </div>
      </li>
    );
  };

  return (
    <>
      <TradeHotkeys symbols={watchOrder} current={stock?.symbol ?? null} side={ticketSide} />
      <PageHeader
        title="Trade"
        subtitle={
          <>
            Nifty 100 stocks at official NSE prices{anyClose ? `, latest close ${shortDate(anyClose.tradeDate)}` : ""}. Orders fill
            against the next session&apos;s official prices, never instantly.
          </>
        }
        action={
          <div className="text-sm sm:text-right">
            <div className="text-muted">Free cash</div>
            <div className="num font-semibold text-ink">{inr(summary.availableCash)}</div>
          </div>
        }
      />

      {/* Terminal layout. Phone: quote, order window, market watch. Large:
          quote and market watch beside a sticky order window. Extra large:
          market watch, quote and order window side by side. */}
      <div className="grid gap-6 [grid-template-areas:'quote'_'ticket'_'watch'] lg:grid-cols-[minmax(0,1fr)_380px] lg:[grid-template-areas:'quote_ticket'_'watch_ticket'] xl:grid-cols-[260px_minmax(0,1fr)_380px] xl:[grid-template-areas:'watch_quote_ticket']">
        <aside className="min-w-0 [grid-area:watch]">
          <Card className="p-3">
            <div className="px-1 pb-3">
              <StockSearch autoFocus={!stock} placeholder="Search stocks  ( / )" />
            </div>
            {watchRows.length > 0 && (
              <>
                <h2 className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted">Watchlist</h2>
                <ul className="mb-3">{watchRows.map(watchRow)}</ul>
              </>
            )}
            {popularRest.length > 0 && (
              <>
                <h2 className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted">Popular</h2>
                <ul>{popularRest.map(watchRow)}</ul>
              </>
            )}
            <p className="hidden border-t border-line px-3 pt-3 text-xs text-faint lg:block">
              Shortcuts: <kbd className="font-sans">B</kbd> buy, <kbd className="font-sans">S</kbd> sell,{" "}
              <kbd className="font-sans">↑</kbd> <kbd className="font-sans">↓</kbd> move, <kbd className="font-sans">/</kbd> search
            </p>
          </Card>
        </aside>

        <section className="flex min-w-0 flex-col gap-6 [grid-area:quote]">
          {symbol && !stock && (
            <Card>
              <p className="text-sm text-muted">
                &quot;{symbol}&quot; is not in the Nifty 100 universe this simulator covers. Search or pick one from the market watch.
              </p>
            </Card>
          )}

          {stock ? (
            <Card>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-semibold text-ink">{stock.symbol}</h2>
                    <Pill tone="neutral">NSE</Pill>
                    <form action={toggleWatchlistAction}>
                      <input type="hidden" name="symbol" value={stock.symbol} />
                      <button type="submit" aria-pressed={watching} className={cx(buttonClass("ghost", "sm"), "px-2 py-0.5 text-xs")}>
                        {watching ? "★ Watching" : "☆ Watch"}
                      </button>
                    </form>
                  </div>
                  <p className="truncate text-sm text-muted">{stock.name}</p>
                </div>
                {stockClose && (
                  <div className="text-right">
                    <div className="num text-2xl font-semibold text-ink">{inr(stockClose.close)}</div>
                    <div className="flex items-center justify-end gap-2 text-xs text-muted">
                      <Change close={stockClose.close} prevClose={stockClose.prevClose} />
                      <span>{shortDate(stockClose.tradeDate)} close</span>
                    </div>
                  </div>
                )}
              </div>

              {bar && stockClose && (
                <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-4 text-sm sm:grid-cols-5">
                  {[
                    ["Open", bar.open !== null ? inr(Number(bar.open)) : "-"],
                    ["High", bar.high !== null ? inr(Number(bar.high)) : "-"],
                    ["Low", bar.low !== null ? inr(Number(bar.low)) : "-"],
                    ["Prev. close", stockClose.prevClose !== null ? inr(stockClose.prevClose) : "-"],
                    ["Volume", bar.volume !== null ? Number(bar.volume).toLocaleString("en-IN") : "-"],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <dt className="text-xs text-muted">{k}</dt>
                      <dd className="num font-medium text-ink">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}

              {history.length > 1 && (
                <div className="mt-4 border-t border-line pt-4">
                  <PriceChart points={history} symbol={stock.symbol} />
                </div>
              )}

              {holding && (
                <div className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-4 text-sm">
                  <div>
                    <div className="text-xs text-muted">You hold</div>
                    <div className="num font-medium text-ink">{holding.qty} shares</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted">Avg. cost (with charges)</div>
                    <div className="num font-medium text-ink">{inr(holding.avgCost)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted">Unrealized P&amp;L</div>
                    <div className={cx("num font-medium", pnlTone(holding.unrealizedPnl))}>
                      {holding.unrealizedPnl !== null ? inr(holding.unrealizedPnl) : "-"}
                    </div>
                  </div>
                </div>
              )}
              {pendingForStock.length > 0 && (
                <div className="mt-4 border-t border-line pt-4">
                  <PendingOrders orders={pendingForStock} compact />
                </div>
              )}
            </Card>
          ) : (
            <Card className="bg-sub">
              <CardTitle>How an order works here</CardTitle>
              <ol className="flex list-decimal flex-col gap-2 pl-5 text-sm text-muted">
                <li>Pick a stock from the market watch, or press B or S on a highlighted one.</li>
                <li>Choose market, limit or stop-loss, and see every charge before you place it.</li>
                <li>The order is checked against the next session&apos;s official open, high, low and close.</li>
                <li>
                  It fills by{" "}
                  <Link href="/orders" className="text-accent-ink underline-offset-2 hover:underline">
                    published rules
                  </Link>
                  , with your broker&apos;s fees and every statutory tax applied.
                </li>
              </ol>
            </Card>
          )}
        </section>

        <div className="[grid-area:ticket]">
          <div className="lg:sticky lg:top-24">
            {stock && stockClose ? (
              <Card>
                <CardTitle>
                  Order window <span className="ml-1 text-sm font-normal text-muted">{stock.symbol}</span>
                </CardTitle>
                <OrderTicket
                  key={`${stock.symbol}-${ticketSide}`}
                  symbol={stock.symbol}
                  name={stock.name}
                  lastClose={stockClose.close}
                  lastCloseDate={stockClose.tradeDate}
                  defaultSide={ticketSide}
                  currentBroker={{ id: summary.broker.id, brand: summary.broker.brand, fees: summary.fees }}
                  rankable={rankable.map(toReplayBroker)}
                  freeCash={summary.availableCash}
                  freeShares={freeShares}
                  avgCost={holding?.avgCost ?? null}
                  targetTradeDate={targetTradeDate}
                  beforeOpen={beforeOpen}
                  clientOrderId={crypto.randomUUID()}
                />
              </Card>
            ) : stock ? (
              <Card>
                <p className="text-sm text-muted">No closing price on file for {stock.symbol} yet, so it cannot be traded here.</p>
              </Card>
            ) : (
              <Card className="bg-sub text-sm text-muted">Select a stock to open the order window.</Card>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
