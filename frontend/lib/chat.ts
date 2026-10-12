/**
 * Pure helpers for the chat (no React, no browser APIs), so tests/chat.test.mjs can run
 * them with Node. Types are type-only imports.
 */

import type { AssistantSource } from "@/lib/types";

export type ChatRole = "user" | "assistant";
export type ChatStatus = "streaming" | "done" | "stopped" | "error";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  at: string; // ISO time
  status: ChatStatus;
  sources?: AssistantSource[];
  retrieval?: "bm25" | "vector" | "hybrid";
  note?: string | null;
  searched?: number;
  writtenBy?: "ai" | "notes" | "general"; // an AI wrote it from the notes, or it IS the notes
  feedback?: "up" | "down"; // the user's rating of this answer (stage 77)
  action?: ProposedAction | null; // stage 78: a change the assistant proposes
  actionState?: "confirmed" | "cancelled";
  actionError?: string | null;
};

/**
 * A change the assistant proposes (stage 78). It never makes it: Confirm sends exactly
 * `method` + `path` + `body` to the app's normal endpoint. "refused" has no request.
 */
export type ProposedAction = {
  kind: "progress" | "link" | "refused";
  skill_id: number;
  skill_name: string;
  summary: string;
  link: string;
  method: "PUT" | "POST" | null;
  path: string | null;
  body: Record<string, unknown> | null;
};

/** Show Confirm / Cancel? Only for a real proposal, on a finished answer, not yet decided. */
export function canConfirm(message: ChatMessage): boolean {
  return (
    message.status === "done" &&
    !!message.action &&
    message.action.kind !== "refused" &&
    message.action.method !== null &&
    message.actionState === undefined
  );
}

/** One line of the /assistant/ask/stream response (NDJSON). */
export type StreamEvent =
  | {
      type: "meta";
      sources: AssistantSource[];
      retrieval: "bm25" | "vector" | "hybrid";
      note: string | null;
      searched: number;
      action?: ProposedAction | null;
    }
  | { type: "delta"; text: string }
  | { type: "replace"; text: string } // the checks changed the answer: show this instead
  | { type: "done"; written_by: "ai" | "notes" | "general"; note: string | null };

/**
 * Network chunks don't line up with lines: a chunk can end halfway through a JSON line.
 * Parse every COMPLETE line and hand back the unfinished rest to prepend to the next chunk.
 */
export function parseNdjson(buffer: string): { events: StreamEvent[]; rest: string } {
  const lines = buffer.split("\n");
  const rest = lines.pop() ?? "";
  const events = lines.filter((line) => line.trim() !== "").map((line) => JSON.parse(line) as StreamEvent);
  return { events, rest };
}

export type TextPart = { kind: "text"; text: string } | { kind: "cite"; number: number };

/** "Learn it [1], then [2]." -> text, cite 1, text, cite 2, text. Only numbers that exist count. */
export function splitCitations(text: string, sourceCount: number): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[(\d+)\]/g)) {
    const number = Number(match[1]);
    if (number < 1 || number > sourceCount) continue; // "[2024]" or a stray bracket stays text
    if (match.index > last) parts.push({ kind: "text", text: text.slice(last, match.index) });
    parts.push({ kind: "cite", number });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}

export type PageContext = { kind: "job"; label: string } | { kind: "skill"; name: string } | null;

export const GENERAL_SUGGESTIONS = [
  "What am I missing for my jobs?",
  "Which skills have no proof yet?",
  "What should I learn first?",
  "Give me an overview",
];

/** Suggestions for where the user is: the current job or skill first, then general ones. */
export function suggestionsFor(context: PageContext): string[] {
  if (context?.kind === "job") {
    return [`What am I missing for ${context.label}?`, `Which skills do I already have for ${context.label}?`, ...GENERAL_SUGGESTIONS.slice(1, 3)];
  }
  if (context?.kind === "skill") {
    return [`Tell me about ${context.name}`, `How do I prove ${context.name}?`, `Which jobs need ${context.name}?`, GENERAL_SUGGESTIONS[2]];
  }
  return GENERAL_SUGGESTIONS;
}

/** Which page are we on? /job-descriptions/7 -> job 7, /skills/3 -> skill 3. */
export function pageTarget(pathname: string): { kind: "job" | "skill"; id: number } | null {
  const job = pathname.match(/^\/job-descriptions\/(\d+)(?:\/|$)/);
  if (job) return { kind: "job", id: Number(job[1]) };
  const skill = pathname.match(/^\/skills\/(\d+)(?:\/|$)/);
  if (skill) return { kind: "skill", id: Number(skill[1]) };
  return null;
}

export const MAX_HISTORY = 4;

/** The last few finished turns, sent with a question so follow-ups ("how do I learn it?") work. */
export type FeedbackBody = {
  message_id: string;
  rating: "up" | "down";
  question: string;
  answer: string;
  sources: { number: number; kind: string; title: string }[];
  retrieval: "bm25" | "vector" | "hybrid" | null;
  written_by: "ai" | "notes" | "general" | null;
  comment: string | null;
};

/**
 * What POST /assistant/feedback needs to record a rating: the answer, the question it
 * answered (the user message just before it), and what the assistant used. null when the
 * message isn't a finished answer to a question.
 */
export function feedbackBody(
  messages: ChatMessage[],
  messageId: string,
  rating: "up" | "down",
  comment = "",
): FeedbackBody | null {
  const index = messages.findIndex((m) => m.id === messageId);
  const answer = messages[index];
  if (!answer || answer.role !== "assistant" || answer.status !== "done") return null;
  const question = messages.slice(0, index).reverse().find((m) => m.role === "user");
  if (!question) return null;
  return {
    message_id: answer.id,
    rating,
    question: question.text,
    answer: answer.text,
    sources: (answer.sources ?? []).slice(0, 10).map((s) => ({ number: s.number, kind: s.kind, title: s.title })),
    retrieval: answer.retrieval ?? null,
    written_by: answer.writtenBy ?? null,
    comment: comment.trim() === "" ? null : comment.trim(),
  };
}

export function historyFor(messages: ChatMessage[]): { role: ChatRole; text: string }[] {
  return messages
    .filter((m) => m.status === "done" && m.text.trim() !== "")
    .slice(-MAX_HISTORY)
    .map((m) => ({ role: m.role, text: m.text }));
}

export const MAX_STORED_MESSAGES = 50;

/** Keep the newest messages; never keep one half-written (a reload can't resume it). */
export function forStorage(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .slice(-MAX_STORED_MESSAGES)
    .map((m) => (m.status === "streaming" ? { ...m, status: "stopped" as const } : m));
}
