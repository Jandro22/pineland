from pathlib import Path


def test_report_writer_binds_report_to_source_run_manifest():
    path = (Path(__file__).resolve().parents[1] / "studies" / "nepal_2001_2006" /
            "scripts" / "write_provenanced_rescore_report.py")
    text = path.read_text(encoding="utf-8")
    assert "source_run_manifest_sha256" in text
    assert '"artifacts"' in text
    assert '"parameter_fit": False' in text
    assert '"holdout_refit": False' in text
