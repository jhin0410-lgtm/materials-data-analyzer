from __future__ import annotations

from pathlib import Path

from materials_data_analyzer.research_loop import (
    autonomous_production_fresh_review_round12 as round12,
)


def test_round12_is_wired_and_uploaded_by_the_live_gate() -> None:
    module_root = Path(round12.__file__).resolve().parent
    verifier = (module_root / "autonomous_production_live_verifier.py").read_text(
        encoding="utf-8"
    )
    workflow = (
        module_root.parents[2] / ".github" / "workflows" / "autonomous-production-live.yml"
    ).read_text(encoding="utf-8")

    assert "verify_fresh_review_round12_boundaries(root)" in verifier
    assert "tests/test_autonomous_production_fresh_review_round12.py" in workflow
    assert "standing-network-policy-qualification.json" in workflow
