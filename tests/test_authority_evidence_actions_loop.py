from __future__ import annotations

import json

from materials_data_analyzer.research_loop.authority_evidence_actions import (
    run_local_authority_evidence_loop,
)
from materials_data_analyzer.research_loop.delimited_structural_intake import (
    inspect_delimited_structure,
)
from materials_data_analyzer.research_loop.generic_semantic_lineage_proposal import (
    build_generic_semantic_lineage_proposal,
)
from materials_data_analyzer.research_loop.reviewed_resolution_compiler import (
    build_reviewed_resolution_contract,
)

BODY = b"sample_id,acquisition_id,value\ns1,a1,1.2\ns2,a2,1.4\n"


def _semantic():
    return {
        "source_id": "source:authority-action-fixture",
        "material": {
            "kind": "identity",
            "material_name": "Example Alloy",
            "declared_identifier": "EXAMPLE-ALLOY",
            "identity_basis": "source_declared_label",
        },
        "sample_id_column": 0,
        "sample_identity_authority": "authoritative_source_column",
        "property_name": "explicitly_resolved_property",
        "value_column": 2,
        "unit": "resolved-unit",
        "method": "resolved-method",
        "instrument_model": "resolved-instrument",
        "calibration_status": "not_reported_no_claim",
        "calibration_id": None,
        "process_signature": None,
        "standard_uncertainty": {"mode": "none"},
    }


def _lineage():
    return {
        "specimen_id_column": 0,
        "specimen_identity_authority": "authoritative_source_column",
        "acquisition_id_column": 1,
        "acquisition_identity_authority": "authoritative_source_column",
        "lab_id_column": None,
        "material_lot_id_column": None,
        "build_or_synthesis_id_column": None,
        "process_run_id_column": None,
    }


def resolution():
    structure = inspect_delimited_structure(BODY)
    proposal = build_generic_semantic_lineage_proposal(
        candidate_id="candidate:authority-action-fixture",
        structure=structure,
    )
    return build_reviewed_resolution_contract(
        structure=structure,
        proposal=proposal,
        semantic_resolution=_semantic(),
        lineage_resolution=_lineage(),
    )


def claim_values():
    semantic = _semantic()
    lineage = _lineage()
    return {
        "material_identity": semantic["material"],
        "sample_identity": {"column_index": semantic["sample_id_column"]},
        "property_semantics": {
            "property_name": semantic["property_name"],
            "value_column": semantic["value_column"],
        },
        "unit": semantic["unit"],
        "method": semantic["method"],
        "instrument_model": semantic["instrument_model"],
        "specimen_identity": {"column_index": lineage["specimen_id_column"]},
        "acquisition_identity": {"column_index": lineage["acquisition_id_column"]},
    }


def metadata(*claims, overrides=None):
    values = claim_values()
    overrides = {} if overrides is None else dict(overrides)
    lines = [b"Companion metadata.\n"]
    for claim in claims:
        value = overrides.get(claim, values[claim])
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        lines.append(f"resolution-authority:{claim}={payload}\n".encode("utf-8"))
    return b"".join(lines)


def companion(label, data):
    return {
        "artifact_label": label,
        "artifact_bytes": data,
        "provenance_ref": f"archive-member:{label}",
        "authorization_ref": "upstream-acquisition-boundary:fixture",
    }


def test_companion_readme_closes_all_authority_gaps():
    claims = tuple(claim_values())
    result = run_local_authority_evidence_loop(
        resolution_contract=resolution(),
        companion_artifacts=[companion("README.txt", metadata(*claims))],
    )
    assert result["status"] == "completed"
    assert result["stop_reason"] == "all_required_authority_source_backed"
    assert result["authority_packet"]["all_positive_resolution_claims_source_authorized"] is True
    assert result["authority_gap_assessment"]["authority_gaps"] == []
    assert len(result["action_results"]) == 1
    action = result["action_results"][0]
    assert action["action_request"]["target_claims"] == sorted(claims)
    assert len(action["produced_authority_record_sha256"]) == 8
    assert action["network_performed"] is False
    assert action["semantic_inference_performed"] is False
    assert len(action["action_request_sha256"]) == 64
    assert len(action["action_result_sha256"]) == 64
    assert result["scientific_support_established"] is False


def test_partial_readme_replans_only_residual_gaps():
    claims = list(claim_values())
    result = run_local_authority_evidence_loop(
        resolution_contract=resolution(),
        companion_artifacts=[
            companion("README-primary.txt", metadata(*claims[:6])),
            companion("README-secondary.txt", metadata(*claims[6:])),
        ],
    )
    assert result["status"] == "completed"
    assert len(result["action_results"]) == 2
    second = result["action_results"][1]
    assert set(second["action_request"]["target_claims"]) == set(claims[6:])
    assert set(second["searched_claims"]) == set(claims[6:])
    assert second["negative_claims"] == []


def test_conflicting_authority_stops_with_targeted_conflict_action():
    claims = tuple(claim_values())
    result = run_local_authority_evidence_loop(
        resolution_contract=resolution(),
        companion_artifacts=[
            companion(
                "README-conflict.txt",
                metadata(*claims, overrides={"unit": "wrong-unit"}),
            )
        ],
    )
    assert result["status"] == "stopped"
    assert result["stop_reason"] == "unresolved_authority_conflict"
    assert result["authority_gap_assessment"]["authority_conflicts"] == ["unit"]
    assert result["authority_packet"] is None
    assert result["next_action_request"]["action_class"] == "resolve_authority_conflict"
    assert result["next_action_request"]["target_claims"] == ["unit"]


def test_negative_search_path_is_persisted_and_not_repeated():
    prose = b"Free-form README only. Units and methods must not be inferred.\n"
    first = run_local_authority_evidence_loop(
        resolution_contract=resolution(),
        companion_artifacts=[companion("README-prose.txt", prose)],
    )
    assert first["stop_reason"] == "no_authorized_route_remains"
    assert len(first["action_results"]) == 1
    negative = first["action_results"][0]
    assert negative["produced_authority_record_sha256"] == []
    assert set(negative["negative_claims"]) == set(claim_values())

    second = run_local_authority_evidence_loop(
        resolution_contract=resolution(),
        companion_artifacts=[companion("README-prose.txt", prose)],
        prior_action_results=first["action_results"],
    )
    assert second["stop_reason"] == "no_authorized_route_remains"
    assert second["new_action_result_count"] == 0
    assert len(second["action_results"]) == 1
