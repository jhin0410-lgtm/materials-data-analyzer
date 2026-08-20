from __future__ import annotations

import hashlib

import pytest

from materials_data_analyzer.research_loop.delimited_structural_intake import (
    DelimitedStructuralIntakeError,
    inspect_delimited_structure,
    structural_intake_acquired_delimited,
)


def test_unseen_csv_is_structurally_inspectable_without_semantic_promotion():
    raw = (
        b"replicate_id,time_s,voltage_v,status\n"
        b"r1,0.0,1.01,ok\n"
        b"r1,0.2,1.00,ok\n"
        b"r1,0.4,0.99,ok\n"
    )

    report = inspect_delimited_structure(raw)

    assert report["artifact_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["delimiter_name"] == "comma"
    assert report["parsed_row_count"] == 4
    assert report["maximum_column_count"] == 4
    assert report["rectangular"] is True
    assert report["column_profiles"][3]["constant_nonblank_signal"] is True
    assert "replicate_like" in report["column_profiles"][0][
        "header_semantic_hints_proposal_only"
    ]
    assert report["replicate_independence_inferred"] is False
    assert report["sample_identity_inferred"] is False
    assert report["measurement_semantics_interpreted"] is False
    assert report["scientific_support_established"] is False
    assert report["scientific_status_changed"] is False
    assert report["accepted_for_analysis"] is False


def test_tsv_hint_parses_but_rows_never_become_independent_n():
    raw = b"frequency_hz\treal_z\timag_z\n1000\t1.0\t-0.1\n100\t1.2\t-0.3\n"

    report = inspect_delimited_structure(raw, delimiter_hint="\t")

    assert report["delimiter_name"] == "tab"
    assert report["data_row_count_if_first_row_is_header"] == 2
    assert "frequency_like" in report["column_profiles"][0][
        "header_semantic_hints_proposal_only"
    ]
    assert all(
        profile["row_values_are_independent_specimens"] is False
        for profile in report["column_profiles"]
    )


def test_plain_text_without_stable_table_fails_closed():
    with pytest.raises(DelimitedStructuralIntakeError, match="no safe delimited"):
        inspect_delimited_structure(b"This is prose.\nIt has multiple lines.\nNo table here.\n")


def test_binary_and_invalid_utf8_fail_closed():
    with pytest.raises(DelimitedStructuralIntakeError, match="NUL"):
        inspect_delimited_structure(b"a,b\n1,\x00\n")
    with pytest.raises(DelimitedStructuralIntakeError, match="UTF-8"):
        inspect_delimited_structure(b"a,b\n1,\xff\n")


def test_byte_row_column_and_cell_ceilings_are_enforced():
    raw = b"a,b\n1,2\n"
    with pytest.raises(DelimitedStructuralIntakeError, match="byte ceiling"):
        inspect_delimited_structure(raw, max_bytes=5)
    with pytest.raises(DelimitedStructuralIntakeError, match="row ceiling"):
        inspect_delimited_structure(raw, max_rows=1)
    with pytest.raises(DelimitedStructuralIntakeError, match="column ceiling"):
        inspect_delimited_structure(raw, max_columns=1)
    with pytest.raises(DelimitedStructuralIntakeError, match="character ceiling"):
        inspect_delimited_structure(b"a,b\n1234,2\n", max_cell_characters=3)


def test_acquired_delimited_intake_rechecks_exact_sha(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    artifact = package / "measurements.csv"
    original = b"sample,value\ns1,1\ns2,2\n"
    artifact.write_bytes(original)
    receipt = {
        "artifact_path": "measurements.csv",
        "artifact_sha256": hashlib.sha256(original).hexdigest(),
    }

    result = structural_intake_acquired_delimited(
        receipt=receipt,
        package_directory=package,
        evidence_gap={"kind": "unknown"},
    )
    assert result["artifact_sha256"] == receipt["artifact_sha256"]
    assert result["decision"] == "requires_domain_scientific_mapping"
    assert result["accepted_for_analysis"] is False

    artifact.write_bytes(original + b"s3,3\n")
    with pytest.raises(DelimitedStructuralIntakeError, match="receipt SHA-256"):
        structural_intake_acquired_delimited(
            receipt=receipt,
            package_directory=package,
            evidence_gap={"kind": "unknown"},
        )
