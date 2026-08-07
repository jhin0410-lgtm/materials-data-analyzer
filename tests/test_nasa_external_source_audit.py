from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop.nasa_external_source_audit import (
    NasaExternalSourceAuditError,
    audit_external_source_candidates,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_external_source_candidates.v1.json"


def _requirement() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "blocker": "protocol_groups_too_small",
        "current_evidence_level": "Unsupported",
        "status": "Diagnostic",
        "source_cohort_design": {
            "unrelated_source_cohort_counts_may_not_be_pooled": True,
            "temperature_and_source_cohort_must_not_be_perfectly_confounded": True,
            "new_source_cohort_minimum_exact_groups": 2,
            "new_source_cohort_minimum_evaluated_batteries_per_exact_group": 5,
        },
    }


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _registry_payload() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_registered_kit_candidate_is_blocked_until_semantics_are_verified(
    tmp_path: Path,
) -> None:
    requirement_path = _write_json(tmp_path / "requirement.json", _requirement())

    report = audit_external_source_candidates(requirement_path, REGISTRY)

    assert report["input_evidence_level"] == "Unsupported"
    assert report["output_evidence_level"] == "Unsupported"
    assert report["scientific_status"] == "Diagnostic"
    assert report["candidate_count"] == 1

    candidate = report["candidates"][0]
    assert candidate["candidate_id"] == "kit-luh-blank-2024-result-v2"
    assert candidate["disposition"] == "semantics_audit_required"
    assert candidate["eligible_for_predeclared_diagnostic"] is False
    assert candidate["eligible_for_external_validation_claim"] is False
    assert candidate["structural_blockers"] == []
    assert candidate["minimum_batteries_per_temperature_lower_bound"] == 36
    assert candidate["exact_temperatures_c"] == [0.0, 10.0, 25.0, 40.0]
    assert candidate["semantic_blockers"] == [
        "protocol_temperature_semantics_unresolved",
        "exact_horizon_semantics_unresolved",
        "target_reference_semantics_unresolved",
    ]


def test_candidate_becomes_diagnostic_eligible_only_after_semantic_matches(
    tmp_path: Path,
) -> None:
    requirement_path = _write_json(tmp_path / "requirement.json", _requirement())
    registry = copy.deepcopy(_registry_payload())
    candidate = registry["candidates"][0]
    candidate["metadata_assertions"]["protocol_temperature_semantics"] = (
        "confirmed_match"
    )
    candidate["metadata_assertions"]["exact_horizon_semantics"] = "confirmed_match"
    candidate["metadata_assertions"]["target_reference_semantics"] = "confirmed_match"
    registry_path = _write_json(tmp_path / "registry.json", registry)

    report = audit_external_source_candidates(requirement_path, registry_path)
    audited = report["candidates"][0]

    assert audited["disposition"] == "predeclared_diagnostic_eligible"
    assert audited["eligible_for_predeclared_diagnostic"] is True
    assert audited["eligible_for_external_validation_claim"] is False
    assert report["output_evidence_level"] == "Unsupported"


def test_source_temperature_confounding_fails_structural_audit(tmp_path: Path) -> None:
    requirement_path = _write_json(tmp_path / "requirement.json", _requirement())
    registry = copy.deepcopy(_registry_payload())
    candidate = registry["candidates"][0]
    candidate["cyclic_design"]["temperature_crossed_with_other_factors"] = False
    registry_path = _write_json(tmp_path / "registry.json", registry)

    report = audit_external_source_candidates(requirement_path, registry_path)
    audited = report["candidates"][0]

    assert audited["disposition"] == "structurally_ineligible"
    assert "source_temperature_crossing_confirmed" in audited["structural_blockers"]
    assert audited["eligible_for_predeclared_diagnostic"] is False


def test_requirement_must_prohibit_cross_source_count_pooling(tmp_path: Path) -> None:
    requirement = _requirement()
    source_design = requirement["source_cohort_design"]
    source_design["unrelated_source_cohort_counts_may_not_be_pooled"] = False
    requirement_path = _write_json(tmp_path / "requirement.json", requirement)

    with pytest.raises(
        NasaExternalSourceAuditError,
        match="prohibit unrelated-source count pooling",
    ):
        audit_external_source_candidates(requirement_path, REGISTRY)
