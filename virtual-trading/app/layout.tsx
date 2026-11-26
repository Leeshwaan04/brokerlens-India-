import type { Metadata, Viewport } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { isDevAuth } from "@/lib/session";
import { APP_URL, SITE_NAME } from "@/lib/site";
import "./globals.css";

const DESCRIPTION =
  "Free paper trading for Indian investors: practise Nifty 100 stocks with ₹10 lakh of virtual cash, market, limit, stop-loss and GTT orders, delivery and intraday, with every broker's real charges.";

export const metadata: Metadata = {
  metadataBase: new URL(APP_URL),
  title: { default: `Free paper trading app for Indian stocks | ${SITE_NAME}`, template: `%s | ${SITE_NAME}` },
  description: DESCRIPTION,
  applicationName: SITE_NAME,
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    locale: "en_IN",
    url: "/",
    title: "Practise trading free, with every broker's real charges",
    description: DESCRIPTION,
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "BrokerLens Virtual Trading: practise trading with real broker charges" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Practise trading free, with every broker's real charges",
    description: DESCRIPTION,
    images: ["/og.png"],
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfbfa" },
    { media: "(prefers-color-scheme: dark)", color: "#131316" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const doc = (
    <html lang="en-IN" className="h-full">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
  // Local development without a Clerk instance renders no ClerkProvider at
  // all (see lib/session.ts), so nothing can start a Clerk session from here.
  return isDevAuth() ? doc : <ClerkProvider>{doc}</ClerkProvider>;
}
