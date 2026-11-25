// Tracked outbound link to a broker's real account-opening page. Records one
// cta_clicks row (which placement sent the click, which broker, and the
// account if signed in; no IP or other personal data), then redirects.
//
// The redirect target is only ever the broker's own cta_url from
// broker_catalog, looked up by id. Nothing from the request is used as a
// destination, so this cannot be turned into an open redirect.
import { NextResponse, type NextRequest } from "next/server";
import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db";
import { brokerCatalog, ctaClicks, virtualAccounts } from "@/lib/schema";
import { getSessionUserId } from "@/lib/session";
import { parsePlacement } from "@/lib/brokers";

export async function GET(request: NextRequest, context: { params: Promise<{ brokerId: string }> }) {
  const { brokerId } = await context.params;
  const db = getDb();
  const [broker] = await db
    .select({ id: brokerCatalog.id, ctaUrl: brokerCatalog.ctaUrl })
    .from(brokerCatalog)
    .where(eq(brokerCatalog.id, brokerId))
    .limit(1);

  if (!broker || !broker.ctaUrl.startsWith("https://")) {
    return NextResponse.redirect(new URL("/", request.url), 302);
  }

  try {
    let accountId: string | null = null;
    const userId = await getSessionUserId();
    if (userId) {
      const [account] = await db
        .select({ id: virtualAccounts.id })
        .from(virtualAccounts)
        .where(eq(virtualAccounts.userId, userId))
        .limit(1);
      accountId = account?.id ?? null;
    }
    await db.insert(ctaClicks).values({
      accountId,
      brokerId: broker.id,
      placement: parsePlacement(request.nextUrl.searchParams.get("src")),
    });
  } catch (err) {
    // Measurement must never stand between a visitor and the broker's page.
    console.error("cta click logging failed", err);
  }

  const res = NextResponse.redirect(broker.ctaUrl, 302);
  res.headers.set("X-Robots-Tag", "noindex, nofollow");
  res.headers.set("Cache-Control", "no-store");
  return res;
}
