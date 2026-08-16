"""Adapt the current hardened scientific-critic report to inquiry-planner inputs.

The critic's public contract uses ``target_reports`` containing
``methodological_alternatives`` and ``discriminating_actions``. The autonomous inquiry
planner intentionally consumes a smaller generic target/action projection. This adapter
makes that projection explicit and checksum-bound instead of silently guessing keys.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .autonomous_inquiry import AutonomousInquiryError, _canonical_sha256

CRITIC_INQUIRY_ADAPTER_SCHEMA_VERSION = "1.0"
CRITIC_INQUIRY_ADAPTER_POLICY_VERSION = "1.0"


def adapt_scientific_critic_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project one current critic report without creating or changing scientific content."""
    target_reports = report.get("target_reports")
    if not isinstance(target_reports, list):
        raise AutonomousInquiryError(
            "current scientific critic report must contain target_reports as a list"
        )

    targets: list[dict[str, Any]] = []
    for index, raw in enumerate(target_reports):
        if not isinstance(raw, Mapping):
            raise AutonomousInquiryError(f"target_reports[{index}] must be an object")
        target_id = raw.get("target_node_id")
        if not isinstance(target_id, str) or not target_id.strip():
            raise AutonomousInquiryError(
                f"target_reports[{index}].target_node_id must be non-empty text"
            )
        alternatives = raw.get("methodological_alternatives")
        actions = raw.get("discriminating_actions")
        findings = raw.get("critic_findings")
        if not isinstance(alternatives, list):
            raise AutonomousInquiryError(
                f"target_reports[{index}].methodological_alternatives must be a list"
            )
        if not isinstance(actions, list):
            raise AutonomousInquiryError(
                f"target_reports[{index}].discriminating_actions must be a list"
            )
        if not isinstance(findings, list):
            raise AutonomousInquiryError(
                f"target_reports[{index}].critic_findings must be a list"
            )
        if any(not isinstance(item, Mapping) for item in alternatives):
            raise AutonomousInquiryError("methodological alternatives must contain objects")
        if any(not isinstance(item, Mapping) for item in actions):
            raise AutonomousInquiryError("discriminating actions must contain objects")
        if any(not isinstance(item, Mapping) for item in findings):
            raise AutonomousInquiryError("critic findings must contain objects")

        targets.append(
            {
                "target_node_id": target_id.strip(),
                "alternatives": [dict(item) for item in alternatives],
                "proposed_actions": [dict(item) for item in actions],
                "critic_findings": [dict(item) for item in findings],
                "stop_recommendation": (
                    dict(raw["stop_recommendation"])
                    if isinstance(raw.get("stop_recommendation"), Mapping)
                    else None
                ),
            }
        )

    projection = {
        "schema_version": CRITIC_INQUIRY_ADAPTER_SCHEMA_VERSION,
        "policy_version": CRITIC_INQUIRY_ADAPTER_POLICY_VERSION,
        "source_critic_schema_version": report.get("schema_version"),
        "source_critic_policy_version": report.get("critic_policy_version"),
        "source_critic_hardening_policy_version": report.get(
            "critic_hardening_policy_version"
        ),
        "source_critic_sha256": _canonical_sha256(report),
        "targets": targets,
        "projection_boundary": {
            "scientific_content_created": False,
            "scientific_status_changed": False,
            "critic_action_availability_inferred": False,
            "execution_authority_granted": False,
        },
    }
    projection["projection_sha256"] = _canonical_sha256(projection)
    return projection


__all__ = [
    "CRITIC_INQUIRY_ADAPTER_POLICY_VERSION",
    "CRITIC_INQUIRY_ADAPTER_SCHEMA_VERSION",
    "adapt_scientific_critic_report",
]
