"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { apiGet } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import { pageTarget, type PageContext } from "@/lib/chat";
import { jobLabel } from "@/lib/jobs";
import { useChat } from "@/lib/chatStore";
import type { JobDescription, Skill } from "@/lib/types";

/**
 * The floating 💬 button on every page (except the full /assistant page) and its chat
 * panel. On a job's or skill's page, the suggestions are about that job or skill.
 * Esc closes the panel and focus returns to the button.
 */
export default function ChatWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [context, setContext] = useState<PageContext>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const { busy } = useChat();
  const target = pageTarget(pathname);
  const targetKey = target ? `${target.kind}:${target.id}` : "";

  // Page-aware suggestions: fetch the job's or skill's name when the panel opens.
  // Fetch first, then set state only in the promise callback.
  useEffect(() => {
    if (!open || targetKey === "") return;
    let active = true;
    const [kind, id] = targetKey.split(":");
    const request =
      kind === "job"
        ? apiGet<JobDescription>(`/job-descriptions/${id}`).then((job): PageContext => ({ kind: "job", label: jobLabel(job, 40) }))
        : apiGet<Skill[]>("/skills").then((skills): PageContext => {
            const skill = skills.find((s) => String(s.id) === id);
            return skill ? { kind: "skill", name: skill.name } : null;
          });
    request.then((found) => active && setContext(found)).catch(() => active && setContext(null));
    return () => {
      active = false;
    };
  }, [open, targetKey]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !document.querySelector("[role=alertdialog]")) {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (pathname === "/assistant") return null; // the full page is already the chat

  return (
    <div className="print:hidden">
      {open && (
        <section
          role="dialog"
          aria-label="Career AI assistant"
          className="fixed bottom-24 right-4 z-40 flex h-[min(34rem,calc(100vh-8rem))] w-[min(26rem,calc(100vw-2rem))] flex-col rounded-xl border border-line bg-surface p-4 shadow-2xl"
        >
          <header className="mb-2 flex items-center justify-between gap-2">
            <h2 className="font-display text-lg text-ink">Assistant</h2>
            <span className="flex items-center gap-3">
              <Link href="/assistant" className="text-xs text-accent underline">
                Open full page
              </Link>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close the assistant"
                className="rounded px-1.5 text-lg leading-none text-ink-soft hover:bg-ground hover:text-ink"
              >
                ×
              </button>
            </span>
          </header>
          <ChatPanel compact context={targetKey ? context : null} autoFocus />
        </section>
      )}
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Close the assistant" : "Open the assistant"}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-accent text-2xl text-surface shadow-lg transition-transform hover:scale-105"
      >
        {open ? "×" : "💬"}
        {busy && !open && <span className="absolute right-1 top-1 h-3 w-3 animate-pulse rounded-full bg-warm" />}
      </button>
    </div>
  );
}
