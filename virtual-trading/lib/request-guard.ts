// Guards for state-changing JSON endpoints called by our own pages.
//
// A cross-site page can make a browser POST a plain form or text/plain body
// with the user's cookies, but it cannot send Content-Type:
// application/json without a CORS preflight, which we never grant. So these
// endpoints accept only JSON, and when the browser says where the request
// came from (Origin), it must be this app. Server actions have Next's own
// origin check; this covers route handlers.

export function crossSiteRejection(request: Request): Response | null {
  const type = request.headers.get("content-type") ?? "";
  if (!type.toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "Send JSON." }, { status: 415 });
  }
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin && origin !== (process.env.NEXT_PUBLIC_APP_URL ?? "").replace(/\/+$/, "")) {
    return Response.json({ error: "Cross-site request refused." }, { status: 403 });
  }
  return null;
}
