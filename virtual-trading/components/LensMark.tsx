export function LensMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <circle cx="14" cy="14" r="7.5" fill="none" stroke="var(--text-invert)" strokeWidth="2.4" />
      <path d="M19.5 19.5 25 25" stroke="var(--text-invert)" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M10 16.5 12.6 13.4 14.8 15.2 18 11.2" fill="none" stroke="var(--text-invert)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
