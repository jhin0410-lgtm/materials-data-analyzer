from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_closure as closure,
)


def _row_record(raw: bytes) -> dict[str, object]:
    return {
        "path": "/historical/reviewed_tensile_rows.v2.jsonl",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "row_count": len(raw.splitlines()),
    }


def test_retained_dataset_zip_does_not_skip_canonical_tensile_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "run"
    repo = tmp_path / "repo"
    root.mkdir()
    repo.mkdir()
    (root / "Dataset.zip").write_bytes(b"retained raw archive")

    policy_path = repo / closure._source_replay._REVIEWED_TENSILE_POLICY
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(
            {
                "workbook": {
                    "archive_member_path": "Dataset/workbook.xlsx",
                    "sha256": hashlib.sha256(b"workbook").hexdigest(),
                    "size_bytes": 8,
                },
                "documentation": {
                    "archive_member_path": "Dataset/README.txt",
                    "sha256": hashlib.sha256(b"readme").hexdigest(),
                    "size_bytes": 6,
                },
            }
        ),
        encoding="utf-8",
    )

    selected = root / closure._source_replay._SELECTED_SOURCE_ROOT / "Dataset"
    selected.mkdir(parents=True)
    (selected / "workbook.xlsx").write_bytes(b"workbook")
    (selected / "README.txt").write_bytes(b"readme")

    persisted_rows = b'{"row":1}\n'
    manifest_path = root / closure._source_replay._REVIEWED_TENSILE_MANIFEST
    manifest_path.parent.mkdir(parents=True)
    persisted_manifest = {
        "schema_version": "2.0",
        "measurement_row_count": 1,
        "row_artifact": _row_record(persisted_rows),
    }
    manifest_path.write_text(json.dumps(persisted_manifest), encoding="utf-8")
    (root / closure._source_replay._REVIEWED_TENSILE_ROWS).write_bytes(
        persisted_rows
    )

    monkeypatch.setattr(
        closure._merge_gate, "_trusted_repository_root", lambda: repo
    )
    called = {"value": False}

    def fake_builder(**kwargs: object) -> dict[str, object]:
        called["value"] = True
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True)
        (output_dir / "reviewed_tensile_rows.v2.jsonl").write_bytes(
            persisted_rows
        )
        return {
            "schema_version": "2.0",
            "measurement_row_count": 1,
            "row_artifact": _row_record(persisted_rows),
        }

    monkeypatch.setattr(
        closure, "build_reviewed_in625_tensile_intake_v2", fake_builder
    )

    closure._replay_reviewed_tensile_for_every_lifecycle(root)
    assert called["value"] is True


def _success_cycles() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for index in range(1, 13):
        cycle: dict[str, object] = {
            "cycle_index": index,
            "scientific_status_changed": False,
            "global_evidence_unavailability_claimed": False,
        }
        if index == 4:
            cycle.update(
                {
                    "directly_comparable_mds2_rows": 0,
                    "paper_claims_promoted_to_row_level_authority": False,
                    "direct_numerical_validation_authorized": False,
                    "issue_76_exact_target_cells_satisfied": 0,
                }
            )
        elif index == 6:
            cycle.update(
                {
                    "bridge_established": False,
                    "directly_comparable_mds2_rows": 0,
                    "issue_76_exact_target_cells_satisfied": 0,
                }
            )
        elif index == 8:
            cycle.update(
                {
                    "candidate_links_followed": 0,
                    "candidate_urls_gain_acquisition_authority": False,
                }
            )
        result.append(cycle)
    return result


@pytest.mark.parametrize(
    ("cycle_index", "field"),
    [
        (5, "global_evidence_unavailability_claimed"),
        (10, "scientific_status_changed"),
    ],
)
def test_every_success_cycle_rejects_authority_promotion(
    cycle_index: int, field: str
) -> None:
    closure._source_replay._DENIED_TRUE_AUTHORITY_FIELDS.add(
        "global_evidence_unavailability_claimed"
    )
    cycles = _success_cycles()
    cycles[cycle_index - 1][field] = True
    with pytest.raises(
        closure.AutonomousProductionExactHeadP2ClosureError,
        match="unsupported authority promotion",
    ):
        closure._verify_all_success_cycles(cycles)


def test_metadata_recorded_provenance_must_match_metadata_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "nist-mds2-2923" / "artifact-01"
    package.mkdir(parents=True)
    (package / "acquisition_manifest.json").write_text("{}", encoding="utf-8")
    (package / "acquisition_declaration.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        closure,
        "_ORIGINAL_NIST_PACKAGE_AUTHENTICATOR",
        lambda **kwargs: (b"evidence", b"metadata"),
    )
    monkeypatch.setattr(
        closure,
        "_metadata_candidate",
        lambda **kwargs: {
            "source_system": "NIST Public Data Repository (PDR/NERDm)",
            "source_version": "1.0.3",
            "retrieval_endpoint": "https://data.nist.gov/od/ds/mds2-2923/file",
        },
    )
    monkeypatch.setattr(
        closure,
        "authenticate_acquisition_record_binding",
        lambda **kwargs: {
            "recorded_source_system": "forged",
            "recorded_source_version": "1.0.3",
            "recorded_retrieval_endpoint": "https://data.nist.gov/od/ds/mds2-2923/file",
            "recorded_retrieval_status": "downloaded_checksum_verified",
            "recorded_network_performed": True,
        },
    )

    with pytest.raises(
        closure.AutonomousProductionExactHeadP2ClosureError,
        match="recorded provenance values disagree",
    ):
        closure._authenticate_nist_package_against_metadata(
            root=tmp_path,
            path="file",
            rule={},
            package_index=1,
            top_receipt={},
        )


def test_historical_nist_paths_are_relocated_only_by_exact_safe_suffix(
    tmp_path: Path,
) -> None:
    root = tmp_path / "relocated"
    nist = root / "nist-mds2-2923"
    (nist / "artifact-01").mkdir(parents=True)
    (nist / "artifact-02").mkdir(parents=True)
    (nist / "nerdm-metadata.json").write_bytes(b"metadata")
    (nist / "artifact-01" / "2923_README.txt").write_bytes(b"readme")
    (
        nist / "artifact-02" / "Master_TrackList_Measurements.xlsx"
    ).write_bytes(b"workbook")

    prefix = "/home/runner/work/repo/repo/outputs/autonomous-in625-production"
    receipt = {
        "metadata_path": f"{prefix}/nist-mds2-2923/nerdm-metadata.json",
        "artifact_paths": {
            "2923_README.txt": (
                f"{prefix}/nist-mds2-2923/artifact-01/2923_README.txt"
            ),
            "Master_TrackList_Measurements.xlsx": (
                f"{prefix}/nist-mds2-2923/artifact-02/"
                "Master_TrackList_Measurements.xlsx"
            ),
        },
        "receipts": [
            {"package_directory": f"{prefix}/nist-mds2-2923/artifact-01"},
            {"package_directory": f"{prefix}/nist-mds2-2923/artifact-02"},
        ],
    }
    mapping = closure._validate_relocation_safe_paths(root, receipt)
    assert (
        mapping[receipt["artifact_paths"]["2923_README.txt"]]
        == (nist / "artifact-01" / "2923_README.txt").resolve()
    )

    receipt["receipts"][0]["package_directory"] = (
        "../../nist-mds2-2923/artifact-01"
    )
    with pytest.raises(
        closure.AutonomousProductionExactHeadP2ClosureError,
        match="traversal",
    ):
        closure._validate_relocation_safe_paths(root, receipt)


def test_verified_new_evidence_is_exactly_derived_from_intake() -> None:
    intake = {
        "source": {"product_id": "mds2-2923"},
        "in625_inventory": {
            "physical_track_count": 106,
            "measurement_row_count": 178,
            "machine_measurement_counts": {"AMMT": 34, "EOS M270": 144},
            "machine_physical_track_counts": {"AMMT": 34, "EOS M270": 72},
            "source_track_metadata_conflict_count": 1,
        },
        "measurements": [{"material": "IN625"} for _ in range(178)],
    }
    assert closure._expected_verified_new_evidence(intake) == {
        "dataset_local_physical_track_count": 106,
        "geometry_response_compatibility_established": True,
        "machine_measurement_counts": {"AMMT": 34, "EOS M270": 144},
        "machine_physical_track_counts": {"AMMT": 34, "EOS M270": 72},
        "material": "IN625",
        "measurement_row_count": 178,
        "response_semantics": ["melt_pool_width", "melt_pool_depth"],
        "row_level_authority": "Data sheet",
        "source": "NIST PDR mds2-2923",
        "source_metadata_conflict_count": 1,
        "summary_role": "incomplete_derived_view",
    }
