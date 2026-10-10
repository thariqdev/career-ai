"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { apiPost, ApiError } from "@/lib/api";
import { Button, Card, FieldError, Page, inputClasses, invalidClasses } from "@/components/ui";
import type { AssistantAnswer } from "@/lib/types";

// Questions that show off what retrieval can find in your own data.
const EXAMPLES = [
  "What am I missing for my jobs?",
  "Which skills have no proof yet?",
  "What should I learn first?",
  "Tell me about Python",
  "Give me an overview",
];

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

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; reply: AssistantAnswer }
  | { role: "error"; text: string };

/**
 * The Career AI assistant (RAG stage 65): your question is matched against small notes
 * built from your own data (BM25 keyword search), and the reply IS the best notes,
 * numbered as sources. No AI writes anything yet, so it can't make things up. The
 * conversation lives only on this page (nothing is saved).
 */
export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, asking]);

  async function ask(text: string) {
    const q = text.trim();
    if (q === "") {
      setQuestionError("Type a question first.");
      return;
    }
    setQuestionError(null);
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setAsking(true);
    try {
      const reply = await apiPost<AssistantAnswer>("/assistant/ask", { question: q });
      setMessages((prev) => [...prev, { role: "assistant", reply }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "error", text: err instanceof ApiError ? err.message : "Could not reach the backend." },
      ]);
    } finally {
      setAsking(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  return (
    <Page title="Assistant">
      <p className="mt-1 text-sm text-ink-soft">
        Ask about your skills, proof, jobs and gaps. Answers come straight from your own data, with
        the sources they came from.
      </p>

      <Card className="mt-6">
        {messages.length === 0 && (
          <div>
            <p className="text-sm text-ink">Try one of these:</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => ask(example)}
                  className="rounded-full border border-line bg-ground/50 px-3 py-1 text-sm text-ink hover:border-accent"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-4">
          {messages.map((message, i) =>
            message.role === "user" ? (
              <div key={i} className="self-end rounded-lg bg-accent px-4 py-2 text-sm text-surface">
                {message.text}
              </div>
            ) : message.role === "error" ? (
              <p key={i} className="text-sm text-not-verified">
                {message.text}
              </p>
            ) : (
              <Reply key={i} reply={message.reply} />
            ),
          )}
          {asking && <p className="text-sm text-ink-soft">Searching your data…</p>}
          <div ref={endRef} />
        </div>

        <form noValidate onSubmit={handleSubmit} className="mt-5 flex flex-col gap-1 border-t border-line pt-4">
          <div className="flex gap-2">
            <input
              value={question}
              onChange={(e) => {
                setQuestion(e.target.value);
                setQuestionError(null);
              }}
              maxLength={500}
              placeholder="Ask about your skills, jobs or what to learn…"
              aria-label="Your question"
              aria-invalid={questionError !== null}
              className={`${inputClasses} flex-1 ${questionError ? invalidClasses : ""}`}
            />
            <Button type="submit" variant="primary" disabled={asking}>
              Ask
            </Button>
          </div>
          <FieldError message={questionError} />
        </form>
      </Card>

      <p className="mt-3 text-xs text-ink-soft">
        How it works: your data is cut into small notes, and your question is matched to the best
        ones with keyword search (BM25). A smarter, AI-written answer comes in a later step.
      </p>
    </Page>
  );
}

function Reply({ reply }: { reply: AssistantAnswer }) {
  if (reply.sources.length === 0) {
    return <p className="rounded-lg bg-ground/60 px-4 py-3 text-sm text-ink">{reply.answer}</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-ink">
        Here&apos;s what I found in your data{" "}
        <span className="text-xs text-ink-soft">(searched {reply.searched} notes)</span>:
      </p>
      {reply.sources.map((source) => (
        <div key={source.number} className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent text-xs text-surface">
              {source.number}
            </span>
            <span className="rounded bg-ground px-1.5 py-0.5 text-xs text-ink-soft">
              {KIND_LABEL[source.kind] ?? source.kind}
            </span>
            <span className="font-medium text-ink">{source.title}</span>
            <Link href={source.link} className="ml-auto text-xs text-accent underline">
              Open →
            </Link>
          </div>
          <p className="mt-1 text-ink-soft">{source.text}</p>
        </div>
      ))}
    </div>
  );
}
