"""FAITHFULNESS (RAG stage 68): does the answer say only what its notes say?

Citations (stage 67) show WHERE the model looked, not that it read correctly. A cited
answer can still add a skill the notes never mention, or call a skill "verified" when
the note says it isn't. Two kinds of check:

1. Rule checks (`check`), on every answer: instant, free, deterministic, and testable.
   - Every skill the answer names must appear in at least one of its notes. Skill names
     come from the skill catalogue plus your own skills and gaps, aliases included.
   - A sentence that calls a skill verified or proven (not "not verified", "no proof")
     needs a note whose status really is verified or partially proven. This is the
     project's core rule, never invent proof, applied to the model's words.
   They can't catch a misreading that reuses the notes' own words ("AWS is on your CV"
   when the note says AWS is missing), so a failure is certain but a pass is not.

2. A judge (`judge`): a second model call that reads the notes and the answer and says
   YES (faithful) or NO. It can catch misreadings, but it's slower and is itself a model
   that can be wrong. Measured against hand-labelled answers in
   app/rag/faithfulness_eval.py; see docs/RAG_GUIDE.md (stage 68) for the numbers.
"""

import re
from dataclasses import dataclass, field

from app.core.services import suggestion_service
from app.rag.chunker import Chunk
from app.rag.generate import ChatModel, GenerationUnavailableError, Note


@dataclass(frozen=True)
class Verdict:
    problems: list[str] = field(default_factory=list)  # plain-language reasons

    @property
    def ok(self) -> bool:
        return not self.problems


def vocabulary(chunks: list[Chunk]) -> tuple[str, ...]:
    """Skill names known to this user's data (beyond the catalogue): skills and gaps."""
    names = {c.title for c in chunks if c.kind == "skill"}
    names |= {c.title.removesuffix(" gap") for c in chunks if c.kind == "gap"}
    return tuple(sorted(names))


_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")
_PROVEN_WORD = re.compile(r"\b(?:verified|proven|proved)\b", re.IGNORECASE)
_NEGATION = re.compile(
    r"\b(?:not|no|never|none|zero|without|unverified|unproven|yet)\b|n't\b|\b0\b", re.IGNORECASE
)
_PROVEN_NOTE = re.compile(r"status: (?:verified|partially proven)", re.IGNORECASE)


def _note_text(note: Note) -> str:
    return f"{note.title}. {note.text}"


def check(answer: str, notes: list[Note], known_names: tuple[str, ...] = ()) -> Verdict:
    """Rule checks. Any problem means the answer says something its notes don't."""
    problems: list[str] = []
    notes_text = "\n".join(_note_text(n) for n in notes)

    in_answer = suggestion_service.mentioned(answer, known_names)
    in_notes = suggestion_service.mentioned(notes_text, known_names)
    for name in sorted(in_answer - in_notes):
        problems.append(f"it mentions {name}, which isn't in your notes")

    for sentence in _SENTENCES.split(answer):
        if not _PROVEN_WORD.search(sentence) or _NEGATION.search(sentence):
            continue
        named = suggestion_service.mentioned(sentence, known_names)
        proven_notes = [n for n in notes if _PROVEN_NOTE.search(n.text)]
        if named:
            unproven = sorted(
                name for name in named
                if not any(name in suggestion_service.mentioned(_note_text(n), known_names) for n in proven_notes)
            )
            problems += [f"it calls {name} verified, but your notes don't" for name in unproven]
        elif not proven_notes:
            problems.append("it says something is verified, but none of your notes is")
    return Verdict(problems)


# Three judge prompts were measured on the labelled set (llama3.2, 3 runs each, majority):
#   A "Is the answer faithful? YES or NO" (strict system prompt): said NO to all 16 -
#     caught 8/8, false alarms 8/8. Useless: it rejects everything.
#   B "Does it state anything the notes don't? YES or NO": caught 3/8, false alarms 1/8.
#   C (below) check each statement, then a verdict: caught 4/8, false alarms 1/8.
# C is the best, but it's slow and throws away about 1 good answer in 8, so the live
# assistant uses only the rule checks; the judge stays a measuring tool.
JUDGE_INSTRUCTIONS = (
    "Check the answer against the notes. For each statement in the answer, write one short "
    "line: the statement, then SUPPORTED if a note says it or UNSUPPORTED if no note says it "
    "or a note says something different. Finally write exactly one line: VERDICT: FAITHFUL or "
    "VERDICT: UNFAITHFUL."
)
_VERDICT = re.compile(r"VERDICT:\s*(UNFAITHFUL|FAITHFUL)")


def judge(answer: str, notes: list[Note], chat: ChatModel) -> bool | None:
    """Ask the model: is this answer faithful to these notes? None if it can't say."""
    numbered = "\n".join(f"[{n.number}] {_note_text(n)}" for n in notes)
    messages = [{"role": "user", "content": f"Notes:\n{numbered}\n\nAnswer:\n{answer}\n\n{JUDGE_INSTRUCTIONS}"}]
    try:
        reply = "".join(chat.stream(messages)).upper()
    except GenerationUnavailableError:
        return None
    verdicts = _VERDICT.findall(reply)
    if not verdicts:
        return None
    return verdicts[-1] == "FAITHFUL"
