// Resolves the signed-in user id. Every deployed request goes through Clerk.
//
// VT_DEV_AUTH_USER_ID exists only so the app can run end to end on a laptop
// without creating a Clerk instance: set it to a user id to be signed in as
// that user, or to "signed-out" to browse as an anonymous visitor (landing
// page, sign-up, account-opening links). It is ignored whenever NODE_ENV is
// "production", which is what `next build` and `next start` always use (and
// Next inlines NODE_ENV at build time, so this branch is dead code in any
// production bundle). It can therefore never authenticate a deployed
// request, even if the variable is set by mistake in a hosting dashboard.
import { auth } from "@clerk/nextjs/server";

type Env = Record<string, string | undefined>;

export const DEV_SIGNED_OUT = "signed-out";

/** True when local dev auth is on (signed in or signed out), so Clerk is bypassed. */
export function isDevAuth(env: Env = process.env): boolean {
  if (env.NODE_ENV === "production") return false;
  return Boolean(env.VT_DEV_AUTH_USER_ID?.trim());
}

/** The local dev user id, or null when dev auth is off or set to signed out. */
export function devAuthUserId(env: Env = process.env): string | null {
  if (!isDevAuth(env)) return null;
  const id = env.VT_DEV_AUTH_USER_ID!.trim();
  return id === DEV_SIGNED_OUT ? null : id;
}

export async function getSessionUserId(): Promise<string | null> {
  if (isDevAuth()) return devAuthUserId();
  const { userId } = await auth();
  return userId;
}
