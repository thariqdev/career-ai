"""Measure the assistant's speed: cold start vs warm, and how long models stay loaded.

Run from backend/:   .venv/Scripts/python -m app.rag.latency_eval

A local model must be loaded into memory before it answers. Ollama unloads an idle
model after its keep-alive time (5 minutes by default), so the next question pays the
loading cost again: a COLD START. This script reports, for the chat and embedding models:

- time to first token (TTFT): how long until the first word appears (what makes a
  chat feel fast or slow), and the total time, both cold (just unloaded) and warm
- what /api/ps says is loaded, its memory, and when Ollama will unload it

It unloads the models first (keep_alive 0) to measure a real cold start.
"""

import os
import sys
import time
from datetime import datetime, timezone

import httpx

from app.rag.embeddings import DEFAULT_BASE_URL, OllamaEmbedder
from app.rag.generate import DEFAULT_CHAT_MODEL, OllamaChat

QUESTION = [
    {"role": "system", "content": "Answer in one short sentence."},
    {"role": "user", "content": "Notes:\n[1] Skill: Python. Your status: verified.\n\nQuestion: Is Python verified? Cite [1]."},
]


def unload(base_url: str, model: str) -> None:
    httpx.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)


def loaded(base_url: str) -> list[str]:
    now = datetime.now(timezone.utc)
    lines = []
    for m in httpx.get(f"{base_url}/api/ps", timeout=10).json().get("models", []):
        expires = datetime.fromisoformat(m["expires_at"].replace("Z", "+00:00"))
        minutes = (expires - now).total_seconds() / 60
        lines.append(f"{m['name']}: {m['size'] / 1e9:.1f} GB in memory, unloads in {minutes:.0f} min")
    return lines or ["nothing loaded"]


def time_chat(chat: OllamaChat) -> tuple[float, float]:
    start = time.time()
    first = None
    for _ in chat.stream(QUESTION):
        if first is None:
            first = time.time() - start
    return first or 0.0, time.time() - start


def time_embed(embedder: OllamaEmbedder) -> float:
    start = time.time()
    embedder.embed(["search_query: which skills are verified?"])
    return time.time() - start


def main() -> int:
    base_url = os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL
    chat_model = os.getenv("OLLAMA_CHAT_MODEL") or DEFAULT_CHAT_MODEL
    embed_model = os.getenv("OLLAMA_EMBED_MODEL") or "nomic-embed-text"
    chat, embedder = OllamaChat(chat_model, base_url), OllamaEmbedder(embed_model, base_url=base_url)

    for model in (chat_model, embed_model):
        unload(base_url, model)
    print("after unloading:", "; ".join(loaded(base_url)))

    embed_cold = time_embed(embedder)
    ttft_cold, total_cold = time_chat(chat)
    embed_warm = time_embed(embedder)
    ttft_warm, total_warm = time_chat(chat)

    print(f"\nembedding   cold {embed_cold:6.1f}s   warm {embed_warm:6.2f}s")
    print(f"chat TTFT   cold {ttft_cold:6.1f}s   warm {ttft_warm:6.2f}s")
    print(f"chat total  cold {total_cold:6.1f}s   warm {total_warm:6.2f}s")
    print("\nloaded now:")
    for line in loaded(base_url):
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
