import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";

export default async function HomePage() {
  const { userId } = await auth();
  if (userId) {
    redirect("/dashboard");
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-1 flex-col justify-center gap-6 p-8 text-center">
      <h1 className="text-3xl font-semibold">Practice investing before you risk real money</h1>
      <p className="text-base text-gray-600 dark:text-gray-400">
        Place virtual equity orders, priced at real NSE closing prices delayed by a day for investor
        education, with the same brokerage and tax costs your real broker would actually charge. Build a
        track record before you decide whether, and with which broker, to invest for real.
      </p>
      <div className="flex justify-center gap-4">
        <Link href="/sign-up" className="rounded-md bg-black px-5 py-2.5 text-white dark:bg-white dark:text-black">
          Get started
        </Link>
        <Link href="/sign-in" className="rounded-md border px-5 py-2.5">
          Sign in
        </Link>
      </div>
      <p className="text-xs text-gray-500">
        This is a simulation for investor education. Orders here are never sent to a real exchange and no
        real money moves.
      </p>
    </main>
  );
}
