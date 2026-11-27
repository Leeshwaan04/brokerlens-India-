"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

interface Studio {
  mountStudio(
    host: HTMLElement,
    opts: { adapter: unknown; height?: number; storagePrefix?: string },
  ): Promise<{ destroy(): void }>;
  columnsAdapter(symbol: string, url: string): unknown;
}

const loading = new Map<string, Promise<void>>();

function loadScript(src: string): Promise<void> {
  const cached = loading.get(src);
  if (cached) return cached;
  const p = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      loading.delete(src);
      reject(new Error(`failed to load ${src}`));
    };
    document.head.append(s);
  });
  loading.set(src, p);
  return p;
}

// The chart studio (static files under /charting, built from /charting in the
// repo) for one stock. It loads in the browser only, after the page is
// interactive, so the worker bundle is unaffected. While it loads, or if it
// cannot (blocked script, old browser, no history), the server-rendered
// fallback chart stays on screen.
export function ChartStudio({ symbol, fallback }: { symbol: string; fallback: ReactNode }) {
  const host = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let cancelled = false;
    let handle: { destroy(): void } | null = null;
    setReady(false);

    (async () => {
      try {
        await loadScript("/charting/lightweight-charts.js");
        await loadScript("/charting/engine.js");
        const lib = (window as unknown as { BrokerLensCharting?: Studio }).BrokerLensCharting;
        if (!lib || cancelled) return;
        const adapter = lib.columnsAdapter(symbol, `/api/history/${encodeURIComponent(symbol)}`);
        const h = await lib.mountStudio(el, { adapter, height: 360, storagePrefix: "vt_chart" });
        if (cancelled) {
          h.destroy();
          return;
        }
        handle = h;
        // mountStudio shows its own message if there is no history; only swap
        // the fallback out when a real chart was drawn.
        setReady(Boolean(el.querySelector(".blc-canvas")));
      } catch {
        /* the fallback stays */
      }
    })();

    return () => {
      cancelled = true;
      handle?.destroy();
    };
  }, [symbol]);

  return (
    <>
      {!ready && fallback}
      <div ref={host} data-testid="chart-studio" />
    </>
  );
}
