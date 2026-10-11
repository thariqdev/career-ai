"""QUERY REWRITING (RAG stage 73): turn a follow-up into a question that stands alone.

"And for Globex?" means nothing to search on its own. Since stage 67 the search text has
been the question glued to the previous question ("And for Globex? What am I missing for
the Acme job?"): it finds the right topic, but drags the old one (Acme) in too, and it
breaks when the follow-up changes topic. A rewrite asks the model for the question the
person meant: "What am I missing for the Globex job?".

Only the SEARCH and the tool ROUTING use the rewrite. The model that writes the answer
still sees the real question and the chat history, so a bad rewrite can at worst fetch
the wrong notes, and the citation and faithfulness checks still apply.

No history means no rewrite (a first question is already standalone). Any failure (the
model is off, or its reply is empty, too long, or several lines) returns None, and the
caller falls back to the old glued text.
"""

from app.rag.generate import ChatModel, GenerationUnavailableError, Turn

MAX_REWRITE_CHARS = 300

REWRITE_SYSTEM = """You rewrite a user's last question so it can be understood without the \
conversation. Replace words like "it", "that", "there", "them" and phrases like \
"and for X?" or "what about X?" with what they refer to in the conversation. If the last \
question is already complete or is about something new, return it unchanged. Reply with \
the rewritten question only: one line, no quotes, no explanation."""


def needs_rewrite(history: list[Turn]) -> bool:
    return any(turn.role == "user" for turn in history)


def standalone_question(question: str, history: list[Turn], chat: ChatModel) -> str | None:
    """The follow-up as a standalone question, or None (no history, or no usable rewrite)."""
    if not needs_rewrite(history):
        return None
    recent = history[-2:]  # the previous question and its answer
    conversation = "\n".join(f"{'User' if t.role == 'user' else 'Assistant'}: {t.text[:400]}" for t in recent)
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM},
        {"role": "user", "content": f"Conversation:\n{conversation}\n\nLast question: {question}\n\nRewritten question:"},
    ]
    try:
        reply = "".join(chat.stream(messages)).strip()
    except GenerationUnavailableError:
        return None
    for prefix in ("Rewritten question:", "Standalone question:"):
        if reply.lower().startswith(prefix.lower()):
            reply = reply[len(prefix):].strip()
    reply = reply.strip().strip('"').strip("'").strip()
    if not reply or "\n" in reply or len(reply) > MAX_REWRITE_CHARS:
        return None
    return reply
