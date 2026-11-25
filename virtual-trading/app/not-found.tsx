import Link from "next/link";
import { AppHeader } from "@/components/AppHeader";
import { buttonClass } from "@/components/ui";

export default function NotFound() {
  return (
    <>
      <AppHeader signedIn={false} />
      <main className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-4 py-20 text-center">
        <h1 className="text-2xl font-semibold text-ink">Page not found</h1>
        <p className="text-muted">That page does not exist, or it has moved.</p>
        <Link href="/" className={buttonClass("primary")}>
          Go to BrokerLens Virtual Trading
        </Link>
      </main>
    </>
  );
}
