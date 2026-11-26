// Shown inside the app's header and footer while a signed-in page loads, so a
// slow connection shows progress straight away instead of a page that seems
// not to respond.
export default function Loading() {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-6">
      <span className="sr-only">Loading</span>
      <div className="h-8 w-56 animate-pulse rounded-lg bg-raised" />
      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl border border-line bg-raised" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-xl border border-line bg-raised" />
    </div>
  );
}
