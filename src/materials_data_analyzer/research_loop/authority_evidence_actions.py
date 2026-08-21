"""Autonomous, bounded actions for unresolved resolution-authority gaps.

The scientific compiler never performs network I/O here. Already-acquired UTF-8
metadata may be inspected automatically only when it contains explicit canonical
directives of the form::

    resolution-authority:<claim_kind>=<canonical JSON>

The whole directive line becomes the exact authority witness. Free-form prose,
filenames, and headers are never promoted heuristically. External search/acquisition
routes are emitted as SHA-bound requests for an upstream authorized executor.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError
from .resolution_authority_evidence import (
    ResolutionAuthorityEvidenceError,
    _normalize_authority_record,
    _required_claim_values,
    build_resolution_authority_packet,
)

AUTHORITY_EVIDENCE_ACTION_SCHEMA_VERSION = "1.0"
AUTHORITY_DIRECTIVE_PREFIX = "resolution-authority:"
LOCAL_ACTION = "inspect_acquired_metadata_artifact"
CONFLICT_ACTION = "resolve_authority_conflict"
EXTERNAL_ACTIONS = {
    "search_safe_archive_text_candidates",
    "acquire_declared_companion_metadata",
    "query_authoritative_repository_record",
    "request_human_source_owner_evidence",
}
AUTOMATED_EXTERNAL_ACTIONS = EXTERNAL_ACTIONS - {"request_human_source_owner_evidence"}
ALLOWED_CLAIMS = {
    "material_identity", "sample_identity", "property_semantics", "unit", "method",
    "instrument_model", "calibration", "process_signature", "standard_uncertainty",
    "specimen_identity", "acquisition_identity", "lab_identity",
    "material_lot_identity", "build_or_synthesis_identity", "process_run_identity",
}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CLAIM = re.compile(r"^[a-z][a-z0-9_]*$")


class AuthorityEvidenceActionError(ResearchLoopError):
    """Raised when a bounded authority-evidence action violates its contract."""


def _canon(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuthorityEvidenceActionError("content is not canonical-JSON serializable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AuthorityEvidenceActionError(f"{field} must be non-empty trimmed text")
    return value


def _integer(value: object, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AuthorityEvidenceActionError(f"{field} must be an integer >= {minimum}")
    return value


def _claims(value: object, field: str, *, empty_ok: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not empty_ok):
        raise AuthorityEvidenceActionError(f"{field} must be a {'non-empty ' if not empty_ok else ''}list")
    out: list[str] = []
    for item in value:
        claim = _text(item, field)
        if claim not in ALLOWED_CLAIMS or claim in out:
            raise AuthorityEvidenceActionError(f"{field} contains unsupported/duplicate claim")
        out.append(claim)
    return sorted(out)


def assess_resolution_authority_gaps(
    *,
    resolution_contract: Mapping[str, Any],
    authority_records: Sequence[Mapping[str, Any]] = (),
    authority_artifacts: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Return exact typed missing/conflicting gaps without requiring a complete packet."""
    artifacts = {} if authority_artifacts is None else dict(authority_artifacts)
    try:
        required = _required_claim_values(resolution_contract)
        normalized = [
            _normalize_authority_record(item, authority_artifacts=artifacts)
            for item in authority_records
        ]
    except ResolutionAuthorityEvidenceError as exc:
        raise AuthorityEvidenceActionError(str(exc)) from exc

    by_claim: dict[str, list[dict[str, Any]]] = {}
    for record in normalized:
        by_claim.setdefault(record["claim_kind"], []).append(record)
    unexpected = sorted(set(by_claim) - set(required))
    if unexpected:
        raise AuthorityEvidenceActionError(
            "authority records claim unresolved/non-required fields: " + ", ".join(unexpected)
        )

    expected = {claim: _digest(value) for claim, value in required.items()}
    gaps: list[dict[str, Any]] = []
    for claim in sorted(required):
        observed = sorted(
            {record["authorized_value_sha256"] for record in by_claim.get(claim, [])}
        )
        kind = None
        if not observed:
            kind = "missing_authority"
        elif observed != [expected[claim]]:
            kind = "conflicting_authority"
        if kind:
            gap = {
                "gap_kind": kind,
                "claim_kind": claim,
                "expected_value_sha256": expected[claim],
                "observed_value_sha256": observed,
                "resolution_packet_sha256": resolution_contract.get("resolution_packet_sha256"),
            }
            gap["authority_gap_sha256"] = _digest(gap)
            gap["authority_gap_id"] = "authority-gap:" + gap["authority_gap_sha256"][:24]
            gaps.append(gap)

    result = {
        "schema_version": AUTHORITY_EVIDENCE_ACTION_SCHEMA_VERSION,
        "candidate_id": resolution_contract.get("candidate_id"),
        "evidence_artifact_sha256": resolution_contract.get("evidence_artifact_sha256"),
        "semantic_resolution_sha256": resolution_contract.get("semantic_resolution_sha256"),
        "lineage_resolution_sha256": resolution_contract.get("lineage_resolution_sha256"),
        "resolution_packet_sha256": resolution_contract.get("resolution_packet_sha256"),
        "required_claim_value_sha256": expected,
        "authority_gaps": gaps,
        "missing_required_authority": [
            g["claim_kind"] for g in gaps if g["gap_kind"] == "missing_authority"
        ],
        "authority_conflicts": [
            g["claim_kind"] for g in gaps if g["gap_kind"] == "conflicting_authority"
        ],
        "all_positive_resolution_claims_source_authorized": not gaps,
        "assessment_is_scientific_support": False,
        "scientific_status_changed": False,
    }
    result["authority_gap_assessment_sha256"] = _digest(result)
    return result


def _directives(data: bytes) -> list[dict[str, Any]]:
    if not isinstance(data, bytes) or not data:
        raise AuthorityEvidenceActionError("authority metadata must be non-empty bytes")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthorityEvidenceActionError("automatic authority inspection requires UTF-8") from exc

    out: list[dict[str, Any]] = []
    offset = 0
    for raw_with_end in data.splitlines(keepends=True):
        raw = raw_with_end.rstrip(b"\r\n")
        start = offset
        offset += len(raw_with_end)
        if not raw:
            continue
        line = raw.decode("utf-8")
        if not line.startswith(AUTHORITY_DIRECTIVE_PREFIX):
            continue
        declaration = line[len(AUTHORITY_DIRECTIVE_PREFIX):]
        if "=" not in declaration:
            raise AuthorityEvidenceActionError("malformed resolution-authority directive")
        claim, payload = declaration.split("=", 1)
        if not _CLAIM.fullmatch(claim) or claim not in ALLOWED_CLAIMS:
            raise AuthorityEvidenceActionError(f"unsupported directive claim: {claim}")
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise AuthorityEvidenceActionError(f"directive {claim} must contain JSON") from exc
        if payload != _canon(value).decode("utf-8"):
            raise AuthorityEvidenceActionError(f"directive {claim} must use canonical JSON")
        item = {
            "claim_kind": claim,
            "authorized_value": value,
            "authorized_value_sha256": _digest(value),
            "byte_start": start,
            "byte_end": start + len(raw),
            "witness_text": line,
        }
        item["directive_sha256"] = _digest(item)
        out.append(item)
    return out


def build_local_text_authority_route(
    *,
    artifact_label: str,
    artifact_bytes: bytes,
    provenance_ref: str,
    authorization_ref: str,
) -> dict[str, Any]:
    """Describe exact already-acquired bytes; this function grants no source trust."""
    directives = _directives(artifact_bytes)
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
    route = {
        "schema_version": AUTHORITY_EVIDENCE_ACTION_SCHEMA_VERSION,
        "route_kind": "already_acquired_exact_text",
        "route_id": "authority-route:local:" + artifact_sha[:24],
        "action_class": LOCAL_ACTION,
        "generic_action_kind": "curate_dataset",
        "artifact_label": _text(artifact_label, "artifact_label"),
        "artifact_sha256": artifact_sha,
        "expected_bytes": len(artifact_bytes),
        "provenance_ref": _text(provenance_ref, "provenance_ref"),
        "authorization_ref": _text(authorization_ref, "authorization_ref"),
        "execution_mode": "local_exact_text_parser",
        "automated": True,
        "search_scope_claims": sorted(ALLOWED_CLAIMS),
        "declared_claims": sorted({d["claim_kind"] for d in directives}),
        "directives": directives,
        "provenance_quality_score": 100,
        "cost_units": 1,
        "network_performed_by_this_module": False,
        "semantic_inference_performed": False,
        "source_trust_granted_by_this_route": False,
        "scientific_support_granted_by_this_route": False,
    }
    route["authority_route_sha256"] = _digest(route)
    return route


def build_external_authority_route(
    *,
    route_id: str,
    action_class: str,
    resolvable_claims: Sequence[str],
    authorization_ref: str,
    provenance_ref: str,
    provenance_quality_score: int,
    expected_bytes: int,
    cost_units: int,
) -> dict[str, Any]:
    """Describe an authorized external path; no fetch/query is executed here."""
    action = _text(action_class, "action_class")
    if action not in EXTERNAL_ACTIONS:
        raise AuthorityEvidenceActionError("unsupported external action class")
    quality = _integer(provenance_quality_score, "provenance_quality_score")
    if quality > 100:
        raise AuthorityEvidenceActionError("provenance_quality_score must be <= 100")
    route = {
        "schema_version": AUTHORITY_EVIDENCE_ACTION_SCHEMA_VERSION,
        "route_kind": "authorized_external_route",
        "route_id": _text(route_id, "route_id"),
        "action_class": action,
        "generic_action_kind": (
            "acquire_data" if action in AUTOMATED_EXTERNAL_ACTIONS else "curate_dataset"
        ),
        "artifact_label": None,
        "artifact_sha256": None,
        "expected_bytes": _integer(expected_bytes, "expected_bytes"),
        "provenance_ref": _text(provenance_ref, "provenance_ref"),
        "authorization_ref": _text(authorization_ref, "authorization_ref"),
        "execution_mode": "external_authorized_executor",
        "automated": action in AUTOMATED_EXTERNAL_ACTIONS,
        "search_scope_claims": _claims(list(resolvable_claims), "resolvable_claims"),
        "declared_claims": [],
        "directives": [],
        "provenance_quality_score": quality,
        "cost_units": _integer(cost_units, "cost_units", 1),
        "network_performed_by_this_module": False,
        "semantic_inference_performed": False,
        "source_trust_granted_by_this_route": False,
        "scientific_support_granted_by_this_route": False,
    }
    route["authority_route_sha256"] = _digest(route)
    return route


def _verify_hashed(value: Mapping[str, Any], sha_field: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthorityEvidenceActionError(f"{label} must be an object")
    body = dict(value)
    sha = body.pop(sha_field, None)
    if not isinstance(sha, str) or not _SHA.fullmatch(sha) or sha != _digest(body):
        raise AuthorityEvidenceActionError(f"{label} SHA mismatch")
    return dict(value)


def _verify_route(route: Mapping[str, Any]) -> dict[str, Any]:
    verified = _verify_hashed(route, "authority_route_sha256", "authority route")
    if verified.get("network_performed_by_this_module") is not False:
        raise AuthorityEvidenceActionError("authority route cannot enable in-module network access")
    return verified


def _verify_request(request: Mapping[str, Any]) -> dict[str, Any]:
    verified = _verify_hashed(request, "action_request_sha256", "authority action request")
    body = {k: v for k, v in verified.items() if k not in {"action_request_sha256", "action_id"}}
    if verified.get("action_id") != "authority-action:" + _digest(body)[:24]:
        raise AuthorityEvidenceActionError("authority action ID mismatch")
    return verified


def _verify_results(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in results:
        result = _verify_hashed(raw, "action_result_sha256", "prior authority action result")
        body = {
            k: v for k, v in result.items()
            if k not in {"action_result_sha256", "action_result_id"}
        }
        if result.get("action_result_id") != "authority-action-result:" + _digest(body)[:24]:
            raise AuthorityEvidenceActionError("prior authority action result ID mismatch")
        request = result.get("action_request")
        if not isinstance(request, Mapping):
            raise AuthorityEvidenceActionError("prior result request is malformed")
        _verify_request(request)
        if result.get("action_request_sha256") != request.get("action_request_sha256"):
            raise AuthorityEvidenceActionError("prior result is bound to another request")
        out.append(dict(result))
    return out


def _request(
    assessment: Mapping[str, Any],
    *,
    route: Mapping[str, Any] | None,
    action_class: str,
    gaps: Sequence[Mapping[str, Any]],
    iteration: int,
    execution_mode: str,
    authorization_ref: str,
    rationale: str,
    expected_information_gain: int,
) -> dict[str, Any]:
    body = {
        "schema_version": AUTHORITY_EVIDENCE_ACTION_SCHEMA_VERSION,
        "iteration": _integer(iteration, "iteration", 1),
        "authority_gap_assessment_sha256": assessment["authority_gap_assessment_sha256"],
        "resolution_packet_sha256": assessment.get("resolution_packet_sha256"),
        "action_class": action_class,
        "generic_action_kind": route.get("generic_action_kind") if route else "curate_dataset",
        "target_claims": sorted({g["claim_kind"] for g in gaps}),
        "target_authority_gap_sha256": sorted({g["authority_gap_sha256"] for g in gaps}),
        "authority_route_sha256": route.get("authority_route_sha256") if route else None,
        "execution_mode": execution_mode,
        "authorization_ref": _text(authorization_ref, "authorization_ref"),
        "rationale": _text(rationale, "rationale"),
        "target_claim_count": len({g["claim_kind"] for g in gaps}),
        "expected_information_gain_claim_count": expected_information_gain,
        "provenance_quality_score": route.get("provenance_quality_score", 100) if route else 100,
        "expected_bytes": route.get("expected_bytes", 0) if route else 0,
        "cost_units": route.get("cost_units", 1) if route else 1,
        "network_performed_by_planner": False,
        "semantic_inference_authorized": False,
        "scientific_support_granted_by_request": False,
        "scientific_status_changed": False,
    }
    result = dict(body)
    result["action_id"] = "authority-action:" + _digest(body)[:24]
    result["action_request_sha256"] = _digest(result)
    return result


def plan_authority_evidence_action(
    *,
    assessment: Mapping[str, Any],
    routes: Sequence[Mapping[str, Any]],
    prior_results: Sequence[Mapping[str, Any]] = (),
    iteration: int = 1,
    remaining_cost_units: int | None = None,
    allow_human_fallback: bool = False,
) -> dict[str, Any] | None:
    """Rank claim-resolving routes by exact matches, provenance quality, cost, and bytes."""
    a = _verify_hashed(assessment, "authority_gap_assessment_sha256", "gap assessment")
    results = _verify_results(prior_results)
    gaps = a.get("authority_gaps")
    if not isinstance(gaps, list) or not gaps:
        return None
    conflicts = [g for g in gaps if g.get("gap_kind") == "conflicting_authority"]
    if conflicts:
        return _request(
            a, route=None, action_class=CONFLICT_ACTION, gaps=conflicts,
            iteration=iteration, execution_mode="external_authorized_conflict_resolution",
            authorization_ref="authority-conflict-boundary",
            rationale="Conflicting exact authority may not be silently preferred.",
            expected_information_gain=0,
        )

    attempted = {
        r["action_request"].get("authority_route_sha256")
        for r in results if r["action_request"].get("authority_route_sha256")
    }
    by_claim = {g["claim_kind"]: g for g in gaps}
    expected = a["required_claim_value_sha256"]
    candidates: list[tuple[tuple[Any, ...], dict[str, Any], list[dict[str, Any]], int]] = []
    for raw in routes:
        route = _verify_route(raw)
        if route["authority_route_sha256"] in attempted:
            continue
        scope = set(_claims(route.get("search_scope_claims"), "search_scope_claims"))
        target = sorted(scope & set(by_claim))
        if not target:
            continue
        if route["action_class"] == "request_human_source_owner_evidence" and not allow_human_fallback:
            continue
        if remaining_cost_units is not None and route["cost_units"] > remaining_cost_units:
            continue
        directives = route.get("directives", [])
        exact = {
            d.get("claim_kind")
            for d in directives if isinstance(d, Mapping)
            and d.get("claim_kind") in target
            and d.get("authorized_value_sha256") == expected.get(d.get("claim_kind"))
        }
        declared = set(route.get("declared_claims", [])) & set(target)
        score = (
            0 if route.get("automated") is True else 1,
            -len(exact), -len(declared), -len(target),
            -int(route["provenance_quality_score"]),
            int(route["cost_units"]), int(route["expected_bytes"]), str(route["route_id"]),
        )
        gain = len(exact) if route["execution_mode"] == "local_exact_text_parser" else len(target)
        candidates.append((score, route, [by_claim[c] for c in target], gain))

    automatic = [c for c in candidates if c[1].get("automated") is True]
    candidates = automatic or (candidates if allow_human_fallback else [])
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    _, route, target_gaps, gain = candidates[0]
    return _request(
        a, route=route, action_class=route["action_class"], gaps=target_gaps,
        iteration=iteration, execution_mode=route["execution_mode"],
        authorization_ref=route["authorization_ref"],
        rationale="Deterministic best bounded route for the current residual authority gaps.",
        expected_information_gain=gain,
    )


def execute_local_text_authority_action(
    *,
    action_request: Mapping[str, Any],
    route: Mapping[str, Any],
    artifact_bytes: bytes,
) -> dict[str, Any]:
    """Execute an exact already-acquired text inspection and bind its result."""
    request = _verify_request(action_request)
    verified_route = _verify_route(route)
    if request["action_class"] != LOCAL_ACTION or verified_route["action_class"] != LOCAL_ACTION:
        raise AuthorityEvidenceActionError("only local metadata inspection executes here")
    if request["authority_route_sha256"] != verified_route["authority_route_sha256"]:
        raise AuthorityEvidenceActionError("action request is bound to another route")
    if hashlib.sha256(artifact_bytes).hexdigest() != verified_route["artifact_sha256"]:
        raise AuthorityEvidenceActionError("local authority artifact bytes changed after planning")
    rebuilt = build_local_text_authority_route(
        artifact_label=verified_route["artifact_label"], artifact_bytes=artifact_bytes,
        provenance_ref=verified_route["provenance_ref"],
        authorization_ref=verified_route["authorization_ref"],
    )
    if rebuilt != verified_route:
        raise AuthorityEvidenceActionError("local authority route changed after planning")

    targets = set(request["target_claims"])
    inputs = [
        {
            "claim_kind": d["claim_kind"], "authorized_value": d["authorized_value"],
            "authority_artifact_sha256": verified_route["artifact_sha256"],
            "byte_start": d["byte_start"], "byte_end": d["byte_end"],
            "witness_text": d["witness_text"],
        }
        for d in verified_route["directives"] if d["claim_kind"] in targets
    ]
    try:
        normalized = [
            _normalize_authority_record(
                item, authority_artifacts={verified_route["artifact_sha256"]: artifact_bytes}
            )
            for item in inputs
        ]
    except ResolutionAuthorityEvidenceError as exc:
        raise AuthorityEvidenceActionError(str(exc)) from exc

    body = {
        "schema_version": AUTHORITY_EVIDENCE_ACTION_SCHEMA_VERSION,
        "action_request": request,
        "action_request_sha256": request["action_request_sha256"],
        "status": "completed",
        "authority_route_sha256": verified_route["authority_route_sha256"],
        "artifact_sha256": verified_route["artifact_sha256"],
        "artifact_provenance_ref": verified_route["provenance_ref"],
        "searched_claims": sorted(targets),
        "produced_authority_record_inputs": inputs,
        "produced_authority_record_sha256": sorted(
            r["authority_record_sha256"] for r in normalized
        ),
        "negative_claims": sorted(targets - {r["claim_kind"] for r in normalized}),
        "network_performed": False,
        "semantic_inference_performed": False,
        "result_is_scientific_support": False,
        "scientific_status_changed": False,
    }
    result = dict(body)
    result["action_result_id"] = "authority-action-result:" + _digest(body)[:24]
    result["action_result_sha256"] = _digest(result)
    return result


def _merge_records(
    existing: Sequence[Mapping[str, Any]], additions: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    out = [dict(r) for r in existing]
    seen = {_digest(r) for r in out}
    for raw in additions:
        record = dict(raw)
        if _digest(record) not in seen:
            out.append(record)
            seen.add(_digest(record))
    return out


def _loop_result(
    *,
    status: str,
    reason: str,
    assessment: Mapping[str, Any],
    packet: Mapping[str, Any] | None,
    records: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    new_count: int,
    spent: int,
    next_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out = {
        "schema_version": AUTHORITY_EVIDENCE_ACTION_SCHEMA_VERSION,
        "status": status,
        "stop_reason": reason,
        "authority_gap_assessment": dict(assessment),
        "authority_packet": None if packet is None else dict(packet),
        "authority_records": [dict(r) for r in records],
        "action_results": [dict(r) for r in results],
        "new_action_result_count": new_count,
        "next_action_request": None if next_request is None else dict(next_request),
        "spent_cost_units": spent,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    out["authority_evidence_loop_sha256"] = _digest(out)
    return out


def run_local_authority_evidence_loop(
    *,
    resolution_contract: Mapping[str, Any],
    authority_records: Sequence[Mapping[str, Any]] = (),
    authority_artifacts: Mapping[str, bytes] | None = None,
    companion_artifacts: Sequence[Mapping[str, Any]] = (),
    external_routes: Sequence[Mapping[str, Any]] = (),
    prior_action_results: Sequence[Mapping[str, Any]] = (),
    maximum_actions: int = 16,
    maximum_cost_units: int = 32,
    allow_human_fallback: bool = False,
) -> dict[str, Any]:
    """Run local evidence actions until ready or an explicit bounded stop is reached."""
    max_actions = _integer(maximum_actions, "maximum_actions", 1)
    max_cost = _integer(maximum_cost_units, "maximum_cost_units", 1)
    records = [dict(r) for r in authority_records]
    artifacts = {} if authority_artifacts is None else dict(authority_artifacts)
    history = _verify_results(prior_action_results)
    for prior in history:
        additions = prior.get("produced_authority_record_inputs")
        if not isinstance(additions, list):
            raise AuthorityEvidenceActionError("prior result record inputs are malformed")
        records = _merge_records(records, additions)

    local_routes: list[dict[str, Any]] = []
    for index, item in enumerate(companion_artifacts):
        if not isinstance(item, Mapping) or set(item) != {
            "artifact_label", "artifact_bytes", "provenance_ref", "authorization_ref"
        }:
            raise AuthorityEvidenceActionError(f"companion_artifacts[{index}] keys are invalid")
        data = item["artifact_bytes"]
        if not isinstance(data, bytes):
            raise AuthorityEvidenceActionError("companion artifact bytes must be bytes")
        route = build_local_text_authority_route(
            artifact_label=item["artifact_label"], artifact_bytes=data,
            provenance_ref=item["provenance_ref"], authorization_ref=item["authorization_ref"],
        )
        local_routes.append(route)
        artifacts[route["artifact_sha256"]] = data

    routes = [*local_routes, *[dict(r) for r in external_routes]]
    spent = sum(int(r["action_request"]["cost_units"]) for r in history)
    new: list[dict[str, Any]] = []
    slots = max_actions - len(history)
    if slots < 0:
        raise AuthorityEvidenceActionError("prior results exceed maximum_actions")

    for local_iteration in range(0, slots + 1):
        iteration = len(history) + local_iteration + 1
        assessment = assess_resolution_authority_gaps(
            resolution_contract=resolution_contract,
            authority_records=records,
            authority_artifacts=artifacts,
        )
        if assessment["all_positive_resolution_claims_source_authorized"]:
            try:
                packet = build_resolution_authority_packet(
                    resolution_contract=resolution_contract,
                    authority_records=records,
                    authority_artifacts=artifacts,
                )
            except ResolutionAuthorityEvidenceError as exc:
                raise AuthorityEvidenceActionError(str(exc)) from exc
            return _loop_result(
                status="completed", reason="all_required_authority_source_backed",
                assessment=assessment, packet=packet, records=records,
                results=[*history, *new], new_count=len(new), spent=spent,
            )
        if assessment["authority_conflicts"]:
            request = plan_authority_evidence_action(
                assessment=assessment, routes=routes, prior_results=[*history, *new],
                iteration=iteration, remaining_cost_units=max_cost - spent,
                allow_human_fallback=allow_human_fallback,
            )
            return _loop_result(
                status="stopped", reason="unresolved_authority_conflict",
                assessment=assessment, packet=None, records=records,
                results=[*history, *new], new_count=len(new), spent=spent,
                next_request=request,
            )
        if local_iteration == slots:
            return _loop_result(
                status="stopped", reason="policy_action_count_boundary",
                assessment=assessment, packet=None, records=records,
                results=[*history, *new], new_count=len(new), spent=spent,
            )
        remaining = max_cost - spent
        if remaining <= 0:
            return _loop_result(
                status="stopped", reason="policy_budget_boundary",
                assessment=assessment, packet=None, records=records,
                results=[*history, *new], new_count=len(new), spent=spent,
            )
        request = plan_authority_evidence_action(
            assessment=assessment, routes=routes, prior_results=[*history, *new],
            iteration=iteration, remaining_cost_units=remaining,
            allow_human_fallback=allow_human_fallback,
        )
        if request is None:
            return _loop_result(
                status="stopped", reason="no_authorized_route_remains",
                assessment=assessment, packet=None, records=records,
                results=[*history, *new], new_count=len(new), spent=spent,
            )
        route = next(
            (r for r in routes if r.get("authority_route_sha256") == request["authority_route_sha256"]),
            None,
        )
        if route is None:
            raise AuthorityEvidenceActionError("planned route disappeared")
        if request["execution_mode"] != "local_exact_text_parser":
            reason = (
                "human_review_boundary"
                if request["action_class"] == "request_human_source_owner_evidence"
                else "authorized_external_executor_required"
            )
            return _loop_result(
                status="action_required", reason=reason, assessment=assessment,
                packet=None, records=records, results=[*history, *new],
                new_count=len(new), spent=spent, next_request=request,
            )
        data = artifacts.get(route["artifact_sha256"])
        if not isinstance(data, bytes):
            raise AuthorityEvidenceActionError("planned local artifact bytes are unavailable")
        action_result = execute_local_text_authority_action(
            action_request=request, route=route, artifact_bytes=data
        )
        new.append(action_result)
        spent += int(request["cost_units"])
        records = _merge_records(records, action_result["produced_authority_record_inputs"])

    raise AuthorityEvidenceActionError("unreachable authority evidence loop state")


__all__ = [
    "AUTHORITY_DIRECTIVE_PREFIX",
    "AUTHORITY_EVIDENCE_ACTION_SCHEMA_VERSION",
    "AuthorityEvidenceActionError",
    "assess_resolution_authority_gaps",
    "build_external_authority_route",
    "build_local_text_authority_route",
    "execute_local_text_authority_action",
    "plan_authority_evidence_action",
    "run_local_authority_evidence_loop",
]
