import type { Metadata } from "next";
import { AppHeader } from "@/components/AppHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { getSessionUserId } from "@/lib/session";

export const metadata: Metadata = { title: "Privacy notice" };

const CONTACT = "letmeknow@brokerlens.in";

// Describes only what this app's code actually stores. The general
// brokerlens.in privacy policy covers the rest of the site and says nothing
// about accounts, so this app carries its own notice.
export default async function PrivacyPage() {
  const signedIn = (await getSessionUserId()) !== null;
  return (
    <>
      <AppHeader signedIn={signedIn} />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10 sm:px-6">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Privacy notice</h1>
        <p className="mt-2 text-sm text-muted">BrokerLens Virtual Trading. Last updated November 2026.</p>

        <div className="mt-8 flex flex-col gap-8 text-sm leading-relaxed text-ink [&_h2]:mb-2 [&_h2]:text-lg [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_p]:text-muted [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-1.5 [&_ul]:text-muted">
          <section>
            <h2>What this covers</h2>
            <p>
              This notice covers the BrokerLens Virtual Trading practice app: what it stores when you create an account and
              practise. The rest of brokerlens.in is covered by its{" "}
              <a href="https://www.brokerlens.in/privacy-policy/" className="text-accent-ink underline-offset-2 hover:underline">
                privacy policy
              </a>
              .
            </p>
          </section>

          <section>
            <h2>What we store</h2>
            <ul>
              <li>
                <span className="text-ink">Your account.</span> An account id, your email address and, if you give it, your
                name. Signing in is handled by a specialist sign-in provider, so your password never reaches BrokerLens.
              </li>
              <li>
                <span className="text-ink">Your practice activity.</span> The broker you practise with, your virtual cash
                balance, virtual orders, holdings and the daily value of your virtual portfolio. None of it is real money or
                a real position.
              </li>
              <li>
                <span className="text-ink">Account-opening clicks.</span> When you follow a link to open an account with a
                broker, we record which broker and which part of the app the link was on, tied to your practice account if
                you are signed in. We do not store your IP address, browser details or any other identifier with it.
              </li>
              <li>
                <span className="text-ink">How you use the app.</span> A short record of key steps, such as opening the
                cost replay, switching broker, an order the app could not accept and why, and the date you last used the
                app. These are tied to your practice account and hold no amounts beyond broad ranges.
              </li>
              <li>
                <span className="text-ink">Payments for Plus.</span> The plan, amount, date and Razorpay&apos;s order and payment
                references. Your card, UPI or bank details are entered with Razorpay, our payment processor, and never reach
                BrokerLens. Payment records are kept as tax law requires, even after an account is deleted, with the link to
                you removed.
              </li>
              <li>
                <span className="text-ink">How you found us.</span> If you arrive from a link carrying campaign tags (such as
                utm_source), we keep just those tags in a cookie for 30 minutes, and save them with your account if you sign
                up in that time. The cookie holds no identifier and is used for nothing else.
              </li>
            </ul>
          </section>

          <section>
            <h2>What we never collect</h2>
            <ul>
              <li>Bank, card or demat account details, PAN, Aadhaar or any other KYC document.</li>
              <li>Your password, which only the sign-in provider handles.</li>
              <li>Anything from a real trading account. Nothing here connects to one, and no order reaches an exchange.</li>
            </ul>
          </section>

          <section>
            <h2>Why we use it</h2>
            <p>
              To run your practice account, show your portfolio, performance and broker cost comparisons, to find and fix
              the places where the app gets in your way, and to measure which parts of the app and which links bring people
              here and lead them to open a broker account. We do not sell your data or use it for
              advertising profiles.
            </p>
          </section>

          <section>
            <h2>Who else handles it</h2>
            <p>
              The sign-in provider and the database host store it on our behalf, to run the app and for no other purpose.
              Razorpay processes Plus payments under its own privacy policy.
              When you follow an account-opening link you leave this app for the broker&apos;s own site, where its privacy
              policy applies. Some of those links are referral links, which tell the broker that you came from BrokerLens.
            </p>
          </section>

          <section>
            <h2>How long we keep it, and your choices</h2>
            <p>
              We keep your account and practice history while your account exists. You can start over or delete your
              account and all its practice data yourself from the Account page. When an account is deleted, its
              account-opening clicks and usage records stay only as anonymous counts. To see what we hold about you or
              correct it, email <span className="font-medium text-ink">{CONTACT}</span> from the address on your account
              and we will act on it.
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
