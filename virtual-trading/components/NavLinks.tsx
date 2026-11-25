"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "./ui";

const ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/trade", label: "Trade" },
  { href: "/portfolio", label: "Holdings" },
  { href: "/orders", label: "Orders" },
  { href: "/performance", label: "Performance" },
  { href: "/costs", label: "Broker costs" },
] as const;

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Main"
      className="-mx-1 flex gap-1 overflow-x-auto pr-6 [mask-image:linear-gradient(to_right,black_85%,transparent)] md:pr-0 md:[mask-image:none]"
    >
      {ITEMS.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
              active ? "bg-accent-soft text-accent-ink" : "text-muted hover:bg-hover hover:text-ink",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
