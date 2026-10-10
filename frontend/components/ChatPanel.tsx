"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui";
import { useConfirm } from "@/components/ConfirmDialog";
import { splitCitations, suggestionsFor, type ChatMessage, type PageContext } from "@/lib/chat";
import { clear, send, stop, useChat } from "@/lib/chatStore";

const KIND_LABEL: Record<string, string> = {
  overview: "Overview",
  skill: "Skill",
  job: "Job",
  gap: "Gap",
  evidence: "Proof",
  project: "Project",
  work: "Work",
  education: "Education",
};

const RETRIEVAL_LABEL = { bm25: "keyword search", vector: "meaning search", hybrid: "keyword + meaning search" };

function time(iso: string): string {
  const at = new Date(iso);
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
}

/**
 * The chat itself: messages, suggestions, input, Send/Stop and Clear. Used by the
 * floating widget (compact) and the /assistant page. Enter sends, Shift+Enter is a new
 * line. Clicking a [1] citation highlights that source below the answer.
 */
export default function ChatPanel({
  context = null,
  compact = false,
  autoFocus = false,
}: {
  context?: PageContext;
  compact?: boolean;
  autoFocus?: boolean;
}) {
  const { messages, busy } = useChat();
  const [draft, setDraft] = useState("");
  const [highlight, setHighlight] = useState<string | null>(null); // "messageId:number"
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const confirm = useConfirm();

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (draft.trim() === "" || busy) return;
    void send(draft);
    setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  async function handleClear() {
    const ok = await confirm({
      title: "Clear the conversation?",
      message: "Your messages with the assistant are removed from this browser. Your Career AI data isn't affected.",
      confirmLabel: "Clear chat",
      danger: true,
    });
    if (ok) clear();
  }

  return (
    <div className={`flex min-h-0 flex-1 flex-col ${compact ? "text-sm" : ""}`}>
      <div className="min-h-0 flex-1 overflow-y-auto pr-1" aria-live="polite">
        {messages.length === 0 ? (
          <div className="flex flex-col gap-3 py-2">
            <p className="text-sm text-ink-soft">
              Ask about your skills, proof, jobs and what to learn. Answers come from your own data,
              with sources.
            </p>
            <div className="flex flex-wrap gap-2">
              {suggestionsFor(context).map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => void send(suggestion)}
                  className="rounded-full border border-line bg-ground/50 px-3 py-1 text-left text-sm text-ink hover:border-accent"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <ol className="flex flex-col gap-4 py-2">
            {messages.map((message) => (
              <li key={message.id}>
                {message.role === "user" ? (
                  <div className="ml-8 flex flex-col items-end gap-0.5">
                    <p className="whitespace-pre-wrap rounded-2xl rounded-br-sm bg-accent px-4 py-2 text-sm text-surface">
                      {message.text}
                    </p>
                    <span className="text-[11px] text-ink-soft">{time(message.at)}</span>
                  </div>
                ) : (
                  <AssistantBubble
                    message={message}
                    highlight={highlight}
                    onCite={(n) => setHighlight(`${message.id}:${n}`)}
                  />
                )}
              </li>
            ))}
          </ol>
        )}
        <div ref={endRef} />
      </div>

      <form noValidate onSubmit={submit} className="mt-3 flex flex-col gap-2 border-t border-line pt-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            rows={compact ? 2 : 2}
            maxLength={500}
            placeholder="Ask about your skills, jobs or what to learn…"
            aria-label="Your question"
            className="min-h-[2.5rem] flex-1 resize-none rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft"
          />
          {busy ? (
            <Button variant="danger" onClick={stop}>
              Stop
            </Button>
          ) : (
            <Button type="submit" variant="primary" disabled={draft.trim() === ""}>
              Send
            </Button>
          )}
        </div>
        <div className="flex items-center justify-between text-[11px] text-ink-soft">
          <span>Enter to send · Shift+Enter for a new line</span>
          {messages.length > 0 && (
            <button type="button" onClick={handleClear} className="underline hover:text-ink" disabled={busy}>
              Clear chat
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function AssistantBubble({
  message,
  highlight,
  onCite,
}: {
  message: ChatMessage;
  highlight: string | null;
  onCite: (n: number) => void;
}) {
  const sources = message.sources ?? [];
  const thinking = message.status === "streaming" && message.text === "";
  return (
    <div className="mr-8 flex flex-col gap-1">
      <div
        className={`rounded-2xl rounded-bl-sm border px-4 py-2 text-sm ${
          message.status === "error" ? "border-not-verified/40 bg-not-verified-bg text-not-verified" : "border-line bg-surface text-ink"
        }`}
      >
        {thinking ? (
          <span className="inline-flex gap-1 text-ink-soft" aria-label="Thinking">
            <span className="animate-pulse">●</span>
            <span className="animate-pulse [animation-delay:150ms]">●</span>
            <span className="animate-pulse [animation-delay:300ms]">●</span>
          </span>
        ) : (
          <p className="whitespace-pre-wrap">
            {splitCitations(message.text, sources.length).map((part, i) =>
              part.kind === "text" ? (
                <span key={i}>{part.text}</span>
              ) : (
                <button
                  key={i}
                  type="button"
                  onClick={() => onCite(part.number)}
                  className="mx-0.5 rounded bg-accent-soft px-1 text-xs font-medium text-accent hover:bg-accent hover:text-surface"
                  aria-label={`Source ${part.number}`}
                >
                  [{part.number}]
                </button>
              ),
            )}
            {message.status === "streaming" && <span className="ml-0.5 animate-pulse">▍</span>}
          </p>
        )}
        {message.status === "stopped" && <p className="mt-1 text-xs text-ink-soft">(stopped)</p>}
      </div>

      {sources.length > 0 && message.status !== "error" && (
        <div className="flex flex-col gap-1">
          <p className="text-[11px] text-ink-soft">
            Sources · searched {message.searched} notes with {RETRIEVAL_LABEL[message.retrieval ?? "bm25"]}
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {sources.map((source) => (
              <li key={source.number}>
                <Link
                  href={source.link}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                    highlight === `${message.id}:${source.number}`
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-line bg-surface text-ink hover:border-accent"
                  }`}
                  title={source.text}
                >
                  <span className="font-medium">[{source.number}]</span>
                  <span className="text-ink-soft">{KIND_LABEL[source.kind] ?? source.kind}</span>
                  {source.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {message.note && <p className="text-[11px] text-warm">{message.note}</p>}
      {message.status !== "streaming" && <span className="text-[11px] text-ink-soft">{time(message.at)}</span>}
    </div>
  );
}
