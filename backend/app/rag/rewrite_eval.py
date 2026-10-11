"""Measure how follow-up questions are searched: alone, glued to the last question, or rewritten.

Run from backend/:   .venv/Scripts/python -m app.rag.rewrite_eval

FOLLOW_UPS was written and committed BEFORE any rewrite code existed (stage 73), over the
fixed made-up career in app/rag/evaluate.py. Each case: the previous turn (question and
answer), the follow-up, the notes that should be found (kind, title), and the tool that
should answer it (None = search). It includes traps: follow-ups that change topic (gluing
on the old question drags the old topic in) and questions with no history at all.
"""

from dataclasses import dataclass

from app.rag.generate import Turn
from app.rag.tools import ToolCall

T = ToolCall


@dataclass(frozen=True)
class FollowUp:
    history: tuple[Turn, ...]
    question: str
    expected: frozenset[tuple[str, str]]  # (kind, title) of the notes that should be found
    tool: ToolCall | None


def _h(question: str, answer: str) -> tuple[Turn, ...]:
    return (Turn("user", question), Turn("assistant", answer))


def _f(history, question, expected, tool=None) -> FollowUp:
    return FollowUp(history, question, frozenset(expected), tool)


FOLLOW_UPS: list[FollowUp] = [
    # --- follow-ups that need the previous turn ---------------------------------------------
    _f(_h("What am I missing for the Acme job?", "You're missing Kubernetes [1] and AWS [2]."),
       "And for Globex?", {("gap", "GraphQL gap")}, T("job_gaps", "Globex")),
    _f(_h("Is my Python skill verified?", "Yes, Python is verified by your FundsApp repo [1]."),
       "Which project is that from?", {("project", "FundsApp"), ("evidence", "FundsApp repo")}),
    _f(_h("Tell me about React", "React is on your CV and you're studying it now [1]."),
       "Is it verified?", {("skill", "React")}),
    _f(_h("Do I know Kubernetes?", "No, Kubernetes is missing for the Backend Engineer job [1]."),
       "Which job needs it?", {("gap", "Kubernetes gap")}),
    _f(_h("Which skills have no proof yet?", "Docker, Git, PostgreSQL, React and TypeScript [1]."),
       "What about the verified ones?", {("skill", "Python")}, T("verified_skills")),
    _f(_h("Tell me about my education", "You studied a BCA at Chinmaya College [1]."),
       "When did I finish?", {("education", "Chinmaya College")}),
    _f(_h("Where did I work before?", "You were a Backend Intern at Initech [1]."),
       "What was my role there?", {("work", "Backend Intern at Initech")}),
    _f(_h("What should I learn first?", "AWS, GraphQL and Kubernetes, each needed by 1 job [1]."),
       "Why AWS?", {("gap", "AWS gap")}),
    _f(_h("Tell me about the Frontend Developer job", "It's at Globex; you match 67% of it [1]."),
       "What am I missing for it?", {("gap", "GraphQL gap")}, T("job_gaps", "Globex")),
    _f(_h("Is Docker verified?", "No, Docker has no proof yet [1]."),
       "How do I prove it?", {("skill", "Docker")}),
    _f(_h("Is TypeScript on my CV?", "Yes, TypeScript is on your CV [1]."),
       "And PostgreSQL?", {("skill", "PostgreSQL")}),
    _f(_h("Do I have a GraphQL gap?", "Yes, for the Frontend Developer job at Globex [1]."),
       "What about AWS?", {("gap", "AWS gap")}),
    _f(_h("Which project proves my Python?", "Your FundsApp repo [1]."),
       "Which skills does it prove?", {("evidence", "FundsApp repo")}),
    _f(_h("What jobs need Docker?", "None of your jobs need Docker [1]."),
       "Is it on my CV?", {("skill", "Docker")}),
    _f(_h("What am I missing for my jobs?", "Kubernetes and AWS for Acme, GraphQL for Globex [1]."),
       "Which one should I learn first?", {("overview", "Your overview")}, T("learn_first")),
    # --- follow-ups that change topic (the old question must NOT drag the search back) ------
    _f(_h("What am I missing for the Acme job?", "You're missing Kubernetes [1] and AWS [2]."),
       "Where did I study?", {("education", "Chinmaya College")}),
    _f(_h("Tell me about Python", "Python is verified by your FundsApp repo [1]."),
       "What did I do at Initech?", {("work", "Backend Intern at Initech")}),
    _f(_h("Tell me about Python", "Python is verified by your FundsApp repo [1]."),
       "What's my name?", {("profile", "Your name and profile")}),
    # --- no history: must work exactly as before -------------------------------------------
    _f((), "What is FundsApp?", {("project", "FundsApp")}),
    _f((), "Which skills are on my CV?", {("overview", "Your overview")}, T("skills_on_cv")),
]


# --- the measurement (written after FOLLOW_UPS was committed) -----------------------------


def main() -> int:
    import os
    import sys
    import time

    from app.rag.assistant import retrieve
    from app.rag.evaluate import K, _ollama_embedder, build_fixture_chunks, reciprocal_rank, recall_at_k
    from app.rag.faithfulness import vocabulary
    from app.rag.generate import DEFAULT_CHAT_MODEL, OllamaChat
    from app.rag.rewrite import standalone_question
    from app.rag.router import guarded_keyword_route
    from app.rag.router_eval import same

    chunks = build_fixture_chunks()
    keys = [(c.kind, c.title) for c in chunks]
    jobs = [c.title for c in chunks if c.kind == "job"]
    known = vocabulary(chunks)
    embedder, info = _ollama_embedder()
    chat = OllamaChat(os.getenv("OLLAMA_CHAT_MODEL") or DEFAULT_CHAT_MODEL, temperature=0.0)
    print(f"search: {'hybrid (' + info + ')' if embedder else 'bm25 (' + info + ')'}, top {K}\n")

    def glued(case: FollowUp) -> str:
        previous = next((t.text for t in reversed(case.history) if t.role == "user"), "")
        return f"{case.question} {previous}".strip()

    rewrites: dict[int, str | None] = {}
    seconds: list[float] = []
    for i, case in enumerate(FOLLOW_UPS):
        start = time.time()
        rewrites[i] = standalone_question(case.question, list(case.history), chat)
        if case.history:
            seconds.append(time.time() - start)

    strategies = {
        # (search text, routing text) per case
        "alone": lambda i, c: (c.question, c.question),
        "glued (live before 73)": lambda i, c: (glued(c), c.question),
        "rewritten": lambda i, c: (rewrites[i] or glued(c), rewrites[i] or c.question),
    }
    for name, texts in strategies.items():
        recall = mrr = 0.0
        right = wrong = missed = 0
        for i, case in enumerate(FOLLOW_UPS):
            search_text, route_text = texts(i, case)
            found = [keys[j] for j, _ in retrieve(chunks, search_text, K, embedder).hits]
            recall += recall_at_k(found, set(case.expected), K)
            mrr += reciprocal_rank(found, set(case.expected), K)
            call = guarded_keyword_route(route_text, jobs, known)
            if same(call, case.tool):
                right += 1
            elif call is None:
                missed += 1
            else:
                wrong += 1
        n = len(FOLLOW_UPS)
        print(f"{name:<24} recall@{K} {recall / n:.3f}   MRR {mrr / n:.3f}   "
              f"tool right {right}/{n}, wrong {wrong}, missed {missed}")

    print(f"\nrewrite time: {sum(seconds) / max(len(seconds), 1):.2f}s per follow-up (model: {chat.name})")
    print("\nrewrites:")
    for i, case in enumerate(FOLLOW_UPS):
        if case.history:
            print(f"  {case.question!r:38} -> {rewrites[i]!r}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
