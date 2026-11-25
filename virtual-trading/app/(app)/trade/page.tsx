import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { asc, eq, inArray } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getAccountSummary } from "@/lib/account-summary";
import { getDb } from "@/lib/db";
import { marketHolidays, stockUniverse, watchlistItems } from "@/lib/schema";
import { closesWithChange } from "@/lib/prices";
import { getRankableBrokers, toReplayBroker } from "@/lib/brokers";
import { targetTradeDateFor } from "@/lib/market-calendar";
import { inr, shortDate, signedPct, pnlTone } from "@/lib/format";
import { StockSearch } from "@/components/StockSearch";
import { OrderTicket } from "@/components/OrderTicket";
import { PendingOrders } from "@/components/PendingOrders";
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
  const targetTradeDate = targetTradeDateFor(new Date(), new Set(holidayRows.map((h) => h.holidayDate)));

  const holding = stock ? summary.holdings.find((h) => h.symbol === stock.symbol) : undefined;
  const pendingSells = stock
    ? summary.pending.filter((o) => o.symbol === stock.symbol && o.side === "SELL").reduce((n, o) => n + o.qty, 0)
    : 0;
  const freeShares = Math.max(0, (holding?.qty ?? 0) - pendingSells);
  const pendingForStock = stock ? summary.pending.filter((o) => o.symbol === stock.symbol) : [];
  const anyClose = [...closes.values()][0];

  return (
    <>
      <PageHeader
        title="Trade"
        subtitle={
          <>
            Nifty 100 stocks at official NSE closing prices{anyClose ? `, latest close ${shortDate(anyClose.tradeDate)}` : ""}.
            Orders fill at the next close, never instantly.
          </>
        }
        action={
          <div className="text-sm sm:text-right">
            <div className="text-muted">Free cash</div>
            <div className="num font-semibold text-ink">{inr(summary.availableCash)}</div>
          </div>
        }
      />

      {/* Three grid children so that on a phone the ticket comes straight
          after the chosen stock, not below all twelve popular stocks; on
          large screens it sits in a sticky right column beside both. */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_400px] lg:grid-rows-[auto_1fr]">
        <div className="flex min-w-0 flex-col gap-6 lg:col-start-1 lg:row-start-1">
          <StockSearch autoFocus={!stock} />

          {symbol && !stock && (
            <Card>
              <p className="text-sm text-muted">
                &quot;{symbol}&quot; is not in the Nifty 100 universe this simulator covers. Search above or pick one below.
              </p>
            </Card>
          )}

          {stock && (
            <Card>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-semibold text-ink">{stock.symbol}</h2>
                    <Pill tone="neutral">NSE</Pill>
                    <form action={toggleWatchlistAction}>
                      <input type="hidden" name="symbol" value={stock.symbol} />
                      <button
                        type="submit"
                        aria-pressed={watching}
                        className={cx(buttonClass("ghost", "sm"), "px-2 py-0.5 text-xs")}
                      >
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
          )}

        </div>

        <div className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <div className="lg:sticky lg:top-24">
          {stock && stockClose ? (
            <Card>
              <CardTitle>Order ticket</CardTitle>
              <OrderTicket
                key={stock.symbol}
                symbol={stock.symbol}
                name={stock.name}
                lastClose={stockClose.close}
                lastCloseDate={stockClose.tradeDate}
                defaultSide={side === "SELL" ? "SELL" : "BUY"}
                currentBroker={{ id: summary.broker.id, brand: summary.broker.brand, fees: summary.fees }}
                rankable={rankable.map(toReplayBroker)}
                freeCash={summary.availableCash}
                freeShares={freeShares}
                avgCost={holding?.avgCost ?? null}
                targetTradeDate={targetTradeDate}
                clientOrderId={crypto.randomUUID()}
              />
            </Card>
          ) : stock ? (
            <Card>
              <p className="text-sm text-muted">No closing price on file for {stock.symbol} yet, so it cannot be traded here.</p>
            </Card>
          ) : (
            <Card className="bg-sub">
              <CardTitle>How an order works here</CardTitle>
              <ol className="flex list-decimal flex-col gap-2 pl-5 text-sm text-muted">
                <li>Pick a stock and a quantity. You see the real charges before you place it.</li>
                <li>The order waits for the next official NSE close, published each trading evening.</li>
                <li>It fills at that price, with your broker&apos;s fees and every statutory tax applied.</li>
              </ol>
            </Card>
          )}
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-6 lg:col-start-1 lg:row-start-2">
          {watchRows.length > 0 && (
            <Card>
              <CardTitle>Your watchlist</CardTitle>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {watchRows.map((w) => {
                  const c = closes.get(w.symbol);
                  return (
                    <Link
                      key={w.symbol}
                      href={`/trade?symbol=${w.symbol}`}
                      className={cx(
                        "rounded-lg border px-3 py-2.5 transition-colors hover:border-accent",
                        stock?.symbol === w.symbol ? "border-accent bg-accent-soft" : "border-line",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-ink">{w.symbol}</span>
                        {c && <Change close={c.close} prevClose={c.prevClose} />}
                      </div>
                      <div className="truncate text-xs text-muted">{w.name}</div>
                      {c && <div className="num mt-1 text-sm text-ink">{inr(c.close)}</div>}
                    </Link>
                  );
                })}
              </div>
            </Card>
          )}
          <Card>
            <CardTitle>Popular stocks</CardTitle>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {popular.map((p) => {
                const c = closes.get(p.symbol);
                return (
                  <Link
                    key={p.symbol}
                    href={`/trade?symbol=${p.symbol}`}
                    className={cx(
                      "rounded-lg border px-3 py-2.5 transition-colors hover:border-accent",
                      stock?.symbol === p.symbol ? "border-accent bg-accent-soft" : "border-line",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-ink">{p.symbol}</span>
                      {c && <Change close={c.close} prevClose={c.prevClose} />}
                    </div>
                    <div className="truncate text-xs text-muted">{p.name}</div>
                    {c && <div className="num mt-1 text-sm text-ink">{inr(c.close)}</div>}
                  </Link>
                );
              })}
            </div>
          </Card>
        </div>

      </div>
    </>
  );
}
