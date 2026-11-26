// Next.js 16 renamed middleware.js to proxy.js (same mechanism, new file
// name). clerkMiddleware() returns a standard proxy-shaped handler.
import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { isDevAuth } from "@/lib/session";
import { CAMPAIGN_COOKIE, encodeCampaign } from "@/lib/campaign";

const isPublicRoute = createRouteMatcher([
  "/",
  "/privacy",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/go/(.*)",
  "/api/webhooks/clerk",
  "/api/webhooks/razorpay",
  "/api/cron/(.*)",
]);

const clerk = clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect();
  }
});

// Arriving with utm_* tags: keep just the tags for 30 minutes so the
// campaign is still known when the visitor finishes signing up.
function rememberCampaign(req: NextRequest, res: Response | void | null | undefined) {
  const tags = encodeCampaign(req.nextUrl.searchParams);
  if (!tags || !(res instanceof NextResponse)) return res;
  res.cookies.set(CAMPAIGN_COOKIE, tags, {
    maxAge: 1800,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
  });
  return res;
}

export default async function proxy(req: NextRequest, event: NextFetchEvent) {
  // Local development without a Clerk instance (see lib/session.ts). Never
  // true in a production build.
  if (isDevAuth()) return rememberCampaign(req, NextResponse.next());
  return rememberCampaign(req, await clerk(req, event));
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
