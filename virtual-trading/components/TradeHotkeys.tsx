"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// Keyboard shortcuts for the trade screen, in the spirit of a broker
// terminal: B and S open the order window on buy or sell for the selected
// stock, the arrow keys move through the market watch, and / jumps to search.
// They never fire while you are typing in a field or holding a modifier.
export function TradeHotkeys({ symbols, current, side }: { symbols: string[]; current: string | null; side: "BUY" | "SELL" }) {
  const router = useRouter();

  useEffect(() => {
    function go(symbol: string, s: "BUY" | "SELL") {
      router.push(`/trade?symbol=${encodeURIComponent(symbol)}&side=${s}`, { scroll: false });
    }
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;

      const target = current ?? symbols[0];
      if (e.key === "/") {
        const input = document.querySelector<HTMLInputElement>("[data-hotkey-search]");
        if (input) {
          e.preventDefault();
          input.focus();
        }
        return;
      }
      if ((e.key === "b" || e.key === "B") && target) {
        e.preventDefault();
        go(target, "BUY");
        return;
      }
      if ((e.key === "s" || e.key === "S") && target) {
        e.preventDefault();
        go(target, "SELL");
        return;
      }
      if ((e.key === "ArrowDown" || e.key === "ArrowUp") && symbols.length > 0) {
        const i = current ? symbols.indexOf(current) : -1;
        const next = e.key === "ArrowDown" ? Math.min(symbols.length - 1, i + 1) : Math.max(0, i === -1 ? 0 : i - 1);
        if (symbols[next] && symbols[next] !== current) {
          e.preventDefault();
          go(symbols[next], side);
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, symbols, current, side]);

  return null;
}
