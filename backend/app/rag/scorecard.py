"""One command for every RAG measurement, compared with the saved "known good" numbers.

Run from backend/:
    .venv/Scripts/python -m app.rag.scorecard            quick: no Ollama needed
    .venv/Scripts/python -m app.rag.scorecard --full     plus the real-model measures
    add --save to store the numbers as the new baseline (after a deliberate improvement)

Why: every stage measured something (retrieval, faithfulness, routing, follow-ups,
answer quality). A change that helps one can quietly hurt another, so before trusting a
change to a prompt, a rule or a model, run them all and compare with the BASELINE
(app/rag/scorecard_baseline.json). Anything worse than its baseline by more than its
tolerance is a regression (❌) and the command exits with code 1.

Quick measures are deterministic (fixed data, no model), so their tolerance is 0, and
tests/test_rag_scorecard.py runs them with the normal test suite. Real-model measures
vary from run to run, so they get a small tolerance and are run by hand (--full).
"""

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

BASELINE_FILE = Path(__file__).with_name("scorecard_baseline.json")


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    higher_is_better: bool
    tolerance: float  # how much worse than the baseline still counts as "the same"
    full: bool = False  # needs the real models


def quick() -> list[Metric]:
    """Deterministic measures: fixed made-up career, keyword search, rules."""
    from app.rag import faithfulness_eval, rewrite_eval, router_eval
    from app.rag.evaluate import build_fixture_chunks, evaluate, summary
    from app.rag.faithfulness import check, vocabulary
    from app.rag.router import guarded_keyword_route

    chunks = build_fixture_chunks()
    known = vocabulary(chunks)
    recall, mrr = summary(evaluate(chunks, stem=False))
    flags = [
        not check(c.answer, faithfulness_eval._notes(chunks, c.notes), known).ok for c in faithfulness_eval.LABELLED
    ]
    caught, _, alarms, _ = faithfulness_eval.score(flags)
    route = lambda q, jobs: guarded_keyword_route(q, jobs, known)  # noqa: E731
    routing = {name: router_eval.score(route, qs) for name, qs in
               (("dev", router_eval.DEV), ("held_out", router_eval.HELD_OUT), ("test", router_eval.TEST))}
    glued = rewrite_eval.measure(lambda i, c: (rewrite_eval.glued(c), c.question))
    return [
        Metric("retrieval: keyword recall@4", recall, True, 0),
        Metric("retrieval: keyword MRR", mrr, True, 0),
        Metric("faithfulness rules: wrong answers caught (of 8)", caught, True, 0),
        Metric("faithfulness rules: right answers rejected (of 8)", alarms, False, 0),
        *(Metric(f"routing ({name}): right", r[0], True, 0) for name, r in routing.items()),
        Metric("routing (all sets): wrong tools", sum(r[1] for r in routing.values()), False, 0),
        Metric("follow-ups (glued, keyword): recall@4", glued.recall, True, 0),
        Metric("follow-ups (glued, keyword): MRR", glued.mrr, True, 0),
    ]


def full() -> list[Metric]:
    """Real-model measures (Ollama): meaning search, rewriting, written answers."""
    import os

    from app.rag import answer_eval, rewrite_eval
    from app.rag.evaluate import _ollama_embedder, build_fixture_chunks, evaluate, summary
    from app.rag.generate import DEFAULT_CHAT_MODEL, OllamaChat

    embedder, info = _ollama_embedder()
    if embedder is None:
        raise RuntimeError(f"Ollama isn't available for --full: {info}")
    model = os.getenv("OLLAMA_CHAT_MODEL") or DEFAULT_CHAT_MODEL
    recall, mrr = summary(evaluate(build_fixture_chunks(), mode="hybrid", embedder=embedder))
    rewrites, _ = rewrite_eval.rewrite_all(OllamaChat(model, temperature=0.0))
    follow = rewrite_eval.measure(
        lambda i, c: (rewrites[i] or rewrite_eval.glued(c), rewrites[i] or c.question), embedder
    )
    glued = rewrite_eval.measure(lambda i, c: (rewrite_eval.glued(c), c.question), embedder)
    answers = answer_eval.measure(answer_eval.prepare_all(embedder), OllamaChat(model), exact_lists=True)
    return [
        Metric("retrieval: hybrid recall@4", recall, True, 0.05, True),
        Metric("retrieval: hybrid MRR", mrr, True, 0.05, True),
        Metric("follow-ups (rewritten, hybrid): recall@4", follow.recall, True, 0.05, True),
        Metric("follow-ups (rewritten, hybrid): MRR", follow.mrr, True, 0.05, True),
        Metric("follow-ups (rewritten): wrong tools", follow.tools_wrong, False, 0, True),
        # The simple method the rewrite replaced, side by side (stage 75 found the rewrite's
        # stage-73 win didn't reproduce: the same prompt at temperature 0 rewrote differently).
        Metric("follow-ups (glued, hybrid): recall@4", glued.recall, True, 0.05, True),
        Metric("follow-ups (glued, hybrid): MRR", glued.mrr, True, 0.05, True),
        Metric("answers: completeness", answers.completeness, True, 0.03, True),
        Metric("answers: same facts every run (of 15)", answers.steady, True, 2, True),
        Metric("answers: forbidden words", answers.forbidden, False, 0, True),
    ]


def load_baseline(path: Path = BASELINE_FILE) -> dict[str, float]:
    if not path.exists():
        return {}
    return {name: entry["value"] for name, entry in json.loads(path.read_text(encoding="utf-8")).items()}


def save_baseline(metrics: list[Metric], path: Path = BASELINE_FILE) -> None:
    """Merge these metrics into the baseline (a quick run keeps the saved full ones)."""
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    saved.update({m.name: {k: v for k, v in asdict(m).items() if k != "name"} for m in metrics})
    path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")


def compare(metrics: list[Metric], baseline: dict[str, float]) -> list[tuple[Metric, float | None, str]]:
    """(metric, baseline value, status): ✅ same or better, ❌ worse beyond tolerance, 🆕 no baseline."""
    rows = []
    for m in metrics:
        before = baseline.get(m.name)
        if before is None:
            status = "🆕"
        else:
            worse_by = (before - m.value) if m.higher_is_better else (m.value - before)
            status = "❌" if worse_by > m.tolerance + 1e-9 else "✅"
        rows.append((m, before, status))
    return rows


def main(argv: list[str]) -> int:
    metrics = quick() + (full() if "--full" in argv else [])
    rows = compare(metrics, load_baseline())
    width = max(len(m.name) for m in metrics)
    print(f"{'measure':<{width}}  {'now':>7}  {'baseline':>8}")
    for m, before, status in rows:
        shown = "-" if before is None else f"{before:.3f}"
        print(f"{m.name:<{width}}  {m.value:>7.3f}  {shown:>8}  {status}")
    regressions = [m.name for m, _, status in rows if status == "❌"]
    if "--save" in argv:
        save_baseline(metrics)
        print(f"\nSaved as the baseline: {BASELINE_FILE.name}")
    if regressions:
        print(f"\n{len(regressions)} regression(s): {', '.join(regressions)}")
        return 1
    print("\nNo regressions.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
