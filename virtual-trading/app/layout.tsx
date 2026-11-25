import type { Metadata, Viewport } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { isDevAuth } from "@/lib/session";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "BrokerLens Virtual Trading", template: "%s | BrokerLens Virtual Trading" },
  description:
    "Practise investing with real NSE closing prices, delayed by a day for investor education, and see what every broker would really charge for the trades you make.",
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
