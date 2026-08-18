from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTIER = ROOT / "configs" / "research" / "post_mvp_real_data_generalization_frontier.v1.json"


def _candidate() -> dict:
    payload = json.loads(FRONTIER.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["frontier_id"] == "post-mvp-real-data-generalization-frontier-v1"
    candidates = payload["candidates"]
    assert len(candidates) == 1
    return candidates[0]


def test_nist_amb2025_03_frontier_is_checksum_bound_and_physical() -> None:
    candidate = _candidate()
    assert candidate["candidate_id"] == "nist-amb2025-03-ti64-fatigue"
    assert candidate["identifier"] == "10.18434/mds2-3734"
    assert candidate["physical_origin"] == "physical"
    assert candidate["automatic_acquisition_plan"]["adapter"] == "nist_pdr"
    assert candidate["automatic_acquisition_plan"]["product_id"] == "mds2-3734"
    assert candidate["automatic_acquisition_plan"]["filepaths"] == candidate["authoritative_files"]
    assert candidate["scientific_status_changed"] is False


def test_fatigue_frontier_preserves_one_build_and_censoring_boundaries() -> None:
    candidate = _candidate()
    design = candidate["source_design"]
    assert design["build_count_declared"] == 1
    assert design["post_build_conditions"] == ["800HIP", "800VAC"]
    assert "independent build replication" in design["independence_warning"]

    requirements = "\n".join(candidate["scientific_intake_requirements"]).lower()
    assert "runout" in requirements
    assert "censor" in requirements
    assert "one-build" in requirements
    assert "do not fit" in requirements
    assert "scientific status" in requirements


def test_first_acquisition_does_not_claim_withheld_vacuum_fatigue_results() -> None:
    candidate = _candidate()
    paths = candidate["authoritative_files"]
    assert "calibration_data/fatigue_testing/fatigue_800hip.xlsx" in paths
    assert not any("fatigue_800vac" in path.lower() for path in paths)
