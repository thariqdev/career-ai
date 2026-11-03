"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { isAuthPage } from "@/lib/auth";
import { logOut } from "@/lib/session";
import { useMe } from "@/lib/useMe";
import type { User } from "@/lib/types";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/skills", label: "Skills" },
  { href: "/job-descriptions", label: "Job Descriptions" },
  { href: "/cv", label: "My CV" },
  { href: "/profile", label: "My Profile" },
  { href: "/assistant", label: "Assistant" },
  { href: "/practice", label: "Practice" },
];

// "/" is active only on the Dashboard itself; the others also cover their sub-pages
// (e.g. /skills/3 highlights "Skills").
function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

/** Your name, with a small menu: who you're logged in as, Account, and Log out (stage 99). */
function UserMenu({ user }: { user: User }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const label = user.full_name?.split(" ").filter((part) => part.length > 1)[0] ?? user.email.split("@")[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded-md px-2 py-1 text-sm text-ink hover:bg-ground focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-soft"
      >
        <span className="grid h-7 w-7 place-items-center rounded-full bg-accent-soft font-medium text-accent">
          {label.charAt(0).toUpperCase()}
        </span>
        <span className="max-w-[10rem] truncate">{label}</span>
        <span aria-hidden className="text-xs text-ink-soft">▾</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-2 w-60 rounded-lg border border-line bg-surface p-1.5 shadow-lg">
          <p className="truncate px-3 py-2 font-mono text-xs text-ink-soft">{user.email}</p>
          <Link
            href="/account"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="block rounded-md px-3 py-2 text-sm text-ink hover:bg-ground"
          >
            Account
          </Link>
          <button
            type="button"
            role="menuitem"
            onClick={logOut}
            className="block w-full rounded-md px-3 py-2 text-left text-sm text-ink hover:bg-ground"
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}

/** The shared header, wired into app/layout.tsx so it appears on every page except the
 * account pages (log in, sign up, forgot / reset password), which have their own frame. */
export default function AppHeader() {
  const pathname = usePathname();
  return isAuthPage(pathname) ? null : <HeaderBar pathname={pathname} />;
}

function HeaderBar({ pathname }: { pathname: string }) {
  const me = useMe();

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
          {me.status === "loaded" && <UserMenu user={me.user} />}
        </span>
      </div>
    </header>
  );
}
