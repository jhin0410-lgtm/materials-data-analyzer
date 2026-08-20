from __future__ import annotations

import hashlib

from materials_data_analyzer.research_loop.public_scientific_intake_router import (
    route_public_scientific_intake,
)


def _receipt(path: str, body: bytes) -> dict[str, str]:
    return {
        "artifact_path": path,
        "artifact_sha256": hashlib.sha256(body).hexdigest(),
        "candidate_id": "unseen-public-source",
    }


def test_router_structurally_intakes_unseen_csv_without_accepting_analysis(tmp_path):
    body = b"sample_id,value\ns1,1\ns2,2\n"
    (tmp_path / "unknown.csv").write_bytes(body)

    result = route_public_scientific_intake(
        receipt=_receipt("unknown.csv", body),
        package_directory=tmp_path.as_posix(),
        evidence_gap={"question": "what is this table?"},
    )

    assert result["adapter"] == "delimited_structural_intake"
    assert result["decision"] == "requires_domain_scientific_mapping"
    assert result["delimited_structure"]["delimiter_name"] == "comma"
    assert result["delimited_structure"]["sample_identity_inferred"] is False
    assert result["delimited_structure"]["replicate_independence_inferred"] is False
    assert result["accepted_for_analysis"] is False
    assert result["scientific_status_changed"] is False


def test_router_structurally_intakes_tsv_and_fails_closed_on_prose_txt(tmp_path):
    tsv = b"time_s\tvalue\n0\t1\n1\t2\n"
    prose = b"A README paragraph.\nAnother sentence without a table.\n"
    (tmp_path / "trace.tsv").write_bytes(tsv)
    (tmp_path / "README.txt").write_bytes(prose)

    routed_tsv = route_public_scientific_intake(
        receipt=_receipt("trace.tsv", tsv),
        package_directory=tmp_path.as_posix(),
        evidence_gap=None,
    )
    routed_text = route_public_scientific_intake(
        receipt=_receipt("README.txt", prose),
        package_directory=tmp_path.as_posix(),
        evidence_gap=None,
    )

    assert routed_tsv["adapter"] == "delimited_structural_intake"
    assert routed_tsv["delimited_structure"]["delimiter_name"] == "tab"
    assert routed_text["decision"] == "structural_intake_failed"
    assert routed_text["reason_codes"] == ["delimited_structural_intake_failed"]
    assert routed_text["accepted_for_analysis"] is False
    assert routed_text["scientific_status_changed"] is False


def test_router_refuses_mutated_acquired_bytes(tmp_path):
    original = b"x,y\n1,2\n"
    mutated = b"x,y\n1,3\n"
    (tmp_path / "measurements.csv").write_bytes(mutated)

    result = route_public_scientific_intake(
        receipt=_receipt("measurements.csv", original),
        package_directory=tmp_path.as_posix(),
        evidence_gap=None,
    )

    assert result["decision"] == "structural_intake_failed"
    assert "receipt SHA-256" in result["error"]
    assert result["accepted_for_analysis"] is False
    assert result["scientific_status_changed"] is False


def test_router_keeps_unknown_binary_suffix_on_domain_intake_boundary(tmp_path):
    body = b"binary-placeholder"
    (tmp_path / "image.tif").write_bytes(body)

    result = route_public_scientific_intake(
        receipt=_receipt("image.tif", body),
        package_directory=tmp_path.as_posix(),
        evidence_gap=None,
    )

    assert result["decision"] == "requires_domain_scientific_intake"
    assert result["reason_codes"] == [
        "no_safe_structural_or_domain_intake_adapter_registered"
    ]
    assert result["accepted_for_analysis"] is False
    assert result["scientific_status_changed"] is False
