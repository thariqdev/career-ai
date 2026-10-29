"""Measure the faithfulness checks against hand-labelled answers.

Run from backend/:   .venv/Scripts/python -m app.rag.faithfulness_eval

"Who checks the checker?" A check is only useful if it agrees with a careful human. So
LABELLED holds answers written and labelled by hand, over the same fixed made-up career
as app/rag/evaluate.py: faithful ones, and unfaithful ones of the kinds a small model
really produces (an extra skill, a false "verified", a status or job mixed up, a wrong
date). Each check is scored on them:

- caught: unfaithful answers it flagged (higher is better; missing one lets a wrong
  answer through)
- false alarms: faithful answers it flagged (lower is better; each one throws away a
  good answer and shows the plain notes instead)

The rule checks run anywhere. The judge needs Ollama (OLLAMA_CHAT_MODEL, default llama3.2)
and runs each answer JUDGE_RUNS times, because a model doesn't always say the same thing.
"""

import sys
from dataclasses import dataclass

from app.rag.evaluate import build_fixture_chunks
from app.rag.faithfulness import check, judge, vocabulary
from app.rag.generate import Note

JUDGE_RUNS = 3


@dataclass(frozen=True)
class Labelled:
    notes: tuple[tuple[str, str], ...]  # (kind, title) of the notes the answer was given
    answer: str
    faithful: bool
    why: str


LABELLED = [
    # --- faithful -------------------------------------------------------------------------
    Labelled((("skill", "Python"),), "Yes, Python is verified, proven by your FundsApp repo [1].", True,
             "says what the note says"),
    Labelled((("gap", "Kubernetes gap"), ("gap", "AWS gap")),
             "For the Backend Engineer job at Acme you're missing Kubernetes [1] and AWS [2].", True, "both gaps, right job"),
    Labelled((("skill", "React"),), "You're studying React right now [1].", True, "learning status"),
    Labelled((("education", "Chinmaya College"),), "You studied a BCA at Chinmaya College [1].", True, "education"),
    Labelled((("work", "Backend Intern at Initech"),), "You were a Backend Intern at Initech in 2023 [1].", True, "work"),
    Labelled((("skill", "Docker"),), "No, Docker isn't verified yet. It's on your CV, but no proof is linked [1].", True,
             "a negated 'verified' is fine"),
    Labelled((("project", "FundsApp"),), "FundsApp is a budgeting API built with Python and PostgreSQL [1].", True,
             "skills named by the note itself"),
    Labelled((("gap", "GraphQL gap"),),
             "To close the GraphQL gap, learn GraphQL, then build a project with it and link it as evidence [1].", True,
             "the note's own advice"),
    # --- unfaithful -----------------------------------------------------------------------
    Labelled((("gap", "Kubernetes gap"), ("gap", "AWS gap")),
             "You're missing Kubernetes [1], AWS [2] and Terraform [1].", False, "Terraform is in no note"),
    Labelled((("skill", "Docker"),), "Docker is verified [1].", False, "the note says not verified"),
    Labelled((("skill", "React"),), "Your React skill is proven, and you're studying it [1].", False,
             "React isn't proven"),
    Labelled((("gap", "Kubernetes gap"), ("gap", "AWS gap")),
             "Kubernetes and AWS are on your CV but not proven yet [1][2].", False, "they're missing, not on the CV"),
    Labelled((("gap", "AWS gap"),), "AWS is missing for the Frontend Developer job [1].", False,
             "the note says the Backend Engineer job"),
    Labelled((("work", "Backend Intern at Initech"),), "You were a Backend Intern at Initech from 2019 to 2021 [1].",
             False, "wrong dates"),
    Labelled((("education", "Chinmaya College"),), "You have a Master's degree from Chinmaya College [1].", False,
             "the note says BCA"),
    Labelled((("skill", "Python"),), "Python is verified by your work at Initech [1].", False,
             "the proof is the FundsApp repo"),
]


def _notes(chunks, keys) -> list[Note]:
    by_key = {(c.kind, c.title): c for c in chunks}
    missing = [k for k in keys if k not in by_key]
    if missing:
        raise ValueError(f"Labelled case names notes that don't exist: {missing}")
    return [Note(i, by_key[k].kind, by_key[k].title, by_key[k].text) for i, k in enumerate(keys, start=1)]


def score(flags: list[bool | None]) -> tuple[int, int, int, int]:
    """(caught, unfaithful total, false alarms, faithful total). A flag is True = 'unfaithful'."""
    caught = sum(1 for case, flag in zip(LABELLED, flags) if not case.faithful and flag)
    alarms = sum(1 for case, flag in zip(LABELLED, flags) if case.faithful and flag)
    bad = sum(1 for case in LABELLED if not case.faithful)
    return caught, bad, alarms, len(LABELLED) - bad


def main() -> int:
    chunks = build_fixture_chunks()
    known = vocabulary(chunks)
    rule_flags = [not check(c.answer, _notes(chunks, c.notes), known).ok for c in LABELLED]

    from app.rag.evaluate import eval_chat

    chat = eval_chat()
    judge_flags: list[bool | None] = []
    judge_detail: list[str] = []
    for case in LABELLED:
        votes = [judge(case.answer, _notes(chunks, case.notes), chat) for _ in range(JUDGE_RUNS)]
        if all(v is None for v in votes):
            judge_flags.append(None)
            judge_detail.append("n/a")
            continue
        no_votes = sum(1 for v in votes if v is False)
        judge_flags.append(no_votes * 2 > JUDGE_RUNS)  # majority says NO
        judge_detail.append("".join("Y" if v else "N" if v is False else "?" for v in votes))

    print(f"{len(LABELLED)} hand-labelled answers\n")
    print(f"{'label':<11}{'rules':<8}{'judge':<8}answer   (why)")
    for case, rule, jflag, detail in zip(LABELLED, rule_flags, judge_flags, judge_detail):
        label = "faithful" if case.faithful else "UNFAITHFUL"
        print(f"{label:<11}{'flag' if rule else '-':<8}{detail:<8}{case.answer[:60]}   ({case.why})")
    print()
    caught, bad, alarms, good = score(rule_flags)
    print(f"rule checks : caught {caught}/{bad} unfaithful, false alarms {alarms}/{good}")
    if any(f is not None for f in judge_flags):
        caught, bad, alarms, good = score(judge_flags)
        print(f"judge ({chat.name}, majority of {JUDGE_RUNS}): caught {caught}/{bad} unfaithful, false alarms {alarms}/{good}")
        both = [r or bool(j) for r, j in zip(rule_flags, judge_flags)]
        caught, bad, alarms, good = score(both)
        print(f"rules OR judge: caught {caught}/{bad} unfaithful, false alarms {alarms}/{good}")
    else:
        print("judge not scored: Ollama isn't available")
    return 0


if __name__ == "__main__":
    sys.exit(main())
