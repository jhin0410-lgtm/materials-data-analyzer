"""Source-row semantic contract for the SSRM titanium description workbook.

The source does not provide prose declarations such as ``TiGd1 - Ti powder``.
Instead, the workbook explicitly places a source file identifier and its physical
material description on the same row.  This adapter permits that row relationship
as evidence while continuing to forbid filename-only sample-identity inference.
"""

from __future__ import annotations

from typing import Any

from .ssrm_titanium_scientific_intake import SsrmTitaniumScientificIntakeError

_ALIAS_REQUIREMENTS = {
    "TiGd1": (
        "66573_DC_TiGd1_500_50_10h_3",
        "The temperature and pressure signals within the cylinder colected during milling of Ti powder under nitrogen pressure",
        "Ti",
    ),
    "Ti64": (
        "66573_DC_Ti64_500_50_10h_3",
        "The temperature and pressure signals within the cylinder colected during milling of Ti6Al4V powder under nitrogen pressure",
        "Ti6Al4V",
    ),
    "Ti5553": (
        "66573_DC_Ti5553_500_50_10h_3",
        "The temperature and pressure signals within the cylinder colected during milling of Ti5553 powder under nitrogen pressure",
        "Ti5553",
    ),
}

_REQUIRED_DESCRIPTIONS = (
    "EDS line scan of nitrogen content in Ti64 powder milled for 10 h under nitrogen pressure",
    "Raman data for Ti powder at the initial stage or milled for 5, 15, 30, 60 and 600 min",
    "Raman data for Ti6Al4V powder at the initial stage or milled for 5, 15, 30, 60 and 600 min",
    "Raman data for Ti5553 powder at the initial stage or milled for 5, 15, 30, 60 and 600 min",
    "Ti, Ti6Al4V and Ti5553 powders at the initial stage or milled for 5, 15, 30, 60 and 600 min",
)


def validate_ssrm_description_contract(rows: list[list[Any]]) -> dict[str, Any]:
    """Return source-supported aliases from exact same-row file/description pairs."""

    row_pairs: set[tuple[str, str]] = set()
    descriptions: set[str] = set()
    for row in rows:
        file_name = row[3] if len(row) > 3 else None
        description = row[4] if len(row) > 4 else None
        if isinstance(description, str):
            description = description.strip()
            descriptions.add(description)
        if isinstance(file_name, str) and isinstance(description, str):
            row_pairs.add((file_name.strip(), description))

    alias_map: dict[str, str] = {}
    missing_alias_rows: list[str] = []
    for alias, (file_name, description, material) in _ALIAS_REQUIREMENTS.items():
        if (file_name, description) not in row_pairs:
            missing_alias_rows.append(alias)
        else:
            alias_map[alias] = material
    if missing_alias_rows:
        raise SsrmTitaniumScientificIntakeError(
            "description workbook lacks explicit same-row alias/material evidence: "
            f"{missing_alias_rows}"
        )

    missing_descriptions = [
        description
        for description in _REQUIRED_DESCRIPTIONS
        if description not in descriptions
    ]
    if missing_descriptions:
        raise SsrmTitaniumScientificIntakeError(
            "description workbook no longer supports declared characterization semantics: "
            f"{missing_descriptions}"
        )

    return {
        "alias_map": alias_map,
        "alias_binding_basis": "same_source_workbook_row_file_name_plus_physical_description",
        "filename_alone_used_as_sample_identity": False,
        "milling_speed_rpm": 500,
        "nitrogen_pressure_bar": 50,
        "declared_characterization_times_min": [0, 5, 15, 30, 60, 600],
        "logger_active_window_explicitly_marked": False,
        "raman_p1_to_p10_semantics_explicitly_defined": False,
        "suffix_1_or_3_replicate_semantics_explicitly_defined": False,
        "cross_technique_identical_aliquot_explicitly_defined": False,
    }
