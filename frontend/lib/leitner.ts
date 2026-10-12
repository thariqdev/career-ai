/**
 * Spaced repetition with Leitner boxes (stage 85), for the interview flashcards.
 *
 * Every card starts in box 1. "I knew it" moves it up a box (to at most BOXES); "Not yet"
 * sends it back to box 1. The next card is always one from the LOWEST box, so practice
 * time goes to what you don't know yet; among those, the one seen least often; never the
 * card you just answered (unless it's the only one). Pure functions: no React, no storage,
 * so tests/leitner.test.mjs runs them with Node.
 */

export const BOXES = 5;

export type CardProgress = { box: number; seen: number };
export type Progress = Record<string, CardProgress>;

export function boxOf(progress: Progress, id: string): number {
  return progress[id]?.box ?? 1;
}

/** The progress after answering one card. */
export function record(progress: Progress, id: string, knew: boolean): Progress {
  const current = progress[id] ?? { box: 1, seen: 0 };
  return {
    ...progress,
    [id]: { box: knew ? Math.min(current.box + 1, BOXES) : 1, seen: current.seen + 1 },
  };
}

/** The card to practise next, or null when there are none. */
export function nextCard<T extends { id: string }>(cards: T[], progress: Progress, lastId: string | null = null): T | null {
  const pool = cards.length > 1 ? cards.filter((c) => c.id !== lastId) : cards;
  let best: T | null = null;
  for (const card of pool) {
    if (best === null) {
      best = card;
      continue;
    }
    const [box, bestBox] = [boxOf(progress, card.id), boxOf(progress, best.id)];
    const [seen, bestSeen] = [progress[card.id]?.seen ?? 0, progress[best.id]?.seen ?? 0];
    if (box < bestBox || (box === bestBox && seen < bestSeen)) best = card;
  }
  return best;
}

/** How many of these cards are in each box: index 0 is box 1. */
export function boxCounts(cards: { id: string }[], progress: Progress): number[] {
  const counts = Array.from({ length: BOXES }, () => 0);
  for (const card of cards) counts[boxOf(progress, card.id) - 1] += 1;
  return counts;
}

/** Keep only entries that are well-formed (storage can hold anything). */
export function cleanProgress(raw: unknown): Progress {
  if (typeof raw !== "object" || raw === null) return {};
  const out: Progress = {};
  for (const [id, value] of Object.entries(raw as Record<string, unknown>)) {
    const v = value as Partial<CardProgress>;
    if (Number.isInteger(v?.box) && Number.isInteger(v?.seen) && v.box! >= 1 && v.box! <= BOXES && v.seen! >= 0) {
      out[id] = { box: v.box!, seen: v.seen! };
    }
  }
  return out;
}
