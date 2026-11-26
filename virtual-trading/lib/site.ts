// The app's public address, for canonical URLs, the sitemap and social
// cards. Set NEXT_PUBLIC_APP_URL per environment; production is
// paper.brokerlens.in.
export const APP_URL = (process.env.NEXT_PUBLIC_APP_URL ?? "https://paper.brokerlens.in").replace(/\/+$/, "");
export const SITE_NAME = "BrokerLens Virtual Trading";

/** Public, indexable pages. Everything else is per-user or sign-in. */
export const PUBLIC_PATHS = ["/", "/how-it-works", "/privacy"] as const;
