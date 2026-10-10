"use client";

/**
 * One conversation, shared by the floating chat widget and the /assistant page.
 *
 * A tiny external store read with React's useSyncExternalStore: components subscribe,
 * and every change hands them a new messages array. The history is kept in this
 * browser's localStorage (newest 50 messages) so it survives page changes and reloads.
 * That's a convenience only: if storage is unavailable (private window, blocked), the
 * chat simply starts empty. On the server there's no history (the snapshot is empty), so
 * the first render matches and there's no hydration mismatch.
 */

import { useSyncExternalStore } from "react";
import { apiStream, ApiError } from "@/lib/api";
import { forStorage, type ChatMessage, type StreamEvent } from "@/lib/chat";

const STORAGE_KEY = "career-ai-chat-v1";
const EMPTY: ChatMessage[] = [];

let messages: ChatMessage[] = EMPTY;
let loaded = false;
let controller: AbortController | null = null;
const listeners = new Set<() => void>();

function load(): void {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved) messages = forStorage(JSON.parse(saved) as ChatMessage[]);
  } catch {
    messages = EMPTY; // unreadable or blocked storage: start fresh
  }
}

function set(next: ChatMessage[]): void {
  messages = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(forStorage(next)));
  } catch {
    // Storage full or blocked: the chat still works for this visit.
  }
  listeners.forEach((listener) => listener());
}

function update(id: string, change: (m: ChatMessage) => ChatMessage): void {
  set(messages.map((m) => (m.id === id ? change(m) : m)));
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): ChatMessage[] {
  load();
  return messages;
}

function getServerSnapshot(): ChatMessage[] {
  return EMPTY;
}

let counter = 0;
function newId(): string {
  counter += 1;
  return `${Date.now().toString(36)}-${counter}`;
}

/** Ask a question; the answer streams into a new assistant message. */
export async function send(question: string): Promise<void> {
  const text = question.trim();
  if (text === "" || controller !== null) return;
  const now = new Date().toISOString();
  const answerId = newId();
  set([
    ...messages,
    { id: newId(), role: "user", text, at: now, status: "done" },
    { id: answerId, role: "assistant", text: "", at: now, status: "streaming" },
  ]);
  controller = new AbortController();
  try {
    await apiStream<StreamEvent>(
      "/assistant/ask/stream",
      { question: text },
      (event) => {
        if (event.type === "meta") {
          update(answerId, (m) => ({ ...m, sources: event.sources, retrieval: event.retrieval, note: event.note, searched: event.searched }));
        } else if (event.type === "delta") {
          update(answerId, (m) => ({ ...m, text: m.text + event.text }));
        } else {
          update(answerId, (m) => ({ ...m, status: "done", at: new Date().toISOString() }));
        }
      },
      controller.signal,
    );
  } catch (error) {
    if (controller?.signal.aborted) {
      update(answerId, (m) => ({ ...m, status: "stopped" }));
    } else {
      const message = error instanceof ApiError ? error.message : "Could not reach the backend.";
      update(answerId, (m) => ({ ...m, status: "error", text: message }));
    }
  } finally {
    controller = null;
    listeners.forEach((listener) => listener()); // "busy" changed
  }
}

/** Stop the answer that's being written. */
export function stop(): void {
  controller?.abort();
}

export function clear(): void {
  stop();
  set([]);
}

/** The conversation, and whether an answer is being written right now. */
export function useChat(): { messages: ChatMessage[]; busy: boolean } {
  const current = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return { messages: current, busy: current.some((m) => m.status === "streaming") };
}
