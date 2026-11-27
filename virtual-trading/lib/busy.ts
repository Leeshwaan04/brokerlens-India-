// Recognises "the database is busy" failures (a queue for the account's row
// lock, no free connection, too many clients) so callers can answer "try again
// in a moment" instead of a generic error. Walks the error's causes, because
// the driver wraps the original.
export function isBusyError(err: unknown): boolean {
  let e: unknown = err;
  for (let depth = 0; e && depth < 5; depth++) {
    const code = (e as { code?: unknown }).code;
    const message = e instanceof Error ? e.message : String(e);
    if (code === "55P03" || code === "57014" || code === "53300") return true;
    if (/timeout exceeded when trying to connect|lock timeout|canceling statement due to|too many (clients|connections)/i.test(message)) return true;
    e = (e as { cause?: unknown }).cause;
  }
  return false;
}
