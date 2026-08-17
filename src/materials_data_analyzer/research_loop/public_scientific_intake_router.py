"""Conservative scientific-intake routing for automatically acquired public artifacts.

Only structural, non-semantic adapters are selected automatically here. A route can
inspect exact bytes and expose what domain mapping is still missing, but it cannot
promote an artifact to scientific evidence without a separately registered domain intake.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .in625_nist_2923_mapping_proposal import (
    Nist2923MappingProposalError,
    propose_nist_2923_workbook_mapping,
)
from .xlsx_structural_intake import (
    XlsxStructuralIntakeError,
    structural_intake_acquired_xlsx,
)

PUBLIC_SCIENTIFIC_INTAKE_ROUTER_SCHEMA_VERSION = "1.1"


def route_public_scientific_intake(
    *,
    receipt: Mapping[str, Any],
    package_directory: str,
    evidence_gap: object,
) -> Mapping[str, Any]:
    """Route exact acquired bytes to a safe structural adapter or fail closed."""
    artifact_path = receipt.get("artifact_path")
    suffix = Path(artifact_path).suffix.lower() if isinstance(artifact_path, str) else ""
    if suffix == ".xlsx":
        try:
            result = structural_intake_acquired_xlsx(
                receipt=receipt,
                package_directory=package_directory,
                evidence_gap=evidence_gap,
            )
        except (XlsxStructuralIntakeError, OSError) as exc:
            return {
                "schema_version": PUBLIC_SCIENTIFIC_INTAKE_ROUTER_SCHEMA_VERSION,
                "decision": "structural_intake_failed",
                "accepted_for_analysis": False,
                "scientific_status_changed": False,
                "artifact_sha256": receipt.get("artifact_sha256"),
                "reason_codes": ["xlsx_structural_intake_failed"],
                "error": str(exc),
            }
        routed = {
            "schema_version": PUBLIC_SCIENTIFIC_INTAKE_ROUTER_SCHEMA_VERSION,
            "adapter": "xlsx_structural_intake",
            **dict(result),
        }
        candidate_id = receipt.get("candidate_id")
        if (
            isinstance(candidate_id, str)
            and "mds2-2923" in candidate_id
            and isinstance(artifact_path, str)
            and Path(artifact_path).name == "Master_TrackList_Measurements.xlsx"
        ):
            try:
                routed["domain_mapping_proposal"] = propose_nist_2923_workbook_mapping(
                    result["workbook_structure"]
                )
            except (Nist2923MappingProposalError, KeyError) as exc:
                routed["domain_mapping_proposal"] = {
                    "status": "proposal_failed",
                    "accepted_for_analysis": False,
                    "scientific_status_changed": False,
                    "error": str(exc),
                }
        return routed
    return {
        "schema_version": PUBLIC_SCIENTIFIC_INTAKE_ROUTER_SCHEMA_VERSION,
        "decision": "requires_domain_scientific_intake",
        "accepted_for_analysis": False,
        "scientific_status_changed": False,
        "artifact_sha256": receipt.get("artifact_sha256"),
        "reason_codes": ["no_safe_structural_or_domain_intake_adapter_registered"],
        "artifact_suffix": suffix,
    }


__all__ = [
    "PUBLIC_SCIENTIFIC_INTAKE_ROUTER_SCHEMA_VERSION",
    "route_public_scientific_intake",
]
