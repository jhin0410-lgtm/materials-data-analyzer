"""Bounded trusted-discovery -> acquisition -> intake -> analysis research loop.

The loop may automatically search only policy-allowlisted public repositories and may
acquire only checksum-bound artifacts accepted by the existing public-acquisition gate.
Acquisition never becomes scientific evidence until an explicit intake adapter accepts it.
Operational failures are never interpreted as contradictory scientific observations.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError
from .nist_pdr_acquisition import (
    NistPdrAcquisitionError,
    discover_nist_pdr_candidates,
    fetch_nist_pdr_metadata,
)
from .public_data_acquisition import (
    AUTO,
    DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
    DEFAULT_MAX_AUTO_BATCH_BYTES,
    PublicAcquisitionError,
    PublicFetcher,
    acquire_public_artifact,
    fetch_https_bytes,
    plan_public_acquisition_queue,
)
from .trusted_source_discovery import (
    TrustedSourceDiscoveryError,
    build_evidence_search_phrase,
    discover_nist_rmm,
    trusted_provider_authorization,
)

AUTONOMOUS_EVIDENCE_LOOP_SCHEMA_VERSION = "1.0"
AUTONOMOUS_EVIDENCE_LOOP_POLICY_VERSION = "1.1"

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
ACQUISITION_BLOCKED = "acquisition_blocked"

_TABLE_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet"}
_TEXT_EXTENSIONS = {".txt", ".md"}
_ARCHIVE_EXTENSIONS = {".zip"}
_IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}
_IMAGE_TERMS = {"image", "micrograph", "microscopy", "sem", "tem", "saed", "topography"}
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")


class AutonomousEvidenceLoopError(ResearchLoopError):
    """Raised when the autonomous evidence loop cannot preserve its trust boundary."""


IntakeHandler = Callable[..., Mapping[str, Any]]
AnalysisHandler = Callable[..., Mapping[str, Any]]
DiscoveryHandler = Callable[..., Mapping[str, Any]]


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AutonomousEvidenceLoopError("loop state must be canonical-JSON serializable") from exc
    return hashlib.sha256(payload).hexdigest()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AutonomousEvidenceLoopError(f"{field} must be a positive integer")
    return value


def _artifact_score(candidate: Mapping[str, Any], search_phrase: str) -> float:
    path = str(candidate.get("artifact_path", ""))
    suffix = Path(path).suffix.lower()
    query_tokens = _tokens(search_phrase)
    path_tokens = _tokens(path)
    token_score = len(query_tokens & path_tokens) / max(1, len(query_tokens))
    if suffix in _TABLE_EXTENSIONS:
        type_score = 0.8
    elif suffix in _TEXT_EXTENSIONS:
        type_score = 0.45
    elif suffix in _ARCHIVE_EXTENSIONS:
        type_score = 0.3
    elif suffix in _IMAGE_EXTENSIONS:
        type_score = 0.35 if query_tokens & _IMAGE_TERMS else -0.5
    else:
        type_score = 0.0
    name_bonus = 0.2 if any(term in path.lower() for term in ("measure", "data", "readme")) else 0.0
    return round(token_score + type_score + name_bonus, 8)


def select_nist_artifacts_for_gap(
    candidates: Sequence[Mapping[str, Any]],
    *,
    evidence_gap: object,
    max_files: int = 4,
) -> list[dict[str, Any]]:
    """Select a small, deterministic metadata/tabular-first subset for automatic intake."""
    _positive_int(max_files, "max_files")
    phrase = build_evidence_search_phrase(evidence_gap)
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        normalized = dict(candidate)
        score = _artifact_score(normalized, phrase)
        if score < 0:
            continue
        ranked.append((score, index, normalized))
    ranked.sort(key=lambda item: (-item[0], item[1], str(item[2].get("artifact_path", ""))))
    if not ranked:
        return []
    selected = [item[2] for item in ranked[:max_files]]
    return selected


def default_scientific_intake_handler(
    *,
    receipt: Mapping[str, Any],
    package_directory: str,
    evidence_gap: object,
) -> Mapping[str, Any]:
    """Fail closed when no domain-specific scientific intake adapter is registered."""
    return {
        "decision": "requires_domain_scientific_intake",
        "accepted_for_analysis": False,
        "artifact_sha256": receipt.get("artifact_sha256"),
        "package_directory": package_directory,
        "next_evidence_gap": evidence_gap,
        "scientific_status_changed": False,
        "reason_codes": ["no_domain_intake_adapter_registered"],
    }


def _acquire_nist_product_for_gap(
    *,
    product_id: str,
    evidence_gap: object,
    output_root: Path,
    fetcher: PublicFetcher,
    timeout_seconds: float,
    max_files: int,
    max_auto_bytes: int,
    max_total_auto_bytes: int,
) -> dict[str, Any]:
    metadata = fetch_nist_pdr_metadata(
        product_id,
        fetcher=fetcher,
        timeout_seconds=timeout_seconds,
    )
    discovered = discover_nist_pdr_candidates(
        metadata_bytes=metadata.body,
        product_id=product_id,
    )
    selected = select_nist_artifacts_for_gap(
        discovered,
        evidence_gap=evidence_gap,
        max_files=max_files,
    )
    if not selected:
        return {
            "product_id": product_id,
            "selected_candidate_count": 0,
            "queue": None,
            "receipts": [],
            "failures": [],
            "review_required": [],
            "blocked": [],
            "scientific_status_changed": False,
            "requires_scientific_intake": True,
            "reason_codes": ["no_artifact_matched_bounded_selection_policy"],
        }
    queue = plan_public_acquisition_queue(
        selected,
        max_auto_bytes=max_auto_bytes,
        max_total_auto_bytes=max_total_auto_bytes,
    )
    auto_ids = {item["candidate_id"] for item in queue["auto"]}
    receipts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, candidate in enumerate(selected):
        if candidate["candidate_id"] not in auto_ids:
            continue
        package_key = hashlib.sha256(candidate["candidate_id"].encode("utf-8")).hexdigest()[:16]
        package_dir = output_root / f"{index:02d}-{package_key}"
        try:
            receipt = acquire_public_artifact(
                candidate=candidate,
                metadata_bytes=metadata.body,
                output_dir=package_dir,
                fetcher=fetcher,
                timeout_seconds=timeout_seconds,
                max_auto_bytes=max_auto_bytes,
            )
        except PublicAcquisitionError as exc:
            failures.append({"candidate_id": candidate["candidate_id"], "error": str(exc)})
            continue
        receipts.append({**receipt, "package_directory": package_dir.as_posix()})
    return {
        "product_id": product_id,
        "metadata_sha256": hashlib.sha256(metadata.body).hexdigest(),
        "selected_candidate_count": len(selected),
        "selected_candidate_ids": [item["candidate_id"] for item in selected],
        "queue": queue,
        "receipts": receipts,
        "failures": failures,
        "review_required": queue["review_required"],
        "blocked": queue["blocked"],
        "scientific_status_changed": False,
        "requires_scientific_intake": True,
    }


def _validate_analysis_result(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    outcome = result.get("scientific_outcome")
    if outcome not in {SUPPORTED, CONTRADICTED, INSUFFICIENT_EVIDENCE}:
        raise AutonomousEvidenceLoopError(
            "analysis_handler scientific_outcome must be supported, contradicted, or insufficient_evidence"
        )
    resolved = result.get("evidence_gap_resolved")
    if not isinstance(resolved, bool):
        raise AutonomousEvidenceLoopError("analysis_handler evidence_gap_resolved must be boolean")
    if outcome in {SUPPORTED, CONTRADICTED} and not resolved:
        raise AutonomousEvidenceLoopError(
            "supported/contradicted analysis must explicitly resolve the evidence gap"
        )
    return result


def run_autonomous_evidence_loop(
    evidence_gap: object,
    *,
    output_root: str | Path,
    discovery_handler: DiscoveryHandler = discover_nist_rmm,
    fetcher: PublicFetcher = fetch_https_bytes,
    intake_handler: IntakeHandler = default_scientific_intake_handler,
    analysis_handler: AnalysisHandler | None = None,
    max_iterations: int = 3,
    max_records_per_iteration: int = 3,
    max_files_per_product: int = 4,
    max_auto_bytes: int = DEFAULT_MAX_AUTO_ARTIFACT_BYTES,
    max_total_auto_bytes: int = DEFAULT_MAX_AUTO_BATCH_BYTES,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Run a bounded trusted external-evidence loop with exception-only human review.

    The generic default stops at scientific intake. A domain adapter must explicitly accept
    acquired bytes before analysis can run. This is intentional: catalog/download success is
    provenance evidence, not a scientific measurement.
    """
    max_iterations = _positive_int(max_iterations, "max_iterations")
    max_records_per_iteration = _positive_int(max_records_per_iteration, "max_records_per_iteration")
    max_files_per_product = _positive_int(max_files_per_product, "max_files_per_product")
    root = Path(output_root)
    provider_auth = trusted_provider_authorization("nist_rmm")
    if provider_auth["decision"] != AUTO or provider_auth["human_approval_required"]:
        raise AutonomousEvidenceLoopError("NIST RMM provider is not policy-authorized")

    current_gap = evidence_gap
    history: list[dict[str, Any]] = []
    seen_scientific_fingerprints: set[str] = set()
    review_queue: list[dict[str, Any]] = []
    operational_failures: list[dict[str, Any]] = []

    for iteration in range(1, max_iterations + 1):
        iteration_record: dict[str, Any] = {
            "iteration": iteration,
            "evidence_gap_sha256": _canonical_sha256(current_gap),
            "scientific_status_changed": False,
        }
        try:
            discovery = dict(
                discovery_handler(
                    current_gap,
                    fetcher=fetcher,
                    timeout_seconds=timeout_seconds,
                )
            )
        except (TrustedSourceDiscoveryError, PublicAcquisitionError) as exc:
            operational_failures.append(
                {"iteration": iteration, "stage": "discovery", "error": str(exc)}
            )
            iteration_record["operational_failure"] = "discovery_failed"
            history.append(iteration_record)
            break

        candidates_raw = discovery.get("candidates", [])
        if not isinstance(candidates_raw, list):
            raise AutonomousEvidenceLoopError("discovery candidates must be a list")
        candidates = [item for item in candidates_raw if isinstance(item, Mapping)]
        iteration_record["discovery"] = {
            "query_sha256": discovery.get("query_sha256"),
            "response_sha256": discovery.get("response_sha256"),
            "candidate_count": len(candidates),
        }
        actionable = [
            item
            for item in candidates
            if item.get("discovery_decision") == AUTO
            and item.get("acquisition_metadata_resolvable") is True
            and isinstance(item.get("product_id"), str)
        ][:max_records_per_iteration]
        review_queue.extend(
            {
                "iteration": iteration,
                "stage": "discovery",
                "candidate_id": item.get("candidate_id"),
                "reason_codes": item.get("discovery_reason_codes", []),
            }
            for item in candidates
            if item.get("discovery_decision") != AUTO
        )
        if not actionable:
            iteration_record["stop_reason"] = "no_policy_actionable_discovery_candidates"
            history.append(iteration_record)
            break

        accepted_intakes: list[dict[str, Any]] = []
        intake_results: list[dict[str, Any]] = []
        acquisition_summaries: list[dict[str, Any]] = []
        for candidate_index, candidate in enumerate(actionable):
            product_id = str(candidate["product_id"])
            product_root = root / f"iteration-{iteration:02d}" / f"record-{candidate_index:02d}-{product_id}"
            try:
                acquisition = _acquire_nist_product_for_gap(
                    product_id=product_id,
                    evidence_gap=current_gap,
                    output_root=product_root,
                    fetcher=fetcher,
                    timeout_seconds=timeout_seconds,
                    max_files=max_files_per_product,
                    max_auto_bytes=max_auto_bytes,
                    max_total_auto_bytes=max_total_auto_bytes,
                )
            except (NistPdrAcquisitionError, PublicAcquisitionError) as exc:
                operational_failures.append(
                    {
                        "iteration": iteration,
                        "stage": "acquisition",
                        "product_id": product_id,
                        "error": str(exc),
                    }
                )
                continue
            acquisition_summaries.append(
                {
                    "product_id": product_id,
                    "selected_candidate_count": acquisition["selected_candidate_count"],
                    "receipt_count": len(acquisition["receipts"]),
                    "failure_count": len(acquisition["failures"]),
                }
            )
            review_queue.extend(
                {
                    "iteration": iteration,
                    "stage": "acquisition",
                    "product_id": product_id,
                    **item,
                }
                for item in acquisition["review_required"]
            )
            for receipt in acquisition["receipts"]:
                intake = dict(
                    intake_handler(
                        receipt=receipt,
                        package_directory=receipt["package_directory"],
                        evidence_gap=current_gap,
                    )
                )
                if intake.get("scientific_status_changed") not in {False, True}:
                    raise AutonomousEvidenceLoopError(
                        "intake_handler scientific_status_changed must be boolean"
                    )
                accepted = intake.get("accepted_for_analysis")
                if accepted not in {False, True}:
                    raise AutonomousEvidenceLoopError(
                        "intake_handler accepted_for_analysis must be boolean"
                    )
                intake_results.append(
                    {
                        "product_id": product_id,
                        "candidate_id": receipt.get("candidate_id"),
                        "artifact_path": receipt.get("artifact_path"),
                        "artifact_sha256": receipt.get("artifact_sha256"),
                        "accepted_for_analysis": accepted,
                        "intake": intake,
                    }
                )
                if accepted is True:
                    accepted_intakes.append(intake)
        iteration_record["acquisition"] = acquisition_summaries
        iteration_record["intake_results"] = intake_results
        iteration_record["accepted_intake_count"] = len(accepted_intakes)

        if not accepted_intakes:
            iteration_record["stop_reason"] = "scientific_intake_not_satisfied"
            history.append(iteration_record)
            break
        scientific_fingerprint = _canonical_sha256(accepted_intakes)
        if scientific_fingerprint in seen_scientific_fingerprints:
            iteration_record["stop_reason"] = "stagnation_no_new_scientific_evidence"
            history.append(iteration_record)
            break
        seen_scientific_fingerprints.add(scientific_fingerprint)
        iteration_record["scientific_status_changed"] = True

        if analysis_handler is None:
            iteration_record["stop_reason"] = "analysis_adapter_not_registered"
            history.append(iteration_record)
            break
        analysis = _validate_analysis_result(
            analysis_handler(
                accepted_intakes=accepted_intakes,
                evidence_gap=current_gap,
                iteration=iteration,
            )
        )
        iteration_record["analysis"] = analysis
        history.append(iteration_record)
        if analysis["scientific_outcome"] in {SUPPORTED, CONTRADICTED}:
            return {
                "schema_version": AUTONOMOUS_EVIDENCE_LOOP_SCHEMA_VERSION,
                "policy_version": AUTONOMOUS_EVIDENCE_LOOP_POLICY_VERSION,
                "terminal_status": analysis["scientific_outcome"],
                "stop_reason": "evidence_gap_resolved_by_domain_analysis",
                "iterations_completed": iteration,
                "history": history,
                "review_queue": review_queue,
                "operational_failures": operational_failures,
                "network_failure_is_scientific_negative_evidence": False,
                "physical_experiment_execution_authorized": False,
            }
        next_gap = analysis.get("next_evidence_gap")
        if next_gap is None:
            return {
                "schema_version": AUTONOMOUS_EVIDENCE_LOOP_SCHEMA_VERSION,
                "policy_version": AUTONOMOUS_EVIDENCE_LOOP_POLICY_VERSION,
                "terminal_status": INSUFFICIENT_EVIDENCE,
                "stop_reason": "analysis_reports_insufficient_evidence_without_next_gap",
                "iterations_completed": iteration,
                "history": history,
                "review_queue": review_queue,
                "operational_failures": operational_failures,
                "network_failure_is_scientific_negative_evidence": False,
                "physical_experiment_execution_authorized": False,
            }
        current_gap = next_gap

    last_reason = history[-1].get("stop_reason") if history else "no_iteration_completed"
    terminal = ACQUISITION_BLOCKED if operational_failures and not seen_scientific_fingerprints else INSUFFICIENT_EVIDENCE
    return {
        "schema_version": AUTONOMOUS_EVIDENCE_LOOP_SCHEMA_VERSION,
        "policy_version": AUTONOMOUS_EVIDENCE_LOOP_POLICY_VERSION,
        "terminal_status": terminal,
        "stop_reason": last_reason or "max_iterations_reached",
        "iterations_completed": len(history),
        "history": history,
        "review_queue": review_queue,
        "operational_failures": operational_failures,
        "network_failure_is_scientific_negative_evidence": False,
        "physical_experiment_execution_authorized": False,
    }


__all__ = [
    "ACQUISITION_BLOCKED",
    "AUTONOMOUS_EVIDENCE_LOOP_POLICY_VERSION",
    "AUTONOMOUS_EVIDENCE_LOOP_SCHEMA_VERSION",
    "AutonomousEvidenceLoopError",
    "CONTRADICTED",
    "INSUFFICIENT_EVIDENCE",
    "SUPPORTED",
    "default_scientific_intake_handler",
    "run_autonomous_evidence_loop",
    "select_nist_artifacts_for_gap",
]
