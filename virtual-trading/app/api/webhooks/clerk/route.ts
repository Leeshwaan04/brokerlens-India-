import type { NextRequest } from "next/server";
import { verifyWebhook } from "@clerk/nextjs/webhooks";
import { getDb } from "@/lib/db";
import { users } from "@/lib/schema";

export async function POST(request: NextRequest) {
  let event;
  try {
    // verifyWebhook checks the Svix signature headers against
    // CLERK_WEBHOOK_SIGNING_SECRET; it throws on a bad or missing signature.
    event = await verifyWebhook(request);
  } catch (err) {
    console.error("Clerk webhook signature verification failed", err);
    return new Response("Invalid signature", { status: 400 });
  }

  if (event.type === "user.created") {
    const { id, email_addresses, first_name, last_name } = event.data;
    const primaryEmail = email_addresses?.[0]?.email_address ?? "";
    const displayName = [first_name, last_name].filter(Boolean).join(" ") || null;

    const db = getDb();
    await db
      .insert(users)
      .values({ id, email: primaryEmail, displayName })
      .onConflictDoNothing({ target: users.id });
  }

  return new Response("OK", { status: 200 });
}
