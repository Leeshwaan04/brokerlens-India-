"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { cx } from "./ui";

interface StockResult {
  symbol: string;
  name: string;
}

const DEBOUNCE_MS = 180;

export function StockSearch({ autoFocus = false, placeholder }: { autoFocus?: boolean; placeholder?: string }) {
  const router = useRouter();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StockResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(-1);
  const [searched, setSearched] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  function onQueryChange(value: string) {
    setQuery(value);
    if (!value.trim()) {
      abortRef.current?.abort();
      setResults([]);
      setSearched(false);
      setLoading(false);
    }
  }

  useEffect(() => {
    const q = query.trim();
    if (!q) return;
    const timer = setTimeout(async () => {
      // Abort the previous request so an older, slower response can never
      // overwrite results for what the user has typed since.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      try {
        const res = await fetch(`/api/stocks/search?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        const data = await res.json();
        setResults(data.results ?? []);
        setActive(-1);
        setSearched(true);
      } catch (err) {
        if ((err as Error).name !== "AbortError") setResults([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  function choose(r: StockResult) {
    setQuery("");
    setResults([]);
    router.push(`/trade?symbol=${encodeURIComponent(r.symbol)}`);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? results.length - 1 : a - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[active >= 0 ? active : 0]);
    } else if (e.key === "Escape") {
      setResults([]);
    }
  }

  const open = results.length > 0;

  return (
    <div className="relative">
      <label htmlFor={`${listId}-input`} className="sr-only">
        Search Nifty 500 stocks
      </label>
      <input
        id={`${listId}-input`}
        type="search"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        autoFocus={autoFocus}
        autoComplete="off"
        data-hotkey-search
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder ?? "Search by symbol or company, e.g. RELIANCE or Infosys"}
        className="w-full rounded-xl border border-line-strong bg-raised px-4 py-3 text-base text-ink placeholder:text-faint focus:border-accent focus:outline-none"
      />
      {loading && <div className="absolute right-4 top-3.5 text-xs text-faint">Searching</div>}
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-2 max-h-80 w-full overflow-auto rounded-xl border border-line bg-raised py-1 shadow-lg"
        >
          {results.map((r, i) => (
            <li key={r.symbol} id={`${listId}-${i}`} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(r)}
                className={cx(
                  "flex w-full items-center justify-between gap-4 px-4 py-2.5 text-left",
                  i === active ? "bg-accent-soft" : "hover:bg-hover",
                )}
              >
                <span className="font-medium text-ink">{r.symbol}</span>
                <span className="truncate text-sm text-muted">{r.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {searched && !loading && !open && query.trim() && (
        <p className="mt-2 text-sm text-muted">No Nifty 500 stock matches &quot;{query.trim()}&quot;.</p>
      )}
    </div>
  );
}
