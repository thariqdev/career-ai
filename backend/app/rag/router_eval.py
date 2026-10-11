"""Measure the routers: for each question, is the right tool picked (or none)?

Run from backend/:   .venv/Scripts/python -m app.rag.router_eval

Two question sets over the fixed made-up career (jobs: "Backend Engineer at Acme",
"Frontend Developer at Globex"):

- DEV: questions drafted while the keyword rules were being written. Rules usually look
  good on these, because they were written with them in mind.
- HELD_OUT: different phrasings written AFTER the rules, and never used to change them.
  This is the honest score: how the router does on wording nobody planned for.

A routing is right when the tool matches and, for job_gaps, the same jobs are chosen
(None = all jobs). Two kinds of wrong are counted separately, because they cost different
things:
- wrong tool: a tool answered a question it doesn't fit (the worst case: an exact-looking
  answer to the wrong question).
- missed tool: search was used where a tool would be exact (still answered, just less
  reliably).
"""

import os
import sys
import time

from app.rag.generate import DEFAULT_CHAT_MODEL
from app.rag.router import OllamaRouter, keyword_route
from app.rag.tools import ToolCall, matches_job

JOBS = ["Backend Engineer at Acme", "Frontend Developer at Globex"]

T = ToolCall
DEV: list[tuple[str, ToolCall | None]] = [
    ("Which skills have no proof yet?", T("skills_without_proof")),
    ("What skills haven't I proven?", T("skills_without_proof")),
    ("List my unverified skills", T("skills_without_proof")),
    ("Which of my skills still need evidence?", T("skills_without_proof")),
    ("Which skills are verified?", T("verified_skills")),
    ("What have I proven so far?", T("verified_skills")),
    ("Show my proven skills", T("verified_skills")),
    ("Which skills are on my CV?", T("skills_on_cv")),
    ("What does my resume list?", T("skills_on_cv")),
    ("List the skills in my CV", T("skills_on_cv")),
    ("What am I missing for my jobs?", T("job_gaps")),
    ("What gaps do I have?", T("job_gaps")),
    ("What am I missing for the Acme job?", T("job_gaps", "Acme")),
    ("Which skills do I lack for the Backend Engineer role?", T("job_gaps", "Acme")),
    ("What do I need for Globex?", T("job_gaps", "Globex")),
    ("What should I learn first?", T("learn_first")),
    ("Which skill should I focus on next?", T("learn_first")),
    ("Prioritise my learning for me", T("learn_first")),
    ("Tell me about Python", None),
    ("Is my Python skill verified?", None),
    ("Do I know Kubernetes?", None),
    ("What is FundsApp?", None),
    ("Where did I work before?", None),
    ("What is my name?", None),
    ("Tell me about my education", None),
    ("How do I prove Docker?", None),
    ("What's the weather in Paris?", None),
]

HELD_OUT: list[tuple[str, ToolCall | None]] = [
    ("Where am I still lacking evidence?", T("skills_without_proof")),
    ("Anything I claimed but never backed up?", T("skills_without_proof")),
    ("What can I already prove?", T("verified_skills")),
    ("Which abilities are confirmed?", T("verified_skills")),
    ("What did I put on my CV?", T("skills_on_cv")),
    ("Remind me what my résumé says I know", T("skills_on_cv")),
    ("How far am I from the frontend developer position?", T("job_gaps", "Globex")),
    ("Am I ready for Acme?", T("job_gaps", "Acme")),
    ("Across all my applications, what don't I know yet?", T("job_gaps")),
    ("What's the most useful thing to study next?", T("learn_first")),
    ("Give me a learning order", T("learn_first")),
    ("Which job is the best fit for me?", None),
    ("Explain my React status", None),
    ("When did I finish college?", None),
    ("How do I add evidence for a skill?", None),
    ("Is TypeScript on my CV?", None),
]


# Written in stage 70 BEFORE the cascade and its guards existed, and run once at the end.
# HELD_OUT had been looked at by then (its mistakes shaped the stage-70 idea), so it no
# longer counts as unseen; TEST is the honest score.
TEST: list[tuple[str, ToolCall | None]] = [
    ("Show me everything I haven't backed with evidence", T("skills_without_proof")),
    ("Which of my skills are still unconfirmed?", T("skills_without_proof")),
    ("What skills do I have proof for?", T("verified_skills")),
    ("List what I've already verified", T("verified_skills")),
    ("Read my CV skills back to me", T("skills_on_cv")),
    ("What's listed on my CV?", T("skills_on_cv")),
    ("What does Globex want that I don't have?", T("job_gaps", "Globex")),
    ("Am I qualified for the backend engineer job?", T("job_gaps", "Acme")),
    ("What's stopping me from getting the Acme role?", T("job_gaps", "Acme")),
    ("Summarise my gaps across every job", T("job_gaps")),
    ("Which skill would help me with the most jobs?", T("learn_first")),
    ("What should be my next skill?", T("learn_first")),
    ("Is Docker on my CV?", None),
    ("Do I have GraphQL?", None),
    ("Why is React not verified?", None),
    ("How do I mark a skill as verified?", None),
    ("What projects have I built?", None),
    ("Tell me about the Acme job", None),
    ("Is Python proven?", None),
    ("What did I do at Initech?", None),
]


def same(got: ToolCall | None, want: ToolCall | None) -> bool:
    if got is None or want is None:
        return got is None and want is None
    if got.name != want.name:
        return False
    if got.name != "job_gaps":
        return True
    pick = lambda call: {label for label in JOBS if call.job is None or matches_job(label, call.job)}  # noqa: E731
    return pick(got) == pick(want)


def score(router, questions) -> tuple[int, int, int, list[str]]:
    """(right, wrong tool, missed tool, mistakes)"""
    right = wrong = missed = 0
    mistakes = []
    for question, want in questions:
        got = router(question, JOBS)
        if same(got, want):
            right += 1
            continue
        if got is None:
            missed += 1
        else:
            wrong += 1
        show = lambda c: "search" if c is None else c.name + (f"({c.job})" if c.job else "")  # noqa: E731
        mistakes.append(f"    {question!r}: got {show(got)}, want {show(want)}")
    return right, wrong, missed, mistakes


def main() -> int:
    # Without Ollama the tool-calling router answers None every time (all "missed tool").
    model = os.getenv("OLLAMA_CHAT_MODEL") or DEFAULT_CHAT_MODEL
    routers = {"keyword rules": keyword_route, f"tool calling ({model})": OllamaRouter(model).route}
    for name, router in routers.items():
        print(f"\n{name}")
        for label, questions in (("dev", DEV), ("held-out", HELD_OUT)):
            start = time.time()
            right, wrong, missed, mistakes = score(router, questions)
            seconds = (time.time() - start) / len(questions)
            print(
                f"  {label:<9} right {right}/{len(questions)}   wrong tool {wrong}   missed tool {missed}"
                f"   ({seconds:.2f}s per question)"
            )
            for line in mistakes:
                print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
