"""Stage 75: the RAG scorecard. The quick measures run with every test run, so a change
that makes retrieval, the faithfulness rules, routing or follow-up search worse fails here."""

from pathlib import Path

from app.rag.scorecard import Metric, compare, load_baseline, quick, save_baseline


def test_no_quick_measure_is_worse_than_its_baseline() -> None:
    rows = compare(quick(), load_baseline())

    missing = [m.name for m, before, _ in rows if before is None]
    worse = [f"{m.name}: {m.value} (baseline {before})" for m, before, status in rows if status == "❌"]
    assert not missing, f"run `python -m app.rag.scorecard --save` to record: {missing}"
    assert not worse, worse


def test_compare_respects_direction_and_tolerance() -> None:
    metrics = [
        Metric("higher, better", 0.9, True, 0),
        Metric("higher, slightly worse but within tolerance", 0.97, True, 0.05),
        Metric("higher, worse", 0.8, True, 0.05),
        Metric("lower, worse", 2, False, 0),
        Metric("lower, better", 0, False, 0),
        Metric("new", 1, True, 0),
    ]
    baseline = {
        "higher, better": 0.8,
        "higher, slightly worse but within tolerance": 1.0,
        "higher, worse": 0.9,
        "lower, worse": 1,
        "lower, better": 1,
    }

    statuses = {m.name: status for m, _, status in compare(metrics, baseline)}

    assert statuses == {
        "higher, better": "✅",
        "higher, slightly worse but within tolerance": "✅",
        "higher, worse": "❌",
        "lower, worse": "❌",
        "lower, better": "✅",
        "new": "🆕",
    }


def test_saving_merges_so_a_quick_run_keeps_the_full_numbers(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    save_baseline([Metric("quick one", 1.0, True, 0), Metric("full one", 0.5, True, 0.05, True)], path)
    save_baseline([Metric("quick one", 0.9, True, 0)], path)

    assert load_baseline(path) == {"quick one": 0.9, "full one": 0.5}
