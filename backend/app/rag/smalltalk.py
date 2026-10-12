"""Small talk: greetings, thanks, goodbyes, "who are you", "help" (stage 91).

Without this, "hi" was searched like a question about the user's data and got "I couldn't
find anything about that", which isn't how an assistant should behave. These replies are
fixed, friendly templates (not the model): instant, and they can't invent anything. Only
a message that is ENTIRELY small talk gets one. A greeting in front of a real question
("hi, what am I missing?") is set aside instead (`strip_greeting`), so the question is
answered normally.
"""

import re

_END = r"[\s!.?,:;)(]*(?:assistant|career ai|bot|there|again|all)?[\s!.?,:;)(]*"
_GREETING = (
    r"(?:hi+|hello+|hey+|hiya|howdy|yo|hola|namaste|greetings|good\s+(?:morning|afternoon|evening|day))"
)
_PATTERNS: dict[str, re.Pattern[str]] = {
    "greeting": re.compile(rf"^\s*{_GREETING}{_END}$", re.IGNORECASE),
    "how_are_you": re.compile(
        rf"^\s*(?:{_GREETING}[\s,!.]*)?(?:how\s+are\s+you(?:\s+doing)?|how'?s\s+it\s+going|what'?s\s+up|sup){_END}$",
        re.IGNORECASE,
    ),
    "thanks": re.compile(r"^\s*(?:thanks?(?:\s+you)?(?:\s+(?:so\s+)?much)?|thank\s+you(?:\s+(?:so\s+)?much)?|thx|ty|cheers|great|awesome|perfect|ok(?:ay)?|cool|nice)" + _END + "$", re.IGNORECASE),
    "bye": re.compile(r"^\s*(?:bye+|goodbye|good\s+night|see\s+(?:you|ya)(?:\s+later)?|cya|later)" + _END + "$", re.IGNORECASE),
    "about": re.compile(
        r"^\s*(?:who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|what\s+do\s+you\s+do|how\s+can\s+you\s+help(?:\s+me)?|help|help\s+me|menu)"
        + _END + "$",
        re.IGNORECASE,
    ),
}
_LEADING_GREETING = re.compile(rf"^\s*{_GREETING}\b[\s,!.:;-]*", re.IGNORECASE)

CAN_DO = (
    "what you're missing for your jobs, which skills still need proof, what to learn first, "
    "or anything about a skill, job, project or proof you've saved"
)


def display_name(full_name: str | None) -> str | None:
    """How to greet the user: their saved name without single-letter initials
    ("B Mohammed Thariq" -> "Mohammed Thariq"). None when no name is saved."""
    if not full_name:
        return None
    words = [w for w in full_name.split() if len(w.rstrip(".")) > 1]
    return " ".join(words) or full_name.strip() or None


def kind_of(message: str) -> str | None:
    """Which small talk this whole message is, or None (it's a real question)."""
    for kind, pattern in _PATTERNS.items():
        if pattern.match(message):
            return kind
    return None


def reply_for(kind: str, name: str | None) -> str:
    hello = f"Hi {name}!" if name else "Hi there!"
    if kind == "greeting":
        return f"{hello} 👋 I'm your Career AI assistant. I can tell you {CAN_DO}. How can I help you today?"
    if kind == "how_are_you":
        return f"I'm doing well, thanks for asking{', ' + name if name else ''}! How can I help with your career today?"
    if kind == "thanks":
        return "You're welcome! Is there anything else you'd like to know about your skills or jobs?"
    if kind == "bye":
        return f"Good luck with your applications{', ' + name if name else ''}! Come back any time."
    return (
        f"I'm your Career AI assistant. I answer from your own data only, and I never invent "
        f"skills or proof. I can tell you {CAN_DO}. Try: \"What am I missing for my jobs?\" or "
        f"\"What should I learn first?\""
    )


def strip_greeting(message: str) -> str:
    """"hi, what am I missing?" -> "what am I missing?" (the greeting alone isn't searched)."""
    rest = _LEADING_GREETING.sub("", message, count=1).strip()
    return rest or message
