import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { after } from "next/server";
import { readCampaign, track } from "@/lib/events";
import { SignUp } from "@clerk/nextjs";
import { devAuthUserId, isDevAuth } from "@/lib/session";
import { AuthFrame } from "@/components/AuthFrame";

export const metadata: Metadata = { title: "Start practising", robots: { index: false, follow: true } };

export default async function SignUpPage() {
  if (devAuthUserId()) redirect("/onboarding/broker");
  const campaign = await readCampaign();
  after(() => track("signup_viewed", campaign));
  if (isDevAuth()) {
    // Local dev, signed out: there is no Clerk instance to render a form for.
    return (
      <AuthFrame title="Start practising, free">
        <p className="max-w-sm rounded-xl border border-line bg-raised p-5 text-sm text-muted">
          Local dev mode: Clerk handles this form in production. Set VT_DEV_AUTH_USER_ID to a user id in .env.local to
          sign in locally.
        </p>
      </AuthFrame>
    );
  }
  return (
    <AuthFrame title="Start practising, free">
      <SignUp fallbackRedirectUrl="/onboarding/broker" signInUrl="/sign-in" />
    </AuthFrame>
  );
}
