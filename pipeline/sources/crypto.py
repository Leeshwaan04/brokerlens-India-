"""Crypto adapters: Binance (price, one request for the whole universe) plus
CoinGecko (name, market-cap rank, supply, ATH/ATL - the identity facts a bare
ticker symbol can't give you).

Phase 1 universe: 28 coins, hand-verified against both CoinGecko's real
market-cap ranking and Binance's actual tradeable USDT pairs. A wrong
coin-name match (a symbol collision - CoinGecko alone has multiple different
coins sharing "BTC"-like tickers) is worse than no page at all, so this list
only grows by hand, never by scanning Binance's symbol list and guessing.
MATIC and XMR were deliberately left out: Binance delisted both (Polygon's
migration to POL, and a years-old Monero delisting over privacy-coin
regulatory concerns), confirmed via exchangeInfo, not an oversight.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from datetime import datetime, timezone

from ..common import Fetcher, log, to_num

BINANCE = "https://api.binance.com/api/v3"
COINGECKO = "https://api.coingecko.com/api/v3"

# Binance base asset -> CoinGecko coin id. Each is the single, dominant,
# unambiguous coin for that symbol by real market cap - verified by hand,
# not pattern-matched.
UNIVERSE = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin", "XRP": "ripple",
    "SOL": "solana", "TRX": "tron", "ZEC": "zcash", "DOGE": "dogecoin",
    "LINK": "chainlink", "ADA": "cardano", "XLM": "stellar", "BCH": "bitcoin-cash",
    "LTC": "litecoin", "UNI": "uniswap", "HBAR": "hedera-hashgraph",
    "AVAX": "avalanche-2", "NEAR": "near", "SUI": "sui", "SHIB": "shiba-inu",
    "DOT": "polkadot", "POL": "polygon-ecosystem-token", "ATOM": "cosmos",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism", "FIL": "filecoin",
    "ICP": "internet-computer", "ETC": "ethereum-classic",
}


def crypto():
    return Fetcher("crypto", timeout=20)


def binance_prices(f, ttl=None):
    """Price + 24h stats for the whole universe in one request."""
    symbols = ["%sUSDT" % s for s in UNIVERSE]
    # Binance rejects the request with the spaces json.dumps adds by default
    # after each comma - confirmed by hand, not documented anywhere obvious.
    url = "%s/ticker/24hr?symbols=%s" % (
        BINANCE, urllib.parse.quote(json.dumps(symbols, separators=(",", ":"))))
    data = f.get_json(url, ttl=60 if ttl is None else ttl)
    if not data:
        return {}
    out = {}
    for row in data or []:
        sym = row.get("symbol", "")
        base = sym[:-4] if sym.endswith("USDT") else None
        if base and base in UNIVERSE:
            out[base] = {
                "price_usd": to_num(row.get("lastPrice")),
                "change_pct_24h": to_num(row.get("priceChangePercent")),
                "high_24h": to_num(row.get("highPrice")),
                "low_24h": to_num(row.get("lowPrice")),
                "volume_24h_usd": to_num(row.get("quoteVolume")),
            }
    return out


def _coingecko_markets_rows(f, ttl):
    ids = ",".join(UNIVERSE.values())
    url = "%s/coins/markets?vs_currency=usd&ids=%s&order=market_cap_desc&per_page=%d&page=1" % (
        COINGECKO, ids, len(UNIVERSE) + 5)
    data = f.get_json(url, ttl=ttl)
    return {row["id"]: row for row in (data or []) if row.get("id")}


def coingecko_meta(f, ttl=None):
    """Identity + supply/ATH/ATL facts, plus the same price/24h fields
    Binance provides - CoinGecko's markets endpoint already carries both in
    one response, refreshed each full build (not every minute; these move
    far slower than price).

    This is also the *only* price leg that actually works from Vercel or
    GitHub Actions: Binance's global API returns HTTP 451 (blocked for
    legal reasons) to any US-hosted IP, and both of those build environments
    are US-hosted - confirmed live in a Vercel build log, not a guess. See
    collect() for how the two are merged."""
    by_id = _coingecko_markets_rows(f, 3600 if ttl is None else ttl)
    out = {}
    for sym, cg_id in UNIVERSE.items():
        row = by_id.get(cg_id)
        if not row:
            continue
        out[sym] = {
            "coingecko_id": cg_id,
            "name": row.get("name"),
            "image": row.get("image"),
            "market_cap_rank": row.get("market_cap_rank"),
            "market_cap_usd": row.get("market_cap"),
            "circulating_supply": row.get("circulating_supply"),
            "max_supply": row.get("max_supply"),
            "ath_usd": row.get("ath"),
            "ath_date": row.get("ath_date"),
            "atl_usd": row.get("atl"),
            "atl_date": row.get("atl_date"),
            "price_usd": to_num(row.get("current_price")),
            "change_pct_24h": to_num(row.get("price_change_percentage_24h")),
            "high_24h": to_num(row.get("high_24h")),
            "low_24h": to_num(row.get("low_24h")),
            "volume_24h_usd": to_num(row.get("total_volume")),
        }
    return out


def coingecko_prices(f, ttl=None):
    """Price-only leg for the cheap pulse/ticker refresh, mirroring
    binance_prices()'s return shape. Same endpoint as coingecko_meta, on a
    short ttl, so a Binance-blocked refresh still gets a real number instead
    of going stale."""
    by_id = _coingecko_markets_rows(f, 60 if ttl is None else ttl)
    out = {}
    for sym, cg_id in UNIVERSE.items():
        row = by_id.get(cg_id)
        if not row:
            continue
        out[sym] = {
            "price_usd": to_num(row.get("current_price")),
            "change_pct_24h": to_num(row.get("price_change_percentage_24h")),
            "high_24h": to_num(row.get("high_24h")),
            "low_24h": to_num(row.get("low_24h")),
            "volume_24h_usd": to_num(row.get("total_volume")),
        }
    return out


def coingecko_history(f, days=365, ttl=None):
    """Up to a year of daily closing prices per coin, for the chart on each
    coin's own page.

    CoinGecko's free tier has no historical OHLC endpoint that stays at daily
    granularity over a year (its /ohlc endpoint coarsens to ~4-day candles
    past 30 days) - market_chart's daily-interval price series is the
    honestly-available data at this range, so the chart is a line/area
    series, not candlesticks. The tail of a days=365 response also carries
    an extra, finer-grained point or two for the still-incomplete current
    day, which would otherwise hand Lightweight Charts two rows for the same
    date - it requires strictly one point per unique time, so that's
    collapsed below, keeping the latest price for each date.

    One call per coin against a free tier that throttles far sooner than
    its own documented limit suggests (confirmed: even 1.5s spacing between
    calls started drawing 429s after under 10 coins). retries=1 rather than
    the usual 3 - once actually throttled, immediate retries just burn the
    call budget other coins in this same run need, for no better odds. A
    coin that misses out this run is not stuck: each URL is cached
    individually on a 20-hour ttl, so whichever coins succeed today are
    skipped (cache hit) tomorrow, and the ones that got 429'd get their
    turn - the full 28 fills in over a few runs rather than never.
    """
    ttl = 20 * 3600 if ttl is None else ttl
    out = {}
    for i, (sym, cg_id) in enumerate(UNIVERSE.items()):
        if i:
            time.sleep(2.0)
        url = "%s/coins/%s/market_chart?vs_currency=usd&days=%d&interval=daily" % (COINGECKO, cg_id, days)
        data = f.get_json(url, ttl=ttl, retries=1)
        points = (data or {}).get("prices") or []
        if not points:
            continue
        by_date = {}
        for ms, price in points:
            date = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            by_date[date] = round(price, 8)  # last write per date wins - the latest sample for that day
        out[sym] = sorted(by_date.items())
    return out


def collect():
    f = crypto()
    prices = binance_prices(f)
    meta = coingecko_meta(f)
    history = coingecko_history(f)
    coins = []
    for sym in UNIVERSE:
        row = {"symbol": sym}
        row.update(meta.get(sym) or {})
        if sym in prices:
            row.update(prices[sym])
            row["price_source"] = "binance"
        elif row.get("price_usd") is not None:
            row["price_source"] = "coingecko"
        # A coin with neither identity facts nor a price isn't worth a page -
        # skip it this run rather than publish something near-empty.
        if row.get("name") and row.get("price_usd") is not None:
            coins.append(row)
        else:
            log("crypto: skipping %s - missing %s" % (
                sym, "CoinGecko metadata" if not row.get("name") else "any price"), "warn")
    coins.sort(key=lambda r: r.get("market_cap_rank") or 9999)
    return {"coins": coins, "history": history}
