"use client";

import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";

// A form's submit button that shows the request is on its way: disabled and
// relabelled until the server action answers, so a slow connection never
// looks like a dead button and a second click cannot send the form twice.
export function SubmitButton({
  children,
  pendingLabel,
  className,
  ...rest
}: {
  children: ReactNode;
  pendingLabel?: ReactNode;
  className?: string;
  "aria-pressed"?: boolean;
  title?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} aria-busy={pending} className={className} {...rest}>
      {pending && pendingLabel !== undefined ? pendingLabel : children}
    </button>
  );
}
