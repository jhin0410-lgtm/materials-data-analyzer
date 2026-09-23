"""Authenticated IN625 mds2-2923 spot-size sensitivity action.

This is a narrow domain action for the first Autonomous Research Scientist competency
benchmark.  It consumes only externally authenticated EvidencePackets from the exact
mds2-2923 AMMT 195 W / 800 mm/s subset and computes descriptive within-source
spot-diameter sensitivity.  It does not create empirical measurements, infer calibrated
laser power, establish causality, or authorize cross-source comparison.

The action boundary is deliberately split:
1. compile a request from the planner-selected sensitivity design and authenticated inputs;
2. require an externally supplied trust-root SHA for that exact request;
3. execute the deterministic local analysis;
4. independently recompute the result before it can influence benchmark re-planning.
"""

from __future__ import annotations

import copy
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .comparability_engine import AuthenticatedEvidenceInput
from .evidence_expectation_trust import validate_authenticated_evidence_packet
from .evidence_packet import canonical_sha256

ACTION_TYPE = "in625_mds2_spot_size_sensitivity"
ACTION_VERSION = "1.0"
ACTION_SCHEMA_VERSION = "1.0"


class In625SpotSizeSensitivityError(ValueError):
    """Raised when the bounded sensitivity action would exceed authenticated evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625SpotSizeSensitivityError(message)


def _sha(value: object, field: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{field} must be lowercase SHA-256",
    )
    return value


def _verify_self_hash(value: Mapping[str, Any], field: str) -> str:
    snapshot = copy.deepcopy(dict(value))
    digest = _sha(snapshot.pop(field, None), field)
    _require(canonical_sha256(snapshot) == digest, f"{field} self-hash mismatch")
    return digest


def _attribute(packet: Mapping[str, Any], context: str, name: str) -> object:
    contexts = packet.get("contexts")
    _require(isinstance(contexts, Mapping), "EvidencePacket contexts are missing")
    section = contexts.get(context)
    _require(isinstance(section, Mapping), f"EvidencePacket context {context!r} is missing")
    attributes = section.get("attributes")
    _require(isinstance(attributes, list), f"EvidencePacket context {context!r} attributes are missing")
    matches = [
        item
        for item in attributes
        if isinstance(item, Mapping) and item.get("name") == name
    ]
    _require(len(matches) == 1, f"EvidencePacket attribute {context}.{name} must occur exactly once")
    return matches[0].get("value")


def _identity(packet: Mapping[str, Any], namespace: str) -> str:
    subject = packet.get("subject")
    _require(isinstance(subject, Mapping), "EvidencePacket subject is missing")
    identities = subject.get("identities")
    _require(isinstance(identities, list), "EvidencePacket subject identities are missing")
    matches = [
        item.get("value")
        for item in identities
        if isinstance(item, Mapping) and item.get("namespace") == namespace
    ]
    _require(
        len(matches) == 1 and isinstance(matches[0], str) and bool(matches[0]),
        f"EvidencePacket identity {namespace!r} must occur exactly once",
    )
    return str(matches[0])


def _result(packet: Mapping[str, Any], kind: str) -> float:
    results = packet.get("results")
    _require(isinstance(results, list), "EvidencePacket results are missing")
    matches = [
        item
        for item in results
        if isinstance(item, Mapping) and item.get("result_kind") == kind
    ]
    _require(len(matches) == 1, f"EvidencePacket result {kind!r} must occur exactly once")
    item = matches[0]
    value = item.get("value")
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"EvidencePacket result {kind!r} must be finite numeric",
    )
    _require(item.get("unit") == "um", f"EvidencePacket result {kind!r} must use um")
    return float(value)


def _mean(values: Sequence[float]) -> float:
    _require(bool(values), "mean requires at least one value")
    return sum(values) / len(values)


def _sample_sd(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    center = _mean(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / (len(values) - 1))


def _linear_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    _require(len(xs) == len(ys) and len(xs) >= 2, "slope requires paired values")
    xbar = _mean(xs)
    ybar = _mean(ys)
    denominator = sum((value - xbar) ** 2 for value in xs)
    _require(denominator > 0.0, "slope requires non-constant x")
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys, strict=True)) / denominator


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    _require(len(xs) == len(ys) and len(xs) >= 2, "correlation requires paired values")
    xbar = _mean(xs)
    ybar = _mean(ys)
    dx = [value - xbar for value in xs]
    dy = [value - ybar for value in ys]
    denominator = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    _require(denominator > 0.0, "correlation requires non-constant paired values")
    return sum(x * y for x, y in zip(dx, dy, strict=True)) / denominator


def _sign(value: float, tolerance: float = 1e-12) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def _authenticate_inputs(
    evidence_inputs: Sequence[AuthenticatedEvidenceInput],
) -> list[dict[str, Any]]:
    _require(
        not isinstance(evidence_inputs, (str, bytes)) and len(evidence_inputs) == 18,
        "spot-size sensitivity requires exactly 18 authenticated mds2 rows",
    )
    packets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_tracks: set[str] = set()
    for index, item in enumerate(evidence_inputs):
        _require(
            isinstance(item, AuthenticatedEvidenceInput),
            f"evidence_inputs[{index}] must be AuthenticatedEvidenceInput",
        )
        packet = validate_authenticated_evidence_packet(
            item.packet,
            artifacts=item.artifacts,
            expected=item.expected,
            trusted_expectation_sha256=item.trusted_expectation_sha256,
        )
        provider = packet.get("provider")
        authority = packet.get("authority")
        calibration = packet.get("calibration")
        _require(isinstance(provider, Mapping), "EvidencePacket provider is missing")
        _require(
            provider.get("provider_id") == "nist-mds2-2923-row-provider",
            "spot-size sensitivity accepts only the mds2 row provider",
        )
        _require(isinstance(authority, Mapping), "EvidencePacket authority is missing")
        _require(
            authority.get("empirical_evidence_created") is True
            and authority.get("row_level_measurement_authority") is True,
            "spot-size sensitivity requires authenticated row-level empirical authority",
        )
        _require(isinstance(calibration, Mapping), "EvidencePacket calibration is missing")
        _require(
            calibration.get("status") == "unknown",
            "mds2 calibrated-power status must remain unknown",
        )
        _require(_identity(packet, "material") == "IN625", "material identity must be IN625")
        track = _identity(packet, "mds2_physical_track_id")
        evidence_id = packet.get("evidence_id")
        _require(isinstance(evidence_id, str) and bool(evidence_id), "EvidencePacket evidence_id is missing")
        _require(evidence_id not in seen_ids, "duplicate evidence_id is not allowed")
        _require(track not in seen_tracks, "duplicate physical track is not independent row evidence")
        seen_ids.add(evidence_id)
        seen_tracks.add(track)
        _require(_attribute(packet, "process", "machine") == "AMMT", "machine must be AMMT")
        _require(
            float(_attribute(packet, "process", "laser_power_machine_setting")) == 195.0,
            "laser power must remain the 195 W machine setting",
        )
        _require(
            float(_attribute(packet, "process", "scan_speed_machine_setting")) == 800.0,
            "scan speed must remain the 800 mm/s machine setting",
        )
        packets.append(packet)

    spot_levels = sorted(
        {float(_attribute(packet, "process", "spot_diameter_D4sigma")) for packet in packets}
    )
    _require(
        len(spot_levels) == 7 and spot_levels[0] == 50.0 and spot_levels[-1] == 256.0,
        "authenticated mds2 spot-size support must preserve seven levels from 50 to 256 um",
    )
    return packets


def _iteration_snapshot(
    iteration: Mapping[str, Any],
    *,
    trusted_iteration_sha256: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    trusted = _sha(trusted_iteration_sha256, "trusted_iteration_sha256")
    snapshot = copy.deepcopy(dict(iteration))
    _require(
        canonical_sha256(snapshot) == trusted,
        "benchmark iteration does not match external trust-root SHA-256",
    )
    embedded = _verify_self_hash(snapshot, "iteration_sha256")
    plan = snapshot.get("plan")
    _require(isinstance(plan, Mapping), "benchmark iteration plan is missing")
    selected = plan.get("selected_next_action")
    _require(isinstance(selected, Mapping), "benchmark iteration has no selected action")
    _require(
        selected.get("action_class") == "sensitivity_analysis",
        "spot-size action may only instantiate a planner-selected sensitivity analysis",
    )
    required = selected.get("required_evidence")
    _require(isinstance(required, list) and bool(required), "selected sensitivity action lacks evidence requirement")
    joined = " ".join(str(item) for item in required).casefold()
    _require(
        "spot" in joined and ("protocol" in joined or "measurement" in joined),
        "selected sensitivity action is not the protocol/spot-size blocker",
    )
    return snapshot, embedded, dict(selected)


def build_in625_spot_size_sensitivity_request(
    iteration: Mapping[str, Any],
    *,
    trusted_iteration_sha256: str,
    evidence_inputs: Sequence[AuthenticatedEvidenceInput],
) -> dict[str, Any]:
    """Compile one typed local-analysis request without authorizing execution."""

    _snapshot, iteration_sha, selected = _iteration_snapshot(
        iteration,
        trusted_iteration_sha256=trusted_iteration_sha256,
    )
    packets = _authenticate_inputs(evidence_inputs)
    request: dict[str, Any] = {
        "schema_version": ACTION_SCHEMA_VERSION,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "source_iteration_sha256": iteration_sha,
        "selected_planner_action": {
            "action_id": selected.get("action_id"),
            "action_class": selected.get("action_class"),
            "execution_mode": selected.get("execution_mode"),
        },
        "evidence_packet_sha256s": sorted(str(packet["packet_sha256"]) for packet in packets),
        "analysis_contract": {
            "population": "18 authenticated mds2-2923 IN625 AMMT physical tracks",
            "fixed_machine_setting_power_w": 195.0,
            "fixed_machine_setting_scan_speed_mm_s": 800.0,
            "independent_variable": "source-native spot_diameter_D4sigma",
            "responses": ["melt_pool_width", "melt_pool_depth"],
            "statistics": [
                "spot-level count/mean/sample-SD",
                "row-level descriptive linear slope",
                "row-level Pearson correlation",
                "leave-one-spot-level-out slope-sign stability",
            ],
            "inferential_p_values_computed": False,
        },
        "authority_boundary": {
            "execution_authorized": False,
            "empirical_measurements_created": False,
            "causal_effect_established": False,
            "calibrated_power_inferred": False,
            "protocol_equivalence_established": False,
            "cross_source_comparison_authorized": False,
            "scientific_status_promoted": False,
        },
    }
    request["request_sha256"] = canonical_sha256(request)
    return request


def authorize_in625_spot_size_sensitivity_request(
    request: Mapping[str, Any],
    *,
    trusted_request_sha256: str,
) -> dict[str, Any]:
    """Authorize only an externally pinned exact request.

    The trusted digest is deliberately supplied by the caller and is never generated inside
    this authorization function.
    """

    trusted = _sha(trusted_request_sha256, "trusted_request_sha256")
    snapshot = copy.deepcopy(dict(request))
    _require(
        canonical_sha256(snapshot) == trusted,
        "spot-size request does not match external authorization trust-root SHA-256",
    )
    request_sha = _verify_self_hash(snapshot, "request_sha256")
    _require(
        snapshot.get("action_type") == ACTION_TYPE
        and snapshot.get("action_version") == ACTION_VERSION,
        "unsupported spot-size action request",
    )
    boundary = snapshot.get("authority_boundary")
    _require(isinstance(boundary, Mapping), "request authority boundary is missing")
    _require(
        boundary.get("execution_authorized") is False
        and boundary.get("scientific_status_promoted") is False,
        "request may not self-authorize or promote scientific status",
    )
    receipt: dict[str, Any] = {
        "schema_version": ACTION_SCHEMA_VERSION,
        "authorization_type": "explicit_external_request_authorization",
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_sha256": request_sha,
        "trusted_request_sha256": trusted,
        "execution_authorized": True,
        "network_access_authorized": False,
        "physical_experiment_authorized": False,
        "scientific_status_promotion_authorized": False,
    }
    receipt["authorization_sha256"] = canonical_sha256(receipt)
    return receipt


def _analysis_from_packets(packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    grouped: dict[float, dict[str, list[float]]] = defaultdict(
        lambda: {"width": [], "depth": []}
    )
    for packet in packets:
        spot = float(_attribute(packet, "process", "spot_diameter_D4sigma"))
        width = _result(packet, "melt_pool_width")
        depth = _result(packet, "melt_pool_depth")
        grouped[spot]["width"].append(width)
        grouped[spot]["depth"].append(depth)
        rows.append(
            {
                "evidence_id": packet["evidence_id"],
                "physical_track_id": _identity(packet, "mds2_physical_track_id"),
                "spot_diameter_um": spot,
                "width_um": width,
                "depth_um": depth,
            }
        )

    rows.sort(key=lambda item: (item["spot_diameter_um"], item["physical_track_id"]))
    spot_levels = sorted(grouped)
    level_summary = []
    for spot in spot_levels:
        widths = grouped[spot]["width"]
        depths = grouped[spot]["depth"]
        level_summary.append(
            {
                "spot_diameter_um": spot,
                "track_count": len(widths),
                "width_mean_um": _mean(widths),
                "width_sample_sd_um": _sample_sd(widths),
                "depth_mean_um": _mean(depths),
                "depth_sample_sd_um": _sample_sd(depths),
            }
        )

    xs = [float(item["spot_diameter_um"]) for item in rows]
    widths = [float(item["width_um"]) for item in rows]
    depths = [float(item["depth_um"]) for item in rows]
    width_slope = _linear_slope(xs, widths)
    depth_slope = _linear_slope(xs, depths)

    width_loo: list[dict[str, Any]] = []
    depth_loo: list[dict[str, Any]] = []
    for excluded in spot_levels:
        kept = [item for item in rows if item["spot_diameter_um"] != excluded]
        kept_x = [float(item["spot_diameter_um"]) for item in kept]
        kept_width = [float(item["width_um"]) for item in kept]
        kept_depth = [float(item["depth_um"]) for item in kept]
        width_loo.append(
            {
                "excluded_spot_diameter_um": excluded,
                "slope_um_per_um": _linear_slope(kept_x, kept_width),
            }
        )
        depth_loo.append(
            {
                "excluded_spot_diameter_um": excluded,
                "slope_um_per_um": _linear_slope(kept_x, kept_depth),
            }
        )

    width_sign = _sign(width_slope)
    depth_sign = _sign(depth_slope)
    return {
        "row_count": len(rows),
        "physical_track_count": len({item["physical_track_id"] for item in rows}),
        "spot_level_count": len(spot_levels),
        "spot_diameter_range_um": [min(spot_levels), max(spot_levels)],
        "spot_level_summary": level_summary,
        "width": {
            "observed_range_um": [min(widths), max(widths)],
            "linear_slope_um_per_um_spot": width_slope,
            "pearson_r_spot_vs_width": _pearson(xs, widths),
            "leave_one_spot_level_out": width_loo,
            "slope_sign": width_sign,
            "leave_one_level_sign_stable": all(
                _sign(item["slope_um_per_um"]) == width_sign for item in width_loo
            ),
        },
        "depth": {
            "observed_range_um": [min(depths), max(depths)],
            "linear_slope_um_per_um_spot": depth_slope,
            "pearson_r_spot_vs_depth": _pearson(xs, depths),
            "leave_one_spot_level_out": depth_loo,
            "slope_sign": depth_sign,
            "leave_one_level_sign_stable": all(
                _sign(item["slope_um_per_um"]) == depth_sign for item in depth_loo
            ),
        },
    }


def execute_in625_spot_size_sensitivity(
    request: Mapping[str, Any],
    *,
    authorization_receipt: Mapping[str, Any],
    trusted_authorization_sha256: str,
    evidence_inputs: Sequence[AuthenticatedEvidenceInput],
) -> dict[str, Any]:
    """Execute only after an externally pinned authorization receipt is authenticated."""

    request_snapshot = copy.deepcopy(dict(request))
    request_sha = _verify_self_hash(request_snapshot, "request_sha256")
    receipt = copy.deepcopy(dict(authorization_receipt))
    trusted_authorization = _sha(
        trusted_authorization_sha256,
        "trusted_authorization_sha256",
    )
    _require(
        canonical_sha256(receipt) == trusted_authorization,
        "authorization receipt does not match external trust-root SHA-256",
    )
    authorization_sha = _verify_self_hash(receipt, "authorization_sha256")
    _require(
        receipt.get("action_type") == ACTION_TYPE
        and receipt.get("action_version") == ACTION_VERSION
        and receipt.get("request_sha256") == request_sha
        and receipt.get("trusted_request_sha256") == canonical_sha256(request),
        "authorization receipt does not bind the exact request",
    )
    _require(receipt.get("execution_authorized") is True, "request is not authorized")
    _require(
        receipt.get("network_access_authorized") is False
        and receipt.get("physical_experiment_authorized") is False
        and receipt.get("scientific_status_promotion_authorized") is False,
        "spot-size authorization widened beyond local descriptive analysis",
    )
    packets = _authenticate_inputs(evidence_inputs)
    packet_shas = sorted(str(packet["packet_sha256"]) for packet in packets)
    _require(
        request_snapshot.get("evidence_packet_sha256s") == packet_shas,
        "request evidence ancestry differs from authenticated packets",
    )

    result: dict[str, Any] = {
        "schema_version": ACTION_SCHEMA_VERSION,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_sha256": request_sha,
        "authorization_sha256": authorization_sha,
        "evidence_packet_sha256s": packet_shas,
        "analysis": _analysis_from_packets(packets),
        "scientific_interpretation": {
            "observation": (
                "Within the authenticated mds2 AMMT 195 W / 800 mm/s subset, spot diameter "
                "is explicitly non-constant and melt-pool geometry is reported across seven "
                "source-native spot levels."
            ),
            "protocol_spot_context_can_be_ignored": False,
            "causal_spot_size_effect_established": False,
            "calibrated_power_relation_established": False,
            "protocol_equivalence_established": False,
            "cross_source_numerical_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "scientific_status_promoted": False,
        },
        "authority_boundary": {
            "new_empirical_measurements_created": False,
            "source_rows_modified": False,
            "interpolation_performed": False,
            "outlier_exclusion_performed": False,
            "inferential_p_values_computed": False,
            "causal_claim_created": False,
            "cross_source_authority_created": False,
            "scientific_status_promoted": False,
        },
    }
    result["result_sha256"] = canonical_sha256(result)
    return result


def verify_in625_spot_size_sensitivity(
    result: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    authorization_receipt: Mapping[str, Any],
    trusted_authorization_sha256: str,
    evidence_inputs: Sequence[AuthenticatedEvidenceInput],
) -> dict[str, Any]:
    """Independently recompute the exact action result from authenticated evidence."""

    supplied = copy.deepcopy(dict(result))
    _verify_self_hash(supplied, "result_sha256")
    expected = execute_in625_spot_size_sensitivity(
        request,
        authorization_receipt=authorization_receipt,
        trusted_authorization_sha256=trusted_authorization_sha256,
        evidence_inputs=evidence_inputs,
    )
    _require(
        supplied == expected,
        "spot-size sensitivity result differs from independent recomputation",
    )
    return expected


__all__ = [
    "ACTION_SCHEMA_VERSION",
    "ACTION_TYPE",
    "ACTION_VERSION",
    "In625SpotSizeSensitivityError",
    "authorize_in625_spot_size_sensitivity_request",
    "build_in625_spot_size_sensitivity_request",
    "execute_in625_spot_size_sensitivity",
    "verify_in625_spot_size_sensitivity",
]
