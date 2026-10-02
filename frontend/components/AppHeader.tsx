"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMe } from "@/lib/useMe";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/skills", label: "Skills" },
  { href: "/job-descriptions", label: "Job Descriptions" },
  { href: "/cv", label: "My CV" },
  { href: "/profile", label: "My Profile" },
];

// "/" is active only on the Dashboard itself; the others also cover their sub-pages
// (e.g. /skills/3 highlights "Skills").
function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

/** The shared header, wired into app/layout.tsx so it appears on every page. */
export default function AppHeader() {
  const me = useMe();
  const pathname = usePathname();

  return (
    <header className="border-b border-line bg-surface print:hidden">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="font-display text-xl text-ink">
          Career <span className="text-accent">AI</span>
        </Link>

        <nav className="order-last flex w-full flex-wrap gap-1 text-sm md:order-none md:w-auto">
          {NAV.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 transition-colors ${
                  active
                    ? "bg-accent-soft font-medium text-accent"
                    : "text-ink-soft hover:bg-ground hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <span className="font-mono text-xs">
          {me.status === "loading" && <span className="text-ink-soft">…</span>}
          {me.status === "error" && (
            <span
              className="rounded bg-not-verified-bg px-2 py-0.5 text-not-verified"
              title="The backend isn't reachable. Is it running?"
            >
              offline
            </span>
          )}
          {me.status === "loaded" && <span className="text-ink-soft">{me.user.email}</span>}
        </span>
      </div>
    </header>
  );
}
