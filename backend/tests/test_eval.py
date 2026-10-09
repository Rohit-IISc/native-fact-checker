"""Eval runner logic (no model calls): rating mapping, URL matching, metrics, drift rule, gold order."""
from eval import datasets, runner
from eval.runner import VerdictRow


def test_ratings_map_onto_our_labels():
    cases = {
        "False": "FALSE", "Fake": "FALSE", "झूठ": "FALSE", "Hoaks": "FALSE", "Not True": "FALSE",
        "Misleading": "MISLEADING", "Out of context": "MISLEADING", "Old video": "MISLEADING",
        "Partly False": "MISLEADING", "भ्रामक": "MISLEADING", "Satire": "MISLEADING",
        "Scam": "SCAM", "Penipuan": "SCAM", "True": "TRUE", "Correct": "TRUE", "सच": "TRUE",
        "Sesat - Benar bahwa anggaran meningkat": "MISLEADING", "sebagian benar": None,
        "Mostly True": None, "Unproven": None, "Explainer": None, "": None, None: None,
    }
    for rating, want in cases.items():
        assert datasets.label_for_rating(rating) == want, rating


def test_url_match_ignores_scheme_www_amp_query_and_slash():
    a = datasets.norm_url("https://www.boomlive.in/fact-check/x-123/?utm_source=wa")
    assert a == datasets.norm_url("http://boomlive.in/fact-check/x-123") == "boomlive.in/fact-check/x-123"
    assert datasets.norm_url("https://amp.example.com/a/amp") == "example.com/a"


def row(expected, got, latency=50_000, cost=0.1, outcome="AGREED", st="gold"):
    return VerdictRow("i", st, "hi", expected, got, latency, cost, outcome)


def test_strict_and_direction_agreement():
    m = runner.verdict_metrics([row("FALSE", "FALSE"), row("FALSE", "MISLEADING"),
                                row("TRUE", "NOT_ENOUGH_EVIDENCE"), row("TRUE", "FALSE")])
    assert m["verdict_agreement"] == 25.0      # only the exact FALSE
    assert m["direction_agreement"] == 50.0    # FALSE vs MISLEADING both say "do not believe this"
    assert m["abstain_rate"] == 25.0
    assert m["accuracy_when_answered"] == 33.3


def test_errors_count_against_agreement_but_not_latency():
    m = runner.verdict_metrics([row("FALSE", "FALSE", latency=40_000), row("FALSE", "ERROR", latency=0)])
    assert m["verdict_agreement"] == 50.0 and m["errors"] == 1 and m["p50_latency_ms"] == 40_000


def test_drift_rule():
    base = {"recall_at_5": {"overall": 60.0}, "verdict_agreement": 70.0, "p95_latency_ms": 80_000}
    assert runner.drift({"recall_at_5": {"overall": 56.0}, "verdict_agreement": 66.0,
                         "p95_latency_ms": 100_000}, base) == []
    reasons = runner.drift({"recall_at_5": {"overall": 50.0}, "verdict_agreement": 60.0,
                            "p95_latency_ms": 110_000}, base)
    assert len(reasons) == 3
    assert runner.drift({"verdict_agreement": 10.0}, None) == []  # first run: nothing to compare


def test_gold_order_is_stable_and_covers_languages():
    items = [{"id": f"{lang}{n}", "language": lang} for lang in ("en", "hi", "ta") for n in range(3)]
    mixed = runner.stable_mix(items)
    assert [i["id"] for i in mixed[:3]] == ["hi0", "ta0", "en0"]
    assert runner.stable_mix(items) == mixed


def test_balanced_spreads_labels():
    import random

    items = [{"id": str(n), "language": "hi", "label": lab} for n, lab in
             enumerate(["FALSE"] * 8 + ["TRUE", "MISLEADING"])]
    pick = datasets.balanced(items, 4, random.Random(1), by_label=True)
    assert {"TRUE", "MISLEADING", "FALSE"} <= {p["label"] for p in pick}
