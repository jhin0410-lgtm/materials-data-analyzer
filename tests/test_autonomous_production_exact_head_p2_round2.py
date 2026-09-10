from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round2 as round2,
)


def _canonical_sha(value: dict[str, object], self_field: str) -> str:
    unsigned = dict(value)
    unsigned.pop(self_field, None)
    return hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _hashed(value: dict[str, object], field: str) -> dict[str, object]:
    result = dict(value)
    result[field] = _canonical_sha(result, field)
    return result


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_cycle1_reviewed_binding_requires_persisted_derivatives(tmp_path: Path) -> None:
    cycles = [
        {
            "cycle_index": 1,
            "reviewed_tensile_manifest_sha256": "bound-review-manifest",
        },
        {"cycle_index": 2},
        {"cycle_index": 3},
    ]
    with pytest.raises(
        round2.AutonomousProductionExactHeadRound2Error,
        match="persisted derivatives are missing",
    ):
        round2._verify_bound_reviewed_tensile_presence(tmp_path, cycles)


def test_genuinely_prederivation_transport_can_omit_reviewed_derivatives(
    tmp_path: Path,
) -> None:
    cycles = [{"cycle_index": 1}, {"cycle_index": 2}, {"cycle_index": 3}]
    round2._verify_bound_reviewed_tensile_presence(tmp_path, cycles)


def test_posttransport_outcome_cannot_omit_cycle1_reviewed_binding(
    tmp_path: Path,
) -> None:
    cycles = [{"cycle_index": index} for index in range(1, 5)]
    with pytest.raises(
        round2.AutonomousProductionExactHeadRound2Error,
        match="missing the cycle-1 reviewed tensile binding",
    ):
        round2._verify_bound_reviewed_tensile_presence(tmp_path, cycles)


def test_historical_zenodo_archive_path_is_resolved_from_replay_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "relocated-run"
    root.mkdir()
    historical = (
        "/home/runner/work/materials-data-analyzer/materials-data-analyzer/"
        "outputs/autonomous-in625-production/Dataset.zip"
    )
    _write_json(
        root / "network-acquisition-receipt.json",
        {"archive": {"path": historical}},
    )
    observed: dict[str, Path] = {}

    def fake_original(
        *, root: Path, cycle1: object
    ) -> tuple[dict[str, object], dict[str, object]]:
        observed["path"] = round2._lifecycle.Path(historical).expanduser().resolve(
            strict=False
        )
        return {}, {}

    monkeypatch.setattr(round2, "_ORIGINAL_ZENODO_POST_CLEANUP", fake_original)
    round2._relocation_safe_zenodo_post_cleanup(root=root, cycle1={})
    assert observed["path"] == (root / "Dataset.zip").resolve(strict=False)


def test_historical_zenodo_archive_path_rejects_traversal(
    tmp_path: Path,
) -> None:
    root = tmp_path / "relocated-run"
    root.mkdir()
    _write_json(
        root / "network-acquisition-receipt.json",
        {"archive": {"path": "../../autonomous-in625-production/Dataset.zip"}},
    )
    with pytest.raises(
        round2.AutonomousProductionExactHeadRound2Error,
        match="traversal",
    ):
        round2._relocation_safe_zenodo_post_cleanup(root=root, cycle1={})


def test_predecessor_rediagnosis_denies_automatic_execution(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "quality-aware-rediagnosis.json",
        {"next_action": {"automatic_execution_authorized": True}},
    )
    with pytest.raises(
        round2.AutonomousProductionExactHeadRound2Error,
        match="granted automatic execution",
    ):
        round2._verify_predecessor_execution_boundary(tmp_path)


def test_post_acquisition_evidence_lane_contract_is_exact(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "nist-post-acquisition-rediagnosis.json",
        {
            "next_action": {
                "eligible_evidence_lanes": list(round2._EXPECTED_EVIDENCE_LANES),
                "paper_evidence_role": round2._EXPECTED_PAPER_EVIDENCE_ROLE,
            }
        },
    )
    round2._verify_post_acquisition_lane_contract(tmp_path)

    value = json.loads(
        (tmp_path / "nist-post-acquisition-rediagnosis.json").read_text(
            encoding="utf-8"
        )
    )
    value["next_action"]["paper_evidence_role"] = "row-level authority"
    _write_json(tmp_path / "nist-post-acquisition-rediagnosis.json", value)
    with pytest.raises(
        round2.AutonomousProductionExactHeadRound2Error,
        match="paper evidence role drifted",
    ):
        round2._verify_post_acquisition_lane_contract(tmp_path)


def _cycle4_fixture(tmp_path: Path) -> list[dict[str, object]]:
    mapping = _hashed(
        {
            "scientific_boundary": {
                "empirical_model_validation_established": False,
                "hypothesis_truth_established": False,
                "numerical_cross_source_comparison_performed": False,
                "positive_scientific_closeout": False,
                "scientific_status_changed": False,
                "source_acquisition_success_interpreted_as_scientific_support": False,
            }
        },
        "report_sha256_without_self_field",
    )
    sources = _hashed(
        {
            "source_count": 8,
            "paper_claims_promoted_to_row_level_authority": False,
            "scientific_status_changed": False,
            "sources": [
                {
                    "source_id": f"source-{index}",
                    "row_level_measurement_authority": False,
                    "scientific_status_changed": False,
                }
                for index in range(1, 9)
            ],
        },
        "report_sha256_without_self_field",
    )
    _write_json(tmp_path / "geometry-condition-mapping-assessment.json", mapping)
    _write_json(tmp_path / "multisource-source-acquisition.json", sources)
    return [
        {"cycle_index": 1},
        {"cycle_index": 2},
        {"cycle_index": 3},
        {
            "cycle_index": 4,
            "mapping_assessment_sha256": mapping[
                "report_sha256_without_self_field"
            ],
            "source_acquisition_report_sha256": sources[
                "report_sha256_without_self_field"
            ],
        },
    ]


def test_cycle4_mapping_self_hash_and_binding_are_authenticated(tmp_path: Path) -> None:
    cycles = _cycle4_fixture(tmp_path)
    mapping_path = tmp_path / "geometry-condition-mapping-assessment.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping["scientific_boundary"]["positive_scientific_closeout"] = True
    mapping["report_sha256_without_self_field"] = _canonical_sha(
        mapping, "report_sha256_without_self_field"
    )
    _write_json(mapping_path, mapping)
    cycles[3]["mapping_assessment_sha256"] = mapping[
        "report_sha256_without_self_field"
    ]

    with pytest.raises(
        round2.AutonomousProductionExactHeadRound2Error,
        match="geometry mapping scientific boundary promoted authority",
    ):
        round2._verify_cycle4_artifacts(tmp_path, cycles)


def test_cycle4_multisource_rejects_per_source_row_authority(tmp_path: Path) -> None:
    cycles = _cycle4_fixture(tmp_path)
    sources_path = tmp_path / "multisource-source-acquisition.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    sources["sources"][3]["row_level_measurement_authority"] = True
    sources["report_sha256_without_self_field"] = _canonical_sha(
        sources, "report_sha256_without_self_field"
    )
    _write_json(sources_path, sources)
    cycles[3]["source_acquisition_report_sha256"] = sources[
        "report_sha256_without_self_field"
    ]

    with pytest.raises(
        round2.AutonomousProductionExactHeadRound2Error,
        match="gained row-level measurement authority",
    ):
        round2._verify_cycle4_artifacts(tmp_path, cycles)


def test_live_workflow_tracks_every_round2_replay_dependency() -> None:
    text = Path(".github/workflows/autonomous-production-live.yml").read_text(
        encoding="utf-8"
    )
    for path in (
        "src/materials_data_analyzer/research_loop/in625_tensile_reviewed_intake_v2.py",
        "src/materials_data_analyzer/research_loop/acquisition_record_binding.py",
        "src/materials_data_analyzer/research_loop/nist_pdr_acquisition.py",
    ):
        assert text.count(f'- "{path}"') == 2
    assert text.count(
        'tests/test_autonomous_production_exact_head_p2_round2.py'
    ) >= 3
