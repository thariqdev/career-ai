"use client";

import Link from "next/link";
import { useMe } from "@/lib/useMe";

/** The shared header, wired into app/layout.tsx so it appears on every page. */
export default function AppHeader() {
  const me = useMe();

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-6 px-6 py-4">
        <span className="font-display text-xl text-ink">Career AI</span>

        <nav className="flex gap-6 text-sm text-ink-soft">
          <Link href="/" className="hover:text-ink">
            Dashboard
          </Link>
          <Link href="/skills" className="hover:text-ink">
            Skills
          </Link>
          <Link href="/job-descriptions" className="hover:text-ink">
            Job Descriptions
          </Link>
          <Link href="/cv" className="hover:text-ink">
            My CV
          </Link>
        </nav>

        <span className="font-mono text-xs text-ink-soft">
          {me.status === "loading" && "…"}
          {me.status === "error" && "offline"}
          {me.status === "loaded" && me.user.email}
        </span>
      </div>
    </header>
  );
}
