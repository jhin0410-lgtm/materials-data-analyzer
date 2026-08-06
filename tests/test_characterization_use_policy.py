from __future__ import annotations

import json

import pytest

from materials_data_analyzer.characterization_import_cli import main
from materials_data_analyzer.characterization_use_policy import (
    CharacterizationUsePolicyError,
    evaluate_characterization_use,
    require_characterization_use,
)


def _policy(**overrides: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "schema_version": "1.0",
        "maximum_allowed_use": "predictive",
        "feature_stage": "derived",
        "evidence_level": "Supported",
        "review_status": "reviewed",
        "independence_group_field": "batch_id",
        "measurement_timing": "pre_outcome",
        "causal_design_validated": False,
        "operational_validation_validated": False,
        "limitations": ["Validated only inside the declared applicability domain."],
    }
    policy.update(overrides)
    return policy


def _write_manifest(tmp_path, *, policy: object = "absent"):
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "scientific_closeout": {"evidence_level": "Supported"},
        "sample_context": {"columns": ["sample_id", "batch_id"]},
    }
    if policy != "absent":
        payload["downstream_use_policy"] = policy
    path = tmp_path / "characterization_handoff_bundle.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_legacy_bundle_defaults_to_descriptive_only(tmp_path) -> None:
    manifest = _write_manifest(tmp_path)

    descriptive = evaluate_characterization_use(
        manifest, requested_use="descriptive"
    )
    predictive = evaluate_characterization_use(
        manifest,
        requested_use="predictive",
        split_group_field="batch_id",
    )

    assert descriptive.allowed is True
    assert descriptive.policy_source == "legacy_default"
    assert predictive.allowed is False
    assert "exceeds maximum_allowed_use" in predictive.reasons[0]


def test_predictive_use_requires_matching_independence_group(tmp_path) -> None:
    manifest = _write_manifest(tmp_path, policy=_policy())

    missing = evaluate_characterization_use(manifest, requested_use="predictive")
    mismatch = evaluate_characterization_use(
        manifest,
        requested_use="predictive",
        split_group_field="sample_id",
    )
    allowed = require_characterization_use(
        manifest,
        requested_use="predictive",
        split_group_field="batch_id",
    )

    assert missing.allowed is False
    assert "requires --split-group-field" in missing.reasons
    assert mismatch.allowed is False
    assert allowed.allowed is True
    assert allowed.independence_group_field == "batch_id"


def test_declared_group_must_exist_in_sample_context(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        policy=_policy(independence_group_field="specimen_id"),
    )
    decision = evaluate_characterization_use(
        manifest,
        requested_use="predictive",
        split_group_field="specimen_id",
    )
    assert decision.allowed is False
    assert any("absent from sample_context" in reason for reason in decision.reasons)


def test_post_outcome_predictive_policy_is_rejected(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        policy=_policy(measurement_timing="post_outcome"),
    )
    with pytest.raises(CharacterizationUsePolicyError, match="pre_outcome"):
        evaluate_characterization_use(
            manifest,
            requested_use="predictive",
            split_group_field="batch_id",
        )


def test_causal_and_engineering_policies_fail_closed(tmp_path) -> None:
    causal = _write_manifest(
        tmp_path,
        policy=_policy(maximum_allowed_use="causal"),
    )
    with pytest.raises(CharacterizationUsePolicyError, match="causal_design"):
        evaluate_characterization_use(causal, requested_use="causal")


def test_policy_evidence_must_match_closeout(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        policy=_policy(evidence_level="Diagnostic", maximum_allowed_use="descriptive"),
    )
    with pytest.raises(CharacterizationUsePolicyError, match="must match"):
        evaluate_characterization_use(manifest)


def test_cli_blocks_predictive_legacy_use_before_output_creation(tmp_path) -> None:
    manifest = _write_manifest(tmp_path)
    output = tmp_path / "blocked-output"

    result = main(
        [
            "--bundle-manifest",
            str(manifest),
            "--output",
            str(output),
            "--requested-use",
            "predictive",
            "--split-group-field",
            "batch_id",
        ]
    )

    assert result == 1
    assert not output.exists()
