"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, ApiError } from "@/lib/api";
import { Button, Card, EmptyState, Page, Pill, SectionHeading } from "@/components/ui";
import { useConfirm } from "@/components/ConfirmDialog";
import { BOXES, boxCounts, boxOf, cleanProgress, nextCard, record, type Progress } from "@/lib/leitner";

// Interview flashcards from docs/RAG_GUIDE.md (stage 85). Answer from memory first, then
// reveal: active recall. Leitner boxes (lib/leitner.ts) bring back the cards you miss.
// Progress lives in this browser only: it's a learning aid, not career data.

type FlashCard = { id: string; stage: string; stage_title: string; question: string; answer: string };

const STORAGE_KEY = "career-ai-practice-v1";

function loadProgress(): Progress {
  try {
    return cleanProgress(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}"));
  } catch {
    return {};
  }
}

function saveProgress(progress: Progress): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch {
    // Storage blocked or full: practice still works for this visit.
  }
}

export default function PracticePage() {
  const [cards, setCards] = useState<FlashCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress>({});
  const [stage, setStage] = useState<string>("all");
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const confirm = useConfirm();

  // Fetch first, then set state only in the callbacks.
  useEffect(() => {
    let active = true;
    apiGet<FlashCard[]>("/practice/rag-questions")
      .then((list) => {
        if (!active) return;
        setCards(list);
        setProgress(loadProgress());
      })
      .catch((err) => active && setError(err instanceof ApiError ? err.message : "Could not reach the backend."));
    return () => {
      active = false;
    };
  }, []);

  const stages = useMemo(() => {
    const seen = new Map<string, string>();
    for (const c of cards ?? []) if (!seen.has(c.stage)) seen.set(c.stage, c.stage_title);
    return [...seen.entries()];
  }, [cards]);
  const pool = useMemo(() => (cards ?? []).filter((c) => stage === "all" || c.stage === stage), [cards, stage]);
  const current = pool.find((c) => c.id === currentId) ?? nextCard(pool, progress);
  const counts = boxCounts(pool, progress);

  function answer(knew: boolean) {
    if (!current) return;
    const next = record(progress, current.id, knew);
    setProgress(next);
    saveProgress(next);
    setCurrentId(nextCard(pool, next, current.id)?.id ?? null);
    setRevealed(false);
  }

  function chooseStage(key: string) {
    setStage(key);
    setCurrentId(null);
    setRevealed(false);
  }

  async function reset() {
    const ok = await confirm({
      title: "Reset your practice progress?",
      message: "Every card goes back to box 1. Your cards and career data aren't affected.",
      confirmLabel: "Reset",
      danger: true,
    });
    if (!ok) return;
    setProgress({});
    saveProgress({});
    setCurrentId(null);
    setRevealed(false);
  }

  return (
    <Page title="Interview practice">
      <p className="mt-1 text-sm text-ink-soft">
        Questions from your RAG guide. Answer out loud first, then reveal. Cards you miss come back
        sooner; cards you know move up to box {BOXES}.
      </p>

      {error && <p className="mt-4 text-sm text-not-verified">{error}</p>}
      {!error && cards === null && <p className="mt-4 text-sm text-ink-soft">Loading…</p>}
      {cards !== null && cards.length === 0 && <EmptyState>No questions found in the guide.</EmptyState>}

      {cards !== null && cards.length > 0 && (
        <div className="mt-5 flex flex-col gap-5">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by stage">
            <Pill selected={stage === "all"} onClick={() => chooseStage("all")}>
              All ({cards.length})
            </Pill>
            {stages.map(([key, title]) => (
              <Pill key={key} selected={stage === key} onClick={() => chooseStage(key)} title={title}>
                Stage {key}
              </Pill>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-ink-soft" aria-label="Cards per box">
            {counts.map((n, i) => (
              <span key={i} className={`rounded px-2 py-0.5 ${i === 0 ? "bg-partial-bg text-partial" : i === BOXES - 1 ? "bg-verified-bg text-verified" : "bg-ground"}`}>
                Box {i + 1}: {n}
              </span>
            ))}
            <button type="button" onClick={reset} className="ml-auto underline hover:text-ink">
              Reset progress
            </button>
          </div>

          {current && (
            <Card>
              <SectionHeading
                title={current.question}
                hint={`Stage ${current.stage}: ${current.stage_title} · box ${boxOf(progress, current.id)}`}
              />
              {revealed ? (
                <>
                  <p className="mt-4 whitespace-pre-wrap rounded-md bg-accent-soft px-4 py-3 text-sm text-ink">
                    {current.answer.replaceAll("**", "")}
                  </p>
                  <div className="mt-4 flex gap-2">
                    <Button variant="primary" onClick={() => answer(true)}>
                      I knew it
                    </Button>
                    <Button onClick={() => answer(false)}>Not yet</Button>
                  </div>
                </>
              ) : (
                <Button className="mt-4" variant="primary" onClick={() => setRevealed(true)}>
                  Show answer
                </Button>
              )}
            </Card>
          )}
        </div>
      )}
    </Page>
  );
}
