"""Proposal-only semantic mapping for the NIST mds2-2923 measurement workbook.

The public catalog establishes that the workbook contains individual measurements on a
``Data`` sheet and aggregate values on a ``Summary`` sheet. Exact workbook headers and
units still come from the acquired bytes. This module therefore proposes candidate roles
from observed preview text but never admits records or upgrades scientific status.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError

NIST_2923_MAPPING_PROPOSAL_SCHEMA_VERSION = "1.0"

_ROLE_PATTERNS = {
    "material": (r"\bmaterial\b", r"\balloy\b"),
    "laser_power": (r"\blaser\s*power\b", r"\bpower\b"),
    "scan_speed": (r"\bscan\s*speed\b", r"\bspeed\b"),
    "melt_pool_width": (r"\bmelt\s*pool\s*width\b", r"\bwidth\b"),
    "melt_pool_depth": (r"\bmelt\s*pool\s*depth\b", r"\bdepth\b"),
    "folder_identity": (r"\bfolder\b", r"\bdirectory\b"),
    "image_identity": (r"\bimage\b", r"\bfile\s*name\b", r"\bfilename\b"),
    "track_identity": (r"\btrack\b", r"\bline\b"),
}


class Nist2923MappingProposalError(ResearchLoopError):
    """Raised when a structural inventory cannot support a bounded mapping proposal."""


def _header_values(sheet: Mapping[str, Any]) -> list[tuple[int, str]]:
    rows = sheet.get("preview_rows")
    if not isinstance(rows, list):
        raise Nist2923MappingProposalError("Data sheet preview_rows must be a list")
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        cells = row.get("cells")
        if not isinstance(cells, list):
            continue
        values: list[tuple[int, str]] = []
        for cell in cells:
            if not isinstance(cell, Mapping):
                continue
            column = cell.get("column_index")
            value = cell.get("value")
            if isinstance(column, int) and column >= 0 and isinstance(value, str) and value.strip():
                values.append((column, value.strip()))
        if values:
            return values
    return []


def _role_matches(header: str) -> list[dict[str, Any]]:
    normalized = " ".join(header.casefold().replace("_", " ").replace("-", " ").split())
    matches: list[dict[str, Any]] = []
    for role, patterns in _ROLE_PATTERNS.items():
        best = 0
        for ordinal, pattern in enumerate(patterns):
            if re.search(pattern, normalized):
                best = max(best, 2 if ordinal == 0 else 1)
        if best:
            matches.append(
                {
                    "candidate_role": role,
                    "match_strength": "strong" if best == 2 else "weak",
                }
            )
    return matches


def propose_nist_2923_workbook_mapping(
    workbook_structure: Mapping[str, Any],
) -> dict[str, Any]:
    """Propose observed header-to-role candidates without admitting scientific records."""
    if not isinstance(workbook_structure, Mapping):
        raise Nist2923MappingProposalError("workbook_structure must be an object")
    sheets = workbook_structure.get("sheets")
    if not isinstance(sheets, list):
        raise Nist2923MappingProposalError("workbook_structure.sheets must be a list")
    by_name = {
        sheet.get("sheet_name"): sheet
        for sheet in sheets
        if isinstance(sheet, Mapping) and isinstance(sheet.get("sheet_name"), str)
    }
    missing = [name for name in ("Data", "Summary") if name not in by_name]
    data_headers = _header_values(by_name["Data"]) if "Data" in by_name else []
    proposals = [
        {
            "column_index": column,
            "observed_header": header,
            "role_candidates": _role_matches(header),
        }
        for column, header in data_headers
    ]
    proposed_roles = {
        match["candidate_role"]
        for proposal in proposals
        for match in proposal["role_candidates"]
    }
    required_measurement_roles = {
        "laser_power",
        "scan_speed",
        "melt_pool_width",
        "melt_pool_depth",
    }
    return {
        "schema_version": NIST_2923_MAPPING_PROPOSAL_SCHEMA_VERSION,
        "dataset_id": "mds2-2923",
        "status": "proposal_only",
        "expected_public_catalog_sheets": ["Data", "Summary"],
        "missing_expected_sheets": missing,
        "observed_data_headers": proposals,
        "candidate_roles_observed": sorted(proposed_roles),
        "required_measurement_roles_candidate_coverage": sorted(
            required_measurement_roles & proposed_roles
        ),
        "all_required_measurement_roles_have_header_candidates": (
            not missing and required_measurement_roles <= proposed_roles
        ),
        "accepted_for_analysis": False,
        "scientific_status_changed": False,
        "automatic_role_assignment_committed": False,
        "requires_unit_semantics_verification": True,
        "requires_machine_material_calibration_mapping": True,
        "requires_replication_identity_mapping": True,
        "limitations": [
            "Header text similarity is not an authoritative scientific schema mapping.",
            "Units, programmed-versus-achieved laser power, machine identity, material state, calibration binding, and replicate identity must be verified from exact source evidence before record admission.",
            "Summary rows may not be substituted for independent raw physical replicates."
        ],
    }


__all__ = [
    "NIST_2923_MAPPING_PROPOSAL_SCHEMA_VERSION",
    "Nist2923MappingProposalError",
    "propose_nist_2923_workbook_mapping",
]
