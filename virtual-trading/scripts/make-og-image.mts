// Renders public/og.png (1200x630), the card shown when the app's link is
// shared. Run once after changing the copy: npx tsx scripts/make-og-image.mts
import { writeFile } from "node:fs/promises";
import { createElement as h } from "react";
import { ImageResponse } from "next/og";

const ink = "#f4f4f2";
const muted = "#a7a7b0";
const accent = "#8b97ff";

const card = h(
  "div",
  {
    style: {
      width: "100%",
      height: "100%",
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      padding: "64px 72px",
      background: "linear-gradient(135deg, #131316 0%, #1c1d2b 100%)",
      color: ink,
      fontFamily: "sans-serif",
    },
  },
  h(
    "div",
    { style: { display: "flex", alignItems: "center", gap: 16, fontSize: 30, color: muted } },
    h("div", { style: { width: 44, height: 44, borderRadius: 10, background: accent, display: "flex" } }),
    "BrokerLens Virtual Trading",
  ),
  h(
    "div",
    { style: { display: "flex", flexDirection: "column", gap: 20 } },
    h("div", { style: { fontSize: 68, fontWeight: 700, lineHeight: 1.08, letterSpacing: -1.5 } }, "Practise trading free, with every broker's real charges"),
    h(
      "div",
      { style: { fontSize: 30, color: muted, lineHeight: 1.35 } },
      "₹10 lakh virtual cash · Nifty 100 · market, limit, stop-loss, GTT · delivery and intraday",
    ),
  ),
  h("div", { style: { display: "flex", fontSize: 26, color: accent } }, "paper.brokerlens.in"),
);

const res = new ImageResponse(card, { width: 1200, height: 630 });
await writeFile(new URL("../public/og.png", import.meta.url), Buffer.from(await res.arrayBuffer()));
console.log("wrote public/og.png");
