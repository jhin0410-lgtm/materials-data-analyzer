from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round3 as round3,
)


def _canonical_sha(value: dict[str, Any], self_field: str) -> str:
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


def _hashed(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = _canonical_sha(result, field)
    return result


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_round3_preflight_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    (tmp_path / "ambiguous.json").write_text(
        '{"scientific_status_changed":true,"scientific_status_changed":false}\n',
        encoding="utf-8",
    )
    with pytest.raises(
        round3.AutonomousProductionExactHeadRound3Error,
        match="duplicate key: scientific_status_changed",
    ):
        round3.verify_exact_head_round3_preflight(tmp_path)


def test_quality_contract_historical_path_resolves_from_trusted_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = tmp_path / "checkout"
    current = trusted / round3._QUALITY_CONTRACT
    current.parent.mkdir(parents=True)
    current.write_text("{}\n", encoding="utf-8")
    historical = (
        "/home/runner/work/materials-data-analyzer/materials-data-analyzer/"
        + round3._QUALITY_CONTRACT
    )
    quality = {"quality_contract": {"path": historical, "sha256": "0" * 64, "bytes": 3}}
    observed: dict[str, Path] = {}

    monkeypatch.setattr(round3._merge_gate, "_trusted_repository_root", lambda: trusted)

    def fake_original(
        *, root: Path, quality: object
    ) -> tuple[dict[str, Any], Path]:
        observed["root"] = root
        observed["path"] = round3._semantic.Path(historical).resolve(strict=True)
        return {}, trusted

    monkeypatch.setattr(round3, "_ORIGINAL_LOAD_BOUND_QUALITY_CONTRACT", fake_original)
    _, repository_root = round3._relocation_safe_quality_contract(
        root=tmp_path / "relocated-output",
        quality=quality,
    )
    assert repository_root == trusted
    assert observed["path"] == current.resolve(strict=True)
    assert trusted in observed["root"].parents


def test_qualification_frontier_historical_path_resolves_from_trusted_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = tmp_path / "checkout"
    current = trusted / round3._semantic.FRONTIER_PATH
    current.parent.mkdir(parents=True)
    current.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "relocated-output"
    output.mkdir()
    historical = (
        "/home/runner/work/materials-data-analyzer/materials-data-analyzer/"
        + round3._semantic.FRONTIER_PATH
    )
    _write_json(
        output / "nist-network-policy-qualification.json",
        {"frontier_path": historical},
    )
    observed: dict[str, Path] = {}
    monkeypatch.setattr(round3._merge_gate, "_trusted_repository_root", lambda: trusted)

    def fake_original(root: Path) -> Path:
        value = round3._semantic._load(
            root, "nist-network-policy-qualification.json"
        )
        observed["path"] = round3._semantic.Path(
            value["frontier_path"]
        ).resolve(strict=True)
        return trusted

    monkeypatch.setattr(round3, "_ORIGINAL_VERIFY_QUALIFICATION", fake_original)
    assert round3._relocation_safe_qualification(output) == trusted
    assert observed["path"] == current.resolve(strict=True)


def test_reviewed_tensile_historical_paths_resolve_from_replay_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = tmp_path / "checkout"
    root = tmp_path / "relocated-output"
    policy_path = trusted / round3._REVIEWED_TENSILE_POLICY
    policy_path.parent.mkdir(parents=True)
    workbook_member = "Dataset/Mechanical testing/Tensile tests/Tensile tests.xlsx"
    documentation_member = (
        "Dataset/Mechanical testing/Tensile tests/README-Tensile tests.txt"
    )
    _write_json(
        policy_path,
        {
            "workbook": {"archive_member_path": workbook_member},
            "documentation": {"archive_member_path": documentation_member},
        },
    )
    workbook = root / round3._SELECTED_SOURCE_ROOT / workbook_member
    documentation = root / round3._SELECTED_SOURCE_ROOT / documentation_member
    rows = root / round3._REVIEWED_TENSILE_ROWS
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"xlsx")
    documentation.write_text("readme", encoding="utf-8")
    rows.parent.mkdir(parents=True, exist_ok=True)
    rows.write_text("{}\n", encoding="utf-8")

    prefix = "/old/runner/materials-data-analyzer/"
    manifest = {
        "policy": {"path": prefix + round3._REVIEWED_TENSILE_POLICY},
        "workbook": {
            "path": prefix
            + "outputs/autonomous-in625-production/"
            + round3._SELECTED_SOURCE_ROOT
            + "/"
            + workbook_member
        },
        "documentation": {
            "path": prefix
            + "outputs/autonomous-in625-production/"
            + round3._SELECTED_SOURCE_ROOT
            + "/"
            + documentation_member
        },
        "row_artifact": {
            "path": prefix
            + "outputs/autonomous-in625-production/"
            + round3._REVIEWED_TENSILE_ROWS
        },
    }
    _write_json(root / round3._REVIEWED_TENSILE_MANIFEST, manifest)
    observed: dict[str, Path] = {}

    def fake_original(**_: object) -> None:
        observed["policy"] = round3._lifecycle.Path(
            manifest["policy"]["path"]
        ).resolve(strict=True)
        observed["workbook"] = round3._lifecycle.Path(
            manifest["workbook"]["path"]
        ).resolve(strict=True)
        observed["documentation"] = round3._lifecycle.Path(
            manifest["documentation"]["path"]
        ).resolve(strict=True)
        observed["rows"] = round3._lifecycle.Path(
            manifest["row_artifact"]["path"]
        ).resolve(strict=True)

    monkeypatch.setattr(round3, "_ORIGINAL_REVIEWED_TENSILE_CHAIN", fake_original)
    round3._relocation_safe_reviewed_tensile_chain(
        root=root,
        repository_root=trusted,
        cycle1={},
        archive_receipt={},
        selected_records={},
    )
    assert observed == {
        "policy": policy_path.resolve(strict=True),
        "workbook": workbook.resolve(strict=True),
        "documentation": documentation.resolve(strict=True),
        "rows": rows.resolve(strict=True),
    }


def _late_cycle_fixture(tmp_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cycles = [{"cycle_index": index} for index in range(1, 13)]
    manifest: dict[str, Any] = {"cycles": cycles}
    digests: dict[str, str] = {}
    for filename, self_field in round3._LATE_SELF_HASH_SPECS:
        report = _hashed({}, self_field)
        _write_json(tmp_path / filename, report)
        digests[filename] = report[self_field]

    for filename, bindings in round3._LATE_BINDINGS:
        digest = digests[filename]
        for scope, cycle_index, field in bindings:
            if scope == "manifest":
                manifest[field] = digest
            else:
                assert cycle_index is not None
                cycles[cycle_index - 1][field] = digest
    return manifest, cycles


def test_late_cycle_reports_are_self_authenticated_and_bound(tmp_path: Path) -> None:
    manifest, cycles = _late_cycle_fixture(tmp_path)
    round3._verify_late_cycle_reports(tmp_path, manifest, cycles)

    bridge_path = tmp_path / "calibration-protocol-bridge-capability-result.json"
    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    bridge["cross_machine_pooling_authorized"] = True
    bridge["report_sha256_without_self_field"] = _canonical_sha(
        bridge, "report_sha256_without_self_field"
    )
    _write_json(bridge_path, bridge)
    manifest["bridge_capability_execution_sha256"] = bridge[
        "report_sha256_without_self_field"
    ]

    with pytest.raises(
        round3.AutonomousProductionExactHeadRound3Error,
        match="cross_machine_pooling_authorized",
    ):
        round3._verify_late_cycle_reports(tmp_path, manifest, cycles)


def test_late_cycle_report_stale_self_hash_is_rejected(tmp_path: Path) -> None:
    manifest, cycles = _late_cycle_fixture(tmp_path)
    discovery_path = tmp_path / "calibration-record-source-discovery.json"
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    discovery["extra_claim"] = "forged"
    _write_json(discovery_path, discovery)

    with pytest.raises(
        round3.AutonomousProductionExactHeadRound3Error,
        match="self-hash mismatch",
    ):
        round3._verify_late_cycle_reports(tmp_path, manifest, cycles)


def test_transport_partial_output_presence_must_match_persisted_packages(
    tmp_path: Path,
) -> None:
    nist_root = tmp_path / "nist-mds2-2923"
    nist_root.mkdir()
    (nist_root / "nerdm-metadata.json").write_text("{}\n", encoding="utf-8")
    _write_json(
        tmp_path / "nist-transport-unavailability.json",
        {"partial_output_present": False},
    )
    manifest = {
        "stop": {"reason_code": round3._semantic.TRANSPORT_STOP_REASON_CODE}
    }
    with pytest.raises(
        round3.AutonomousProductionExactHeadRound3Error,
        match="partial_output_present disagrees",
    ):
        round3._verify_transport_partial_output(tmp_path, manifest)


def test_aggregate_nerdm_metadata_is_bound_to_receipt(tmp_path: Path) -> None:
    metadata = tmp_path / "nist-mds2-2923" / "nerdm-metadata.json"
    metadata.parent.mkdir()
    metadata.write_bytes(b'{"title":"exact"}\n')
    digest = hashlib.sha256(metadata.read_bytes()).hexdigest()
    _write_json(
        tmp_path / "nist-network-acquisition-receipt.json",
        {"metadata_sha256": digest},
    )
    round3._verify_aggregate_nerdm_metadata(
        tmp_path, {"nist_mds2_2923_metadata_sha256": digest}
    )

    metadata.write_bytes(b'{"title":"tampered"}\n')
    with pytest.raises(
        round3.AutonomousProductionExactHeadRound3Error,
        match="aggregate NERDm metadata SHA-256",
    ):
        round3._verify_aggregate_nerdm_metadata(
            tmp_path, {"nist_mds2_2923_metadata_sha256": digest}
        )


def test_tensile_quality_projection_matches_reviewed_manifest(tmp_path: Path) -> None:
    reviewed = {
        "manifest_sha256": "reviewed-sha",
        "reviewed_numeric_field_quality_counts": {
            "load_n": {"numeric": 200288, "blank": 1, "non_numeric": 0}
        },
        "sheets": [
            {
                "sheet_name": "AM-AB-H",
                "measurement_row_count": 33485,
                "complete_numeric_row_count": 33484,
                "incomplete_numeric_row_count": 1,
                "parallel_test_block_count": 3,
            }
        ],
    }
    quality = {
        "reviewed_tensile_manifest_sha256": "reviewed-sha",
        "reviewed_numeric_field_quality_counts": reviewed[
            "reviewed_numeric_field_quality_counts"
        ],
        "sheet_quality": {
            "AM-AB-H": {
                "measurement_row_count": 33485,
                "complete_numeric_row_count": 33484,
                "incomplete_numeric_row_count": 1,
                "parallel_test_block_count": 3,
            }
        },
    }
    _write_json(tmp_path / round3._REVIEWED_TENSILE_MANIFEST, reviewed)
    _write_json(tmp_path / "tensile-quality-verification.json", quality)
    round3._verify_tensile_quality_projection(tmp_path)

    quality["sheet_quality"]["AM-AB-H"]["complete_numeric_row_count"] = 1
    _write_json(tmp_path / "tensile-quality-verification.json", quality)
    with pytest.raises(
        round3.AutonomousProductionExactHeadRound3Error,
        match="sheet-quality projection",
    ):
        round3._verify_tensile_quality_projection(tmp_path)


def test_live_workflow_tracks_round3_parser_and_test_dependencies() -> None:
    text = Path(".github/workflows/autonomous-production-live.yml").read_text(
        encoding="utf-8"
    )
    parser = (
        "src/materials_data_analyzer/research_loop/"
        "xlsx_structural_intake.py"
    )
    assert text.count(f'- "{parser}"') == 2
    assert text.count(
        "tests/test_autonomous_production_exact_head_p2_round3.py"
    ) >= 3
