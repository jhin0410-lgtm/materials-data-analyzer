from __future__ import annotations

import json
from pathlib import Path


SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "research"
    / "tm_fe_si_cross_repo_real_replay.v1.json"
)


def test_tm_fe_si_real_replay_stays_descriptive_and_fail_closed() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    producer = payload["mca_producer"]
    assert producer["merge_commit"] == (
        "9be7c5ab439add42f0612b12477e819759ca2d55"
    )
    assert producer["bundle_manifest_sha256"] == (
        "c4305411f6a0232f1a567637672ad9527a9b098a881716ffc3eeecea4c0b8cfb"
    )

    replay = payload["descriptive_replay"]
    assert replay["status"] == "verified_descriptive_cross_repo_case"
    assert replay["sample_count"] == 6
    assert replay["characterization_evidence_level"] == "Diagnostic"
    assert replay["requested_use"] == "descriptive"
    assert replay["maximum_allowed_use"] == "descriptive"
    assert replay["identity_fields_verified"] == [
        "sample_id",
        "nominal_composition",
        "preparation_family_id",
    ]
    assert replay["row_order_join_used"] is False
    assert replay["exact_xrd_vsm_physical_aliquot_identity_confirmed"] is False
    assert replay["correlation_computed"] is False
    assert replay["hypothesis_test_computed"] is False
    assert replay["model_trained"] is False
    assert replay["saturation_magnetization_claimed"] is False
    assert replay["interpolation_performed"] is False
    assert replay["smoothing_performed"] is False

    negative = payload["stronger_use_negative_control"]
    assert negative["requested_use"] == "predictive"
    assert negative["exit_code"] == 1
    assert negative["output_created"] is False
    assert negative["staging_directory_left_behind"] is False

    closeout = payload["scientific_closeout"]
    assert closeout["evidence_level"] == "Diagnostic"
    assert "prediction" in closeout["unsupported_for"]
    assert "causality" in closeout["unsupported_for"]
    assert "engineering decision" in closeout["unsupported_for"]
