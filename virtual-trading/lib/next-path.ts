// Where to send a visitor after onboarding: only a path inside this app.
// Anything else (another site, "//host", a backslash trick) is ignored.
export function safeNextPath(raw: string | string[] | undefined | null, fallback = "/dashboard"): string {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (!v || v.length > 200 || !v.startsWith("/") || v.startsWith("//") || v.includes("\\") || /[\u0000-\u001f]/.test(v)) return fallback;
  return v;
}
