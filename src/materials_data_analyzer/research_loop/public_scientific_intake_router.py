"""Conservative scientific-intake routing for automatically acquired public artifacts.

Only structural, non-semantic adapters are selected automatically here. A route can
inspect exact bytes and expose what domain mapping is still missing, but it cannot
promote an artifact to scientific evidence without a separately registered domain intake.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .delimited_structural_intake import (
    DelimitedStructuralIntakeError,
    structural_intake_acquired_delimited,
)
from .generic_semantic_lineage_proposal import (
    GenericSemanticLineageProposalError,
    build_generic_semantic_lineage_proposal,
)
from .in625_nist_2923_mapping_proposal import (
    Nist2923MappingProposalError,
    propose_nist_2923_workbook_mapping,
)
from .xlsx_structural_intake import (
    XlsxStructuralIntakeError,
    structural_intake_acquired_xlsx,
)

PUBLIC_SCIENTIFIC_INTAKE_ROUTER_SCHEMA_VERSION = "1.3"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _proposal_candidate_id(receipt: Mapping[str, Any]) -> str | None:
    candidate = receipt.get("candidate_id")
    if (
        isinstance(candidate, str)
        and candidate.strip()
        and candidate == candidate.strip()
    ):
        return candidate
    digest = receipt.get("artifact_sha256")
    if isinstance(digest, str) and _SHA_RE.fullmatch(digest):
        return "artifact-sha256:" + digest[:24]
    return None


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
    if suffix in {".csv", ".tsv", ".txt"}:
        try:
            result = structural_intake_acquired_delimited(
                receipt=receipt,
                package_directory=package_directory,
                evidence_gap=evidence_gap,
            )
        except (DelimitedStructuralIntakeError, OSError) as exc:
            return {
                "schema_version": PUBLIC_SCIENTIFIC_INTAKE_ROUTER_SCHEMA_VERSION,
                "decision": "structural_intake_failed",
                "accepted_for_analysis": False,
                "scientific_status_changed": False,
                "artifact_sha256": receipt.get("artifact_sha256"),
                "reason_codes": ["delimited_structural_intake_failed"],
                "error": str(exc),
            }
        routed_delimited: dict[str, Any] = {
            "schema_version": PUBLIC_SCIENTIFIC_INTAKE_ROUTER_SCHEMA_VERSION,
            "adapter": "delimited_structural_intake",
            **dict(result),
        }
        proposal_candidate = _proposal_candidate_id(receipt)
        if proposal_candidate is None:
            routed_delimited["generic_semantic_lineage_proposal"] = {
                "status": "proposal_not_prepared",
                "reason": "candidate_identifier_could_not_be_bound",
                "accepted_for_analysis": False,
                "scientific_status_changed": False,
            }
        else:
            try:
                routed_delimited["generic_semantic_lineage_proposal"] = (
                    build_generic_semantic_lineage_proposal(
                        candidate_id=proposal_candidate,
                        structure=result["delimited_structure"],
                    )
                )
            except (GenericSemanticLineageProposalError, KeyError) as exc:
                routed_delimited["generic_semantic_lineage_proposal"] = {
                    "status": "proposal_failed",
                    "error": str(exc),
                    "accepted_for_analysis": False,
                    "scientific_status_changed": False,
                }
        return routed_delimited
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
