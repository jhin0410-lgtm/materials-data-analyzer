from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from loaders.characterization_evidence_ladder import (
    CharacterizationEvidenceLadderError,
    LADDER_HANDOFF_CONTRACT,
    LADDER_RECORD_SCHEMA_VERSION,
    LEVELS,
    evaluate_scientific_evidence_ladder,
    replay_scientific_evidence_ladder_assessment,
    validate_bundle_scientific_evidence_ladder,
)
from materials_data_analyzer.characterization_research_gap import (
    CharacterizationResearchGapError,
    build_characterization_research_evidence_gap,
    write_characterization_research_evidence_gap,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "characterization_handoff_bundle.json"
    path.write_text('{"case_id":"case-1"}\n', encoding="utf-8")
    return path


def _binding() -> dict[str, object]:
    return {
        "case_id_bound": True,
        "source_digests_bound": True,
        "subject_modality_bound": True,
        "required_source_roles": [
            "analysis_manifest",
            "comparability_matrix",
            "source_manifest",
        ],
        "bundle_instruments": ["raman"],
    }


def _assessment(
    *,
    case_id: str,
    source_bindings: list[dict[str, str]],
    supported_through: int,
    modality: str = "raman",
) -> dict[str, object]:
    levels: dict[str, dict[str, object]] = {}
    for index, level in enumerate(LEVELS):
        supported = index <= supported_through
        levels[level] = {
            "assessment": "Supported" if supported else "Unsupported",
            "evidence": [f"verified {level}"] if supported else [],
            "limitations": [] if supported else [f"missing {level}"],
        }
    return evaluate_scientific_evidence_ladder(
        {
            "schema_version": "1.0",
            "declaration_id": case_id,
            "subject": {
                "modality": modality,
                "source_material_domain": "reference-material",
                "target_material_domain": "target-material",
                "claim_scope": "method_validation",
            },
            "source_bindings": source_bindings,
            "levels": levels,
            "limitations": ["maturity metadata only"],
        }
    )


def _producer_record(
    assessment: dict[str, object],
    ladder_path: Path,
) -> dict[str, object]:
    declaration = assessment["declaration"]
    assert isinstance(declaration, dict)
    handoff = assessment["handoff"]
    assert isinstance(handoff, dict)
    return {
        "contract": LADDER_HANDOFF_CONTRACT,
        "schema_version": LADDER_RECORD_SCHEMA_VERSION,
        "policy_version": assessment["policy_version"],
        "assessment": {
            "path": ladder_path.name,
            "sha256": _sha(ladder_path),
            "size_bytes": ladder_path.stat().st_size,
        },
        "declaration_id": declaration["declaration_id"],
        "declaration_sha256": assessment["declaration_sha256"],
        "assessment_sha256": assessment["assessment_sha256"],
        "subject": handoff["subject"],
        "source_bindings": handoff["source_bindings"],
        "highest_contiguous_supported_level": assessment[
            "highest_contiguous_supported_level"
        ],
        "first_blocking_level": assessment["first_blocking_level"],
        "readiness": assessment["readiness"],
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "lower_level_evidence_preserved": True,
    }


def _ladder_fixture(
    tmp_path: Path,
    *,
    supported_through: int = 4,
) -> tuple[Path, dict[str, Path], dict[str, object]]:
    evidence_paths: dict[str, Path] = {}
    source = tmp_path / "source_manifest.json"
    analysis = tmp_path / "analysis_manifest.json"
    matrix = tmp_path / "comparability_matrix.csv"
    source.write_text('{"source":"public"}\n', encoding="utf-8")
    analysis.write_text('{"analysis":"verified"}\n', encoding="utf-8")
    pd.DataFrame({"modality": ["raman"]}).to_csv(matrix, index=False)
    evidence_paths.update(
        source_manifest=source,
        analysis_manifest=analysis,
        comparability_matrix=matrix,
    )
    bindings = [
        {"role": role, "sha256": _sha(path)}
        for role, path in sorted(evidence_paths.items())
    ]
    assessment = _assessment(
        case_id="case-1",
        source_bindings=bindings,
        supported_through=supported_through,
    )
    ladder_path = tmp_path / "scientific_evidence_ladder_assessment.json"
    ladder_path.write_text(
        json.dumps(assessment, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ladder_path, evidence_paths, _producer_record(assessment, ladder_path)


def test_independent_replay_matches_deterministic_assessment(tmp_path: Path) -> None:
    ladder_path, _, _ = _ladder_fixture(tmp_path)
    persisted = json.loads(ladder_path.read_text(encoding="utf-8"))

    replayed = replay_scientific_evidence_ladder_assessment(persisted)

    assert replayed["highest_contiguous_supported_level"] == "L4_method_algorithm_validation"
    assert replayed["first_blocking_level"] == "L5_material_domain_validation"
    assert replayed["handoff"]["scientific_status_promoted"] is False
    assert replayed["handoff"]["downstream_use_authorized"] is False


def test_manifest_summary_substitution_is_rejected(tmp_path: Path) -> None:
    _, evidence_paths, record = _ladder_fixture(tmp_path)
    record["first_blocking_level"] = "L6_independent_external_validation"

    with pytest.raises(
        CharacterizationEvidenceLadderError,
        match="manifest summary does not match independent replay",
    ):
        validate_bundle_scientific_evidence_ladder(
            bundle_root=tmp_path,
            record=record,
            case_id="case-1",
            evidence_paths=evidence_paths,
            instruments=["raman"],
        )


def test_source_binding_substitution_is_rejected(tmp_path: Path) -> None:
    ladder_path, evidence_paths, _ = _ladder_fixture(tmp_path)
    persisted = json.loads(ladder_path.read_text(encoding="utf-8"))
    declaration = persisted["declaration"]
    stripped = {
        "schema_version": declaration["schema_version"],
        "declaration_id": declaration["declaration_id"],
        "subject": declaration["subject"],
        "source_bindings": [dict(item) for item in declaration["source_bindings"]],
        "levels": {
            level: {
                "assessment": declaration["levels"][level]["assessment"],
                "evidence": declaration["levels"][level]["evidence"],
                "limitations": declaration["levels"][level]["limitations"],
            }
            for level in LEVELS
        },
        "limitations": declaration["limitations"],
    }
    stripped["source_bindings"][0]["sha256"] = "f" * 64
    changed = evaluate_scientific_evidence_ladder(stripped)
    ladder_path.write_text(
        json.dumps(changed, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    record = _producer_record(changed, ladder_path)

    with pytest.raises(
        CharacterizationEvidenceLadderError,
        match="source binding mismatch",
    ):
        validate_bundle_scientific_evidence_ladder(
            bundle_root=tmp_path,
            record=record,
            case_id="case-1",
            evidence_paths=evidence_paths,
            instruments=["raman"],
        )


def test_backslash_parent_path_is_rejected_portably(tmp_path: Path) -> None:
    _, evidence_paths, record = _ladder_fixture(tmp_path)
    assessment_record = record["assessment"]
    assert isinstance(assessment_record, dict)
    assessment_record["path"] = "..\\scientific_evidence_ladder_assessment.json"

    with pytest.raises(
        CharacterizationEvidenceLadderError,
        match="direct safe sibling",
    ):
        validate_bundle_scientific_evidence_ladder(
            bundle_root=tmp_path,
            record=record,
            case_id="case-1",
            evidence_paths=evidence_paths,
            instruments=["raman"],
        )


def test_first_blocker_maps_to_provenance_bound_target_material_gap(tmp_path: Path) -> None:
    _, evidence_paths, record = _ladder_fixture(tmp_path, supported_through=4)
    ladder, binding = validate_bundle_scientific_evidence_ladder(
        bundle_root=tmp_path,
        record=record,
        case_id="case-1",
        evidence_paths=evidence_paths,
        instruments=["raman"],
    )
    manifest = _manifest(tmp_path)

    first = build_characterization_research_evidence_gap(
        bundle_manifest_path=manifest,
        instruments=["raman"],
        ladder=ladder,
        ladder_binding=binding,
    )
    second = build_characterization_research_evidence_gap(
        bundle_manifest_path=manifest,
        instruments=["raman"],
        ladder=ladder,
        ladder_binding=binding,
    )

    assert first == second
    assert first["bundle_manifest_sha256"] == _sha(manifest)
    assert first["case_id"] == "case-1"
    assert first["ladder_declaration_id"] == "case-1"
    assert first["ladder_binding"] == _binding()
    assert first["first_blocking_level"] == "L5_material_domain_validation"
    assert first["next_requirement"]["requirement_id"] == (
        "characterization_target_material_validation_required"
    )
    assert first["next_requirement"]["planning_action_family"] == (
        "characterization_target_material_validation"
    )
    assert first["next_requirement"]["authorization_required_before_execution"] is True
    assert first["scientific_status_promoted"] is False
    assert first["downstream_use_authorized"] is False
    assert first["action_execution_authorized"] is False
    assert first["semantic_marker"] == "planning_requirement_not_scientific_evidence"


def test_gap_digest_changes_when_bound_manifest_bytes_change(tmp_path: Path) -> None:
    _, evidence_paths, record = _ladder_fixture(tmp_path, supported_through=4)
    ladder, binding = validate_bundle_scientific_evidence_ladder(
        bundle_root=tmp_path,
        record=record,
        case_id="case-1",
        evidence_paths=evidence_paths,
        instruments=["raman"],
    )
    manifest = _manifest(tmp_path)
    first = build_characterization_research_evidence_gap(
        bundle_manifest_path=manifest,
        instruments=["raman"],
        ladder=ladder,
        ladder_binding=binding,
    )
    manifest.write_text('{"case_id":"case-1","revision":2}\n', encoding="utf-8")
    second = build_characterization_research_evidence_gap(
        bundle_manifest_path=manifest,
        instruments=["raman"],
        ladder=ladder,
        ladder_binding=binding,
    )

    assert first["bundle_manifest_sha256"] != second["bundle_manifest_sha256"]
    assert first["characterization_evidence_gap_sha256"] != second[
        "characterization_evidence_gap_sha256"
    ]


def test_independence_blocker_maps_to_external_validation_requirement(tmp_path: Path) -> None:
    _, evidence_paths, record = _ladder_fixture(tmp_path, supported_through=5)
    ladder, binding = validate_bundle_scientific_evidence_ladder(
        bundle_root=tmp_path,
        record=record,
        case_id="case-1",
        evidence_paths=evidence_paths,
        instruments=["raman"],
    )

    gap = build_characterization_research_evidence_gap(
        bundle_manifest_path=_manifest(tmp_path),
        instruments=["raman"],
        ladder=ladder,
        ladder_binding=binding,
    )

    assert gap["first_blocking_level"] == "L6_independent_external_validation"
    assert gap["next_requirement"]["requirement_id"] == (
        "characterization_independent_external_validation_required"
    )
    assert gap["next_requirement"]["planning_action_family"] == (
        "characterization_independent_validation_acquisition"
    )
    assert gap["action_execution_authorized"] is False


def test_legacy_bundle_requires_maturity_assessment_instead_of_inferred_level(
    tmp_path: Path,
) -> None:
    gap = build_characterization_research_evidence_gap(
        bundle_manifest_path=_manifest(tmp_path),
        instruments=["xrd"],
        ladder=None,
        ladder_binding=None,
    )

    assert gap["ladder_present"] is False
    assert gap["first_blocking_level"] is None
    assert gap["next_requirement"]["requirement_id"] == (
        "characterization_evidence_maturity_assessment_required"
    )
    assert gap["next_requirement"]["authorization_required_before_execution"] is True
    assert gap["scientific_status_promoted"] is False
    assert gap["action_execution_authorized"] is False


def test_complete_ladder_has_no_next_characterization_requirement_but_authorizes_nothing(tmp_path: Path) -> None:
    _, evidence_paths, record = _ladder_fixture(tmp_path, supported_through=8)
    ladder, binding = validate_bundle_scientific_evidence_ladder(
        bundle_root=tmp_path,
        record=record,
        case_id="case-1",
        evidence_paths=evidence_paths,
        instruments=["raman"],
    )

    gap = build_characterization_research_evidence_gap(
        bundle_manifest_path=_manifest(tmp_path),
        instruments=["raman"],
        ladder=ladder,
        ladder_binding=binding,
    )

    assert gap["first_blocking_level"] is None
    assert gap["next_requirement"] is None
    assert gap["scientific_status_promoted"] is False
    assert gap["downstream_use_authorized"] is False
    assert gap["action_execution_authorized"] is False


def test_present_ladder_requires_verified_binding_proof(tmp_path: Path) -> None:
    _, evidence_paths, record = _ladder_fixture(tmp_path)
    ladder, _ = validate_bundle_scientific_evidence_ladder(
        bundle_root=tmp_path,
        record=record,
        case_id="case-1",
        evidence_paths=evidence_paths,
        instruments=["raman"],
    )

    with pytest.raises(CharacterizationResearchGapError, match="ladder_binding is required"):
        build_characterization_research_evidence_gap(
            bundle_manifest_path=_manifest(tmp_path),
            instruments=["raman"],
            ladder=ladder,
            ladder_binding=None,
        )


def test_gap_writer_rejects_tamper_and_overwrite(tmp_path: Path) -> None:
    gap = build_characterization_research_evidence_gap(
        bundle_manifest_path=_manifest(tmp_path),
        instruments=["xrd"],
        ladder=None,
        ladder_binding=None,
    )
    output = tmp_path / "outputs"
    path = write_characterization_research_evidence_gap(output, gap)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted == gap

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_characterization_research_evidence_gap(output, gap)

    tampered = dict(gap)
    tampered["action_execution_authorized"] = True
    with pytest.raises(CharacterizationResearchGapError, match="must not authorize action execution"):
        write_characterization_research_evidence_gap(tmp_path / "tampered-output", tampered)

    wrong_hash = dict(gap)
    wrong_hash["first_blocking_level"] = "L1_raw_representation_identity"
    with pytest.raises(CharacterizationResearchGapError, match="canonical SHA-256 mismatch"):
        write_characterization_research_evidence_gap(tmp_path / "wrong-hash-output", wrong_hash)
