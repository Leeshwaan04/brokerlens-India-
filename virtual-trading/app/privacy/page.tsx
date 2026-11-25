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
              To run your practice account, show your portfolio, performance and broker cost comparisons, and to measure
              which parts of the app lead people to open a broker account. We do not sell your data or use it for
              advertising profiles.
            </p>
          </section>

          <section>
            <h2>Who else handles it</h2>
            <p>
              The sign-in provider and the database host store it on our behalf, to run the app and for no other purpose.
              When you follow an account-opening link you leave this app for the broker&apos;s own site, where its privacy
              policy applies. Some of those links are referral links, which tell the broker that you came from BrokerLens.
            </p>
          </section>

          <section>
            <h2>How long we keep it, and your choices</h2>
            <p>
              We keep your account and practice history while your account exists. To see what we hold about you, correct
              it, or have your account and all its practice data deleted, email{" "}
              <span className="font-medium text-ink">{CONTACT}</span> from the address on your account and we will act on
              it.
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
