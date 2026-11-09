"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const pages = [
  { href: "/", label: "Analyze" },
  { href: "/screener", label: "Screener" },
];

export default function SiteNavigation() {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary" className="border-b border-line bg-ink">
      <div className="gutter mx-auto flex max-w-6xl gap-2 py-3">
        {pages.map(({ href, label }) => {
          const active = pathname === href;

          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border px-5 py-2 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass ${
                active
                  ? "border-brass bg-brass/10 text-brass underline decoration-2 underline-offset-4"
                  : "border-transparent text-paper hover:border-line hover:bg-panel hover:text-brass"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
