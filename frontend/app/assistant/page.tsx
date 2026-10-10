"use client";

import ChatPanel from "@/components/ChatPanel";
import { Card, Page } from "@/components/ui";

/**
 * The full-page Assistant: the same conversation as the floating 💬 widget (one shared
 * chat store), with more room. Answers come from your own data with numbered sources;
 * see docs/RAG_GUIDE.md for how retrieval works.
 */
export default function AssistantPage() {
  return (
    <Page title="Assistant">
      <p className="mt-1 text-sm text-ink-soft">
        Ask about your skills, proof, jobs and gaps. Answers come straight from your own data,
        with the sources they came from. The 💬 button on every other page opens this same chat.
      </p>

      <Card className="mt-6 flex h-[min(42rem,calc(100vh-14rem))] flex-col">
        <ChatPanel autoFocus />
      </Card>

      <p className="mt-3 text-xs text-ink-soft">
        How it works: your data is cut into small notes, and your question is matched to the best
        ones with keyword search (BM25), plus meaning search when a local Ollama embedding model is
        switched on. Answers stream in word by word. An AI-written answer comes in a later step.
      </p>
    </Page>
  );
}
