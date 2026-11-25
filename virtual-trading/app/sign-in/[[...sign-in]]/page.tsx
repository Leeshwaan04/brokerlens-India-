import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SignIn } from "@clerk/nextjs";
import { devAuthUserId, isDevAuth } from "@/lib/session";
import { AuthFrame } from "@/components/AuthFrame";

export const metadata: Metadata = { title: "Sign in" };

export default function SignInPage() {
  if (devAuthUserId()) redirect("/dashboard");
  if (isDevAuth()) {
    // Local dev, signed out: there is no Clerk instance to render a form for.
    return (
      <AuthFrame title="Welcome back">
        <p className="max-w-sm rounded-xl border border-line bg-raised p-5 text-sm text-muted">
          Local dev mode: Clerk handles this form in production. Set VT_DEV_AUTH_USER_ID to a user id in .env.local to
          sign in locally.
        </p>
      </AuthFrame>
    );
  }
  return (
    <AuthFrame title="Welcome back">
      <SignIn fallbackRedirectUrl="/dashboard" signUpUrl="/sign-up" />
    </AuthFrame>
  );
}
