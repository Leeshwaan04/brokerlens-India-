"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface StockResult {
  symbol: string;
  name: string;
}

export function StockSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StockResult[]>([]);
  const [loading, setLoading] = useState(false);

  async function onChange(value: string) {
    setQuery(value);
    if (value.trim().length === 0) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/stocks/search?q=${encodeURIComponent(value)}`);
      const data = await res.json();
      setResults(data.results ?? []);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search a stock, e.g. RELIANCE"
        className="w-full rounded-md border px-3 py-2"
      />
      {loading && <div className="mt-1 text-xs text-gray-500">Searching...</div>}
      {results.length > 0 && (
        <ul className="mt-2 divide-y rounded-md border">
          {results.map((r) => (
            <li key={r.symbol}>
              <button
                type="button"
                onClick={() => router.push(`/trade?symbol=${r.symbol}`)}
                className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-900"
              >
                <span className="font-medium">{r.symbol}</span>
                <span className="text-sm text-gray-500">{r.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
