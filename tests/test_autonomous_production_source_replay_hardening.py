from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_source_replay_hardening as hardening,
)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _rehash(value: dict[str, Any], field: str) -> None:
    value.pop(field, None)
    value[field] = hardening._canonical_sha(value)


def test_jointly_rehashed_reviewed_tensile_jsonl_is_rejected_by_source_replay() -> None:
    replay_rows = b'{"load_n":null,"source":"exact"}\n'
    forged_rows = b'{"load_n":999.0,"source":"forged"}\n'
    replay_manifest: dict[str, Any] = {
        "schema_version": "2.0",
        "measurement_row_count": 1,
        "scientific_boundaries": {"automatic_scientific_promotion": False},
        "row_artifact": {
            "path": "/tmp/replay.jsonl",
            "sha256": hashlib.sha256(replay_rows).hexdigest(),
            "bytes": len(replay_rows),
            "row_count": 1,
        },
    }
    persisted_manifest = copy.deepcopy(replay_manifest)
    persisted_manifest["row_artifact"] = {
        "path": "/persisted/reviewed_tensile_rows.v2.jsonl",
        "sha256": hashlib.sha256(forged_rows).hexdigest(),
        "bytes": len(forged_rows),
        "row_count": 1,
    }
    _rehash(persisted_manifest, "manifest_sha256")
    _rehash(replay_manifest, "manifest_sha256")

    with pytest.raises(
        hardening.AutonomousProductionSourceReplayHardeningError,
        match="row artifact does not match canonical source-byte replay",
    ):
        hardening._require_tensile_replay_match(
            persisted_manifest=persisted_manifest,
            persisted_row_bytes=forged_rows,
            replay_manifest=replay_manifest,
            replay_row_bytes=replay_rows,
        )


def test_merge_gate_replays_canonical_acquisition_record_binding(
    tmp_path: Path,
) -> None:
    evidence = b"exact NIST source evidence\n"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    metadata = b'{"@id":"mds2-test"}\n'
    metadata_sha = hashlib.sha256(metadata).hexdigest()

    manifest = {
        "artifact": {"sha256": evidence_sha},
        "source": {"system": "NIST PDR", "version": "authenticated-real-version"},
        "retrieval": {
            "endpoint": "https://data.nist.gov/exact",
            "status": "success",
            "network_performed": True,
        },
    }
    manifest_bytes = _json_bytes(manifest)
    declaration = {
        "schema_version": "1.0",
        "acquisition_id": "regression-forged-self-consistent-record",
        "evidence_artifact_sha256": evidence_sha,
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "evidence_role": "source_artifact",
        "manifest_evidence_sha256_pointer": "/artifact/sha256",
        "manifest_claim_bindings": [
            {
                "claim": "source_system",
                "json_pointer": "/source/system",
                "expected_value": "NIST PDR",
            },
            {
                "claim": "source_version",
                "json_pointer": "/source/version",
                "expected_value": "jointly-forged-version",
            },
            {
                "claim": "retrieval_endpoint",
                "json_pointer": "/retrieval/endpoint",
                "expected_value": "https://data.nist.gov/exact",
            },
            {
                "claim": "retrieval_status",
                "json_pointer": "/retrieval/status",
                "expected_value": "success",
            },
            {
                "claim": "network_performed",
                "json_pointer": "/retrieval/network_performed",
                "expected_value": True,
            },
        ],
        "limitations": ["regression fixture; no scientific authority"],
    }
    declaration_bytes = _json_bytes(declaration)

    package = tmp_path / "nist-mds2-2923" / "artifact-01"
    package.mkdir(parents=True)
    (package / "fixture.bin").write_bytes(evidence)
    (package / "source_metadata.json").write_bytes(metadata)
    (package / "acquisition_manifest.json").write_bytes(manifest_bytes)
    (package / "acquisition_declaration.json").write_bytes(declaration_bytes)

    top_receipt = {
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "acquisition_declaration_sha256": hashlib.sha256(declaration_bytes).hexdigest(),
    }
    with pytest.raises(
        hardening.AutonomousProductionSourceReplayHardeningError,
        match="canonical acquisition-record binding failed",
    ):
        hardening._authenticate_nist_package(
            root=tmp_path,
            path="fixture.bin",
            rule={"sha256": evidence_sha, "size_bytes": len(evidence)},
            package_index=1,
            top_receipt=top_receipt,
            expected_metadata_sha256=metadata_sha,
        )


def test_rehashed_nist_intake_semantic_forgery_is_rejected_by_source_replay() -> None:
    replayed: dict[str, Any] = {
        "schema_version": "1.0",
        "source": {"product_id": "mds2-2923"},
        "in625_inventory": {"measurement_row_count": 178},
        "scientific_boundary": {"scientific_support_established": False},
    }
    _rehash(replayed, "report_sha256_without_self_field")
    persisted = copy.deepcopy(replayed)
    persisted["in625_inventory"]["measurement_row_count"] = 999
    persisted["scientific_boundary"]["scientific_support_established"] = True
    _rehash(persisted, "report_sha256_without_self_field")

    with pytest.raises(
        hardening.AutonomousProductionSourceReplayHardeningError,
        match="scientific intake does not match canonical source-byte replay",
    ):
        hardening._require_nist_intake_replay_match(
            persisted=persisted,
            replayed=replayed,
        )


def _late_cycle_manifest() -> dict[str, Any]:
    cycles: list[dict[str, Any]] = []
    predecessor: str | None = None
    for index in range(1, 9):
        cycle: dict[str, Any] = {
            "cycle_index": index,
            "scientific_status_changed": False,
        }
        if predecessor is not None:
            cycle["predecessor_cycle_sha256"] = predecessor
        if index == 4:
            cycle.update(
                {
                    "directly_comparable_mds2_rows": 0,
                    "paper_claims_promoted_to_row_level_authority": False,
                    "direct_numerical_validation_authorized": False,
                    "issue_76_exact_target_cells_satisfied": 0,
                }
            )
        if index == 6:
            cycle.update(
                {
                    "bridge_established": False,
                    "directly_comparable_mds2_rows": 0,
                    "issue_76_exact_target_cells_satisfied": 0,
                }
            )
        if index == 8:
            cycle.update(
                {
                    "candidate_links_followed": 0,
                    "candidate_urls_gain_acquisition_authority": False,
                }
            )
        cycle["cycle_sha256"] = hardening._canonical_sha(cycle)
        predecessor = cycle["cycle_sha256"]
        cycles.append(cycle)
    manifest: dict[str, Any] = {"cycles": cycles}
    manifest["manifest_sha256"] = hardening._canonical_sha(manifest)
    return manifest


def _rehash_cycle_suffix(manifest: dict[str, Any], *, start_index: int) -> None:
    cycles = [dict(item) for item in manifest["cycles"]]
    for index in range(start_index - 1, len(cycles)):
        cycle = cycles[index]
        cycle.pop("cycle_sha256", None)
        if index > 0:
            cycle["predecessor_cycle_sha256"] = cycles[index - 1]["cycle_sha256"]
        cycle["cycle_sha256"] = hardening._canonical_sha(cycle)
        cycles[index] = cycle
    manifest["cycles"] = cycles
    _rehash(manifest, "manifest_sha256")


def test_rehashed_cycle_4_to_8_authority_promotion_is_rejected() -> None:
    manifest = _late_cycle_manifest()
    cycles = hardening._verify_cycle_chain(manifest)
    hardening._verify_late_cycle_authority_boundaries(cycles)

    forged = copy.deepcopy(manifest)
    forged["cycles"][5]["optimization_authorized"] = True
    _rehash_cycle_suffix(forged, start_index=6)

    authenticated_cycles = hardening._verify_cycle_chain(forged)
    with pytest.raises(
        hardening.AutonomousProductionSourceReplayHardeningError,
        match="cycle 6 attempted unsupported authority promotion",
    ):
        hardening._verify_late_cycle_authority_boundaries(authenticated_cycles)


def test_live_workflow_retains_successful_nist_source_packages() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/autonomous-production-live.yml"
    ).read_text(encoding="utf-8")
    assert "outputs/autonomous-in625-production/nist-mds2-2923/**" in workflow
