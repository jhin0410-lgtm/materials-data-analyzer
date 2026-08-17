from materials_data_analyzer.research_loop.in625_nist_2923_mapping_proposal import (
    propose_nist_2923_workbook_mapping,
)


def _structure(headers, *, include_summary=True):
    sheets = [
        {
            "sheet_name": "Data",
            "preview_rows": [
                {
                    "row_number": 1,
                    "cells": [
                        {"column_index": index, "value": value}
                        for index, value in enumerate(headers)
                    ],
                }
            ],
        }
    ]
    if include_summary:
        sheets.append({"sheet_name": "Summary", "preview_rows": []})
    return {"sheets": sheets}


def test_mapping_proposal_detects_candidate_roles_but_never_commits_semantics():
    report = propose_nist_2923_workbook_mapping(
        _structure(
            [
                "Material",
                "Laser Power (W)",
                "Scan Speed (mm/s)",
                "Melt Pool Width (um)",
                "Melt Pool Depth (um)",
                "Folder Name",
                "Image Name",
            ]
        )
    )

    assert report["missing_expected_sheets"] == []
    assert report["all_required_measurement_roles_have_header_candidates"] is True
    assert report["status"] == "proposal_only"
    assert report["accepted_for_analysis"] is False
    assert report["automatic_role_assignment_committed"] is False
    assert report["requires_unit_semantics_verification"] is True
    assert report["requires_machine_material_calibration_mapping"] is True


def test_missing_summary_sheet_remains_unresolved_even_when_headers_look_good():
    report = propose_nist_2923_workbook_mapping(
        _structure(
            [
                "Laser Power",
                "Scan Speed",
                "Melt Pool Width",
                "Melt Pool Depth",
            ],
            include_summary=False,
        )
    )

    assert report["missing_expected_sheets"] == ["Summary"]
    assert report["all_required_measurement_roles_have_header_candidates"] is False
    assert report["scientific_status_changed"] is False


def test_ambiguous_width_header_is_only_a_candidate_not_an_authoritative_mapping():
    report = propose_nist_2923_workbook_mapping(_structure(["Width"]))
    proposal = report["observed_data_headers"][0]
    assert proposal["role_candidates"] == [
        {"candidate_role": "melt_pool_width", "match_strength": "weak"}
    ]
    assert report["accepted_for_analysis"] is False
