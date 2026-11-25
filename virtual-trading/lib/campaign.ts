// Campaign (utm_*) tags, kept free of any database or server-only import so
// proxy.ts can use it: the proxy bundle should not carry the database stack.

// Set by proxy.ts when a visitor arrives with utm_* tags, so the campaign
// survives the trip through sign-up. Holds only the tags, no identifier.
export const CAMPAIGN_COOKIE = "vt_src";
export const CAMPAIGN_TAG = /^[a-z0-9_.-]{1,40}$/i;

export function encodeCampaign(params: URLSearchParams): string | null {
  const parts = ["utm_source", "utm_medium", "utm_campaign"].map((k) => params.get(k) ?? "");
  if (!parts[0] || !parts.every((p) => p === "" || CAMPAIGN_TAG.test(p))) return null;
  return parts.join("|");
}
