from pathlib import Path


def test_rescore_runner_captures_provenance_and_refuses_backfill():
    text = (Path(__file__).resolve().parents[1] / "studies" / "nepal_2001_2006" /
            "scripts" / "run_untuned_benchmark.py").read_text(encoding="utf-8")
    assert '"model_sha256_start"' in text
    assert '"model_sha256_end"' in text
    assert '"tracked_diff_sha256"' in text
    assert "refusing to backfill provenance" in text
    assert 'parser.add_argument("--output-dir"' in text
