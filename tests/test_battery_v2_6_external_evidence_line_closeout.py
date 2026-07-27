from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.platform_core import battery_v2_6_external_evidence_line_closeout as mod


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_config_manifest_and_contract_are_checksum_bound():
    config = mod.load_config()
    manifest = _load(mod.DEFAULT_MANIFEST_PATH)
    contract = _load(mod.DEFAULT_CONTRACT_PATH)
    assert config["execution_mode"] == "verify"
    assert config["dry_run"] is False
    assert mod.canonical_checksum(manifest) == mod.EXPECTED_MANIFEST_CHECKSUM
    assert mod.canonical_checksum(contract) == mod.EXPECTED_CONTRACT_CHECKSUM
    mod.validate_manifest(manifest)
    mod.validate_contract(contract)


def test_all_thirteen_tracked_artifacts_verify_and_closeout_is_deterministic():
    config = mod.load_config()
    first = mod.execute(config)
    second = mod.execute(config)
    assert first == second
    assert first["verified_stage_count"] == 13
    assert first["stage_checksum_failures"] == []
    assert first["deterministic_result_checksum"] == mod.EXPECTED_RESULT_CHECKSUM
    assert first["software_validation"]["status"] == "supported"
    assert first["scientific_closeout"]["status"] == "inconclusive"
    assert first["decision"]["predictive_validation_readiness"] == "not_ready"
    assert first["next_action"]["automatic_next_feature_stage_authorized"] is False


def test_stage_versions_and_paths_are_exactly_ordered():
    manifest = _load(mod.DEFAULT_MANIFEST_PATH)
    assert [item["version"] for item in manifest["stages"]] == [f"2.6.{number}" for number in range(1, 14)]
    assert len({item["artifact_path"] for item in manifest["stages"]}) == 13
    assert len({item["expected_checksum"] for item in manifest["stages"]}) == 13


def test_tampered_upstream_artifact_fails_closed(tmp_path: Path):
    stage = copy.deepcopy(_load(mod.DEFAULT_MANIFEST_PATH)["stages"][0])
    target = tmp_path / stage["artifact_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _load(stage["artifact_path"])
    payload["software_validation"] = "tampered"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical checksum mismatch"):
        mod._verify_stage(stage, repo_root=tmp_path)


def test_manifest_contract_and_result_reject_scientific_promotion():
    manifest = _load(mod.DEFAULT_MANIFEST_PATH)
    promoted_manifest = copy.deepcopy(manifest)
    promoted_manifest["claim_policy"]["software_test_success_is_scientific_validation"] = True
    with pytest.raises(ValueError):
        mod.validate_manifest(promoted_manifest)

    contract = _load(mod.DEFAULT_CONTRACT_PATH)
    promoted_contract = copy.deepcopy(contract)
    promoted_contract["required_final_decisions"]["predictive_validation_readiness"] = "ready"
    with pytest.raises(ValueError):
        mod.validate_contract(promoted_contract)

    result = mod.execute(mod.load_config())
    for key, promoted_value in (
        ("ridge_generalization", "supported"),
        ("cross_cohort_comparability", "established"),
        ("external_cohort_admission", "admitted"),
        ("predictive_validation_readiness", "ready"),
        ("engineering_decision_readiness", "ready"),
    ):
        promoted = copy.deepcopy(result)
        promoted["decision"][key] = promoted_value
        promoted["deterministic_result_checksum"] = mod.canonical_checksum(promoted)
        with pytest.raises(ValueError):
            mod.validate_result(promoted)


def test_no_execution_or_data_access_flags_are_promoted():
    result = mod.execute(mod.load_config())
    for flag in mod.PROHIBITED_TRUE_FLAGS:
        assert result[flag] is False


def test_path_escape_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        mod.repo_path(tmp_path, "../escape.json")
