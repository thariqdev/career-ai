"""ACTIONS (stage 78): the chat PROPOSES a change; you confirm it; nothing else writes.

Human in the loop, with two safety layers:
1. Rules, not the model, decide whether a message asks for an action (stages 69-70
   showed the model picks wrong tools; rules can't invent one). Anything unclear (a
   question, no skill or two skills named) is not an action: the chat answers normally.
2. The assistant never writes. It returns a proposal: what will change, and the exact
   request to make. The chat shows Confirm / Cancel, and Confirm calls the app's normal
   endpoint, with all its usual checks.

Only two actions exist: set learning progress, and save a learning link. Verifying a
skill, adding evidence and deleting are refused with an explanation, because proof
needs real evidence (PROJECT_RULES.md) and deletions deserve their own page.
"""

import re
from dataclasses import asdict, dataclass
from typing import Literal

from app.core.services.suggestion_service import term_pattern

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_QUESTION = re.compile(r"^\s*(?:is|are|am|do|does|did|what|which|how|why|when|where|who|should)\b", re.IGNORECASE)
_REFUSE = re.compile(r"\b(?:verify|verified|prove|proven|evidence|proof|delete|remove)\b", re.IGNORECASE)
_DELETE = re.compile(r"\b(?:delete|remove)\b", re.IGNORECASE)
_SAVE = re.compile(r"\b(?:save|add|keep|store|bookmark)\b", re.IGNORECASE)
_THEORY = re.compile(r"\b(?:interview|theory|questions)\b", re.IGNORECASE)
_REQUEST = re.compile(r"\b(?:mark|set|put|change|i|i'm|i've|im)\b", re.IGNORECASE)
_NOT_STARTED = re.compile(r"\bnot\s+started\b|\bstop(?:ped)?\s+(?:learning|studying)\b", re.IGNORECASE)
_FINISHED = re.compile(r"\b(?:finished|done|completed?)\b", re.IGNORECASE)
_STUDYING = re.compile(r"\b(?:studying|learning|in\s+progress|started)\b", re.IGNORECASE)

STATUS_LABEL = {"studying": "Studying", "finished": "Finished studying", "not_started": "Not started"}
MODE_LABEL = {"theory_interview": "Theory / Interview", "technical_practical": "Technical / Practical"}


@dataclass(frozen=True)
class Action:
    kind: Literal["progress", "link", "refused"]
    skill_id: int
    skill_name: str
    summary: str  # what will change ("Mark React as Studying?"), or why it's refused
    link: str  # the skill's page
    method: str | None = None  # the request Confirm makes (None when refused)
    path: str | None = None
    body: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _named_skills(text: str, skills: dict[int, tuple[str, list[str]]]) -> list[int]:
    """Ids of the saved skills the text names (by name or nickname, whole terms)."""
    found = []
    for skill_id, (_, terms) in skills.items():
        if any((p := term_pattern(t)) is not None and p.search(text) for t in terms):
            found.append(skill_id)
    return found


def detect_action(message: str, skills: dict[int, tuple[str, list[str]]]) -> Action | None:
    """An action the message asks for, a refusal, or None (not an action, or unclear).

    skills: {skill_id: (name, [name, *aliases])} of the saved skills.
    """
    url_match = _URL.search(message)
    text = _URL.sub(" ", message)  # a link's letters never name a skill
    if _QUESTION.search(text):
        return None
    named = _named_skills(text, skills)
    if len(named) != 1:
        return None
    skill_id = named[0]
    name = skills[skill_id][0]
    page = f"/skills/{skill_id}"

    if _REFUSE.search(text):
        if _DELETE.search(text):
            why = f"I can't delete things from the chat. You can remove {name} on its page, where you can see what else it affects."
        else:
            why = (
                f"I can't verify skills or add proof from the chat. A skill becomes verified only with real "
                f"evidence, which you add and link on {name}'s page."
            )
        return Action("refused", skill_id, name, why, page)

    if url_match and _SAVE.search(text):
        mode = "theory_interview" if _THEORY.search(text) else "technical_practical"
        url = url_match.group(0).rstrip(".,;:!?)")
        title = f"{name} {'interview' if mode == 'theory_interview' else 'tutorial'} link"
        return Action(
            "link", skill_id, name, f"Save this link for {name} ({MODE_LABEL[mode]})? {url}", page,
            "POST", f"/skills/{skill_id}/learning-resources", {"mode": mode, "title": title, "url": url},
        )

    if not _REQUEST.search(text):
        return None
    for pattern, status in ((_NOT_STARTED, "not_started"), (_FINISHED, "finished"), (_STUDYING, "studying")):
        if pattern.search(text):
            return Action(
                "progress", skill_id, name, f"Mark {name} as {STATUS_LABEL[status]}?", page,
                "PUT", f"/skills/{skill_id}/learning-progress", {"status": status},
            )
    return None


def reply_for(action: Action) -> str:
    """What the chat says above the Confirm / Cancel card (or instead of it, when refused)."""
    if action.kind == "refused":
        return action.summary
    return f"I can do that once you confirm. {action.summary} Nothing changes until you click Confirm."
