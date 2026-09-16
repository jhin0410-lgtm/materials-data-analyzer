from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_cycle6_reacquisition_binding as binding,
)
from materials_data_analyzer.research_loop import calibration_protocol_bridge_capability as bridge


def _rehash(value: dict[str, Any], field: str = "report_sha256_without_self_field") -> None:
    value.pop(field, None)
    value[field] = bridge._canonical_sha(value)


def _evidence(prefix: str) -> dict[str, Any]:
    required = sorted(bridge._REQUIRED_CLAIMS)
    sources: list[dict[str, Any]] = []
    for index in range(8):
        claims = (
            [{"claim_id": claim_id, "matched": True} for claim_id in required]
            if index == 0
            else []
        )
        sources.append(
            {
                "source_id": f"source-{index}",
                "source_sha256": f"{index + 1:064x}",
                "claims": claims,
                "source_bytes_b64": f"{prefix}-{index}",
                "source_bytes_persisted": True,
            }
        )
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "acquisition_status": "exact_multisource_condition_evidence_acquired",
        "source_count": 8,
        "network_requests_performed": 8,
        "all_claim_anchors_matched": True,
        "paper_claims_promoted_to_row_level_authority": False,
        "source_bytes_persisted": True,
        "retained_source_bytes_count": 8,
        "sources": sources,
    }
    _rehash(report)
    return report


def _artifacts() -> dict[str, dict[str, Any]]:
    prior = _evidence("prior")
    reacquired = _evidence("cycle6")
    mapping: dict[str, Any] = {
        "gate_decision": {
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
        }
    }
    _rehash(mapping)
    bridge_result = bridge.build_bridge_frontier_report(
        mapping_assessment=mapping,
        reacquired_evidence=reacquired,
        prior_evidence=prior,
    )
    cycles = [{"cycle_index": index} for index in range(1, 6)]
    cycles.append(
        {
            "cycle_index": 6,
            "network_requests_performed": 8,
            "new_verified_information": False,
            "output_next_action_class": bridge.NEXT_ACTION_CLASS,
            "bridge_established": False,
            "directly_comparable_mds2_rows": 0,
            "issue_76_exact_target_cells_satisfied": 0,
        }
    )
    manifest = {
        "cycles": cycles,
        "bridge_capability_execution_sha256": bridge_result[
            "report_sha256_without_self_field"
        ],
        "generated_next_action_class": bridge.NEXT_ACTION_CLASS,
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
    }
    return {
        "autonomous-production-manifest.json": manifest,
        "calibration-protocol-bridge-capability-result.json": bridge_result,
        "multisource-source-acquisition.json": prior,
        "geometry-condition-mapping-assessment.json": mapping,
    }


def _install_loads(
    monkeypatch: pytest.MonkeyPatch,
    artifacts: dict[str, dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        binding._merge_gate,
        "_load",
        lambda _root, name: copy.deepcopy(artifacts[name]),
    )


def test_cycle6_reacquisition_rebuild_accepts_exact_bound_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _artifacts()
    _install_loads(monkeypatch, artifacts)
    seen: list[str] = []
    monkeypatch.setattr(
        binding,
        "verify_multisource_acquisition_against_reviewed_witness",
        lambda report: seen.append(str(report["sources"][0]["source_bytes_b64"])),
    )

    binding.verify_cycle6_reacquisition_boundaries(tmp_path)
    assert seen == ["cycle6-0", "prior-0"]


def test_cycle6_missing_reacquisition_evidence_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _artifacts()
    artifacts["calibration-protocol-bridge-capability-result.json"].pop(
        "reacquired_source_evidence"
    )
    _rehash(artifacts["calibration-protocol-bridge-capability-result.json"])
    artifacts["autonomous-production-manifest.json"]["bridge_capability_execution_sha256"] = (
        artifacts["calibration-protocol-bridge-capability-result.json"][
            "report_sha256_without_self_field"
        ]
    )
    _install_loads(monkeypatch, artifacts)

    with pytest.raises(
        binding.AutonomousProductionCycle6ReacquisitionBindingError,
        match="retained reacquisition evidence",
    ):
        binding.verify_cycle6_reacquisition_boundaries(tmp_path)


def test_cycle6_self_consistent_retained_body_mutation_reaches_independent_witness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _artifacts()
    result = artifacts["calibration-protocol-bridge-capability-result.json"]
    reacquired = result["reacquired_source_evidence"]
    assert isinstance(reacquired, dict)
    sources = reacquired["sources"]
    assert isinstance(sources, list) and isinstance(sources[0], dict)
    sources[0]["source_bytes_b64"] = "attacker-rehashed-bytes"
    _rehash(reacquired)
    result["reacquired_source_report_sha256"] = reacquired[
        "report_sha256_without_self_field"
    ]
    _rehash(result)
    artifacts["autonomous-production-manifest.json"]["bridge_capability_execution_sha256"] = result[
        "report_sha256_without_self_field"
    ]
    _install_loads(monkeypatch, artifacts)

    def reviewed_witness(report: dict[str, Any]) -> None:
        raw_sources = report["sources"]
        assert isinstance(raw_sources, list) and isinstance(raw_sources[0], dict)
        if raw_sources[0].get("source_bytes_b64") == "attacker-rehashed-bytes":
            raise binding.AutonomousProductionMultisourceReviewedWitnessError(
                "retained source bytes do not match reviewed authority"
            )

    monkeypatch.setattr(
        binding,
        "verify_multisource_acquisition_against_reviewed_witness",
        reviewed_witness,
    )
    with pytest.raises(
        binding.AutonomousProductionCycle6ReacquisitionBindingError,
        match="failed independent retained-source replay",
    ):
        binding.verify_cycle6_reacquisition_boundaries(tmp_path)


def test_cycle6_fabricated_source_version_changes_rejected_after_rehash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _artifacts()
    result = artifacts["calibration-protocol-bridge-capability-result.json"]
    result["source_version_changes"] = ["forged-source"]
    result["new_source_version_information"] = True
    _rehash(result)
    manifest = artifacts["autonomous-production-manifest.json"]
    manifest["bridge_capability_execution_sha256"] = result[
        "report_sha256_without_self_field"
    ]
    cycle6 = manifest["cycles"][5]
    assert isinstance(cycle6, dict)
    cycle6["new_verified_information"] = True
    _install_loads(monkeypatch, artifacts)
    monkeypatch.setattr(
        binding,
        "verify_multisource_acquisition_against_reviewed_witness",
        lambda _report: None,
    )

    with pytest.raises(
        binding.AutonomousProductionCycle6ReacquisitionBindingError,
        match="conclusions drifted",
    ):
        binding.verify_cycle6_reacquisition_boundaries(tmp_path)


def test_cycle6_manifest_bridge_binding_drift_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _artifacts()
    artifacts["autonomous-production-manifest.json"]["bridge_capability_execution_sha256"] = (
        "f" * 64
    )
    _install_loads(monkeypatch, artifacts)
    monkeypatch.setattr(
        binding,
        "verify_multisource_acquisition_against_reviewed_witness",
        lambda _report: None,
    )

    with pytest.raises(
        binding.AutonomousProductionCycle6ReacquisitionBindingError,
        match="manifest bridge execution digest",
    ):
        binding.verify_cycle6_reacquisition_boundaries(tmp_path)
