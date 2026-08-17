"""Provenance-stratified external physical evidence for IN625 LPBF research.

This module deliberately separates two questions that are easy to conflate:

1. How strong is the provenance of a physical record (raw repository bytes,
   author table, author figure, etc.)?
2. How comparable is that experiment to the exact NIST AMB2018-02 AMMT
   benchmark contract?

A physically real experiment from another machine can be valuable external
validation without becoming an AMMT trace. Numerical proximity, energy-density
similarity, or a shared alloy name never upgrades cross-machine evidence to the
exact benchmark stratum.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
REGISTRY_ID = "in625-single-track-external-physical-sources-v1"

NIST_STAGE1_TARGETS: dict[tuple[float, float], int] = {
    (137.9, 800.0): 3,
    (137.9, 1200.0): 3,
    (179.2, 400.0): 3,
}

EVIDENCE_STRATA = {
    "exact_benchmark_compatible",
    "machine_stratified_physical",
    "adjacent_physical",
    "publication_derived_physical",
    "diagnostic_or_simulated",
    "unusable",
}

RAW_EXTRACTION_MODES = {"raw_dataset"}
PUBLICATION_EXTRACTION_MODES = {"author_table", "author_figure"}
NON_PHYSICAL_EXTRACTION_MODES = {"secondary_only", "simulation", "diagnostic"}


class PhysicalEvidenceRegistryError(ValueError):
    """Raised when the source registry violates the fail-closed contract."""


def _required_string(value: dict[str, Any], key: str, label: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise PhysicalEvidenceRegistryError(f"{label} requires non-blank {key}.")
    return raw.strip()


def _finite_positive(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise PhysicalEvidenceRegistryError(f"{label} must be numeric.")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise PhysicalEvidenceRegistryError(f"{label} must be numeric.") from exc
    if not math.isfinite(out) or out <= 0:
        raise PhysicalEvidenceRegistryError(f"{label} must be finite and positive.")
    return out


def _validate_stage1_targets(registry: dict[str, Any]) -> None:
    raw = registry.get("nist_stage1_target_cells")
    if not isinstance(raw, list):
        raise PhysicalEvidenceRegistryError(
            "nist_stage1_target_cells must be an explicit list."
        )
    configured: dict[tuple[float, float], int] = {}
    for index, item in enumerate(raw):
        label = f"nist_stage1_target_cells[{index}]"
        if not isinstance(item, dict):
            raise PhysicalEvidenceRegistryError(f"{label} must be an object.")
        power = _finite_positive(item.get("actual_laser_power_w"), f"{label}.power")
        speed = _finite_positive(item.get("scan_speed_mm_s"), f"{label}.speed")
        count = item.get("minimum_independent_traces")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise PhysicalEvidenceRegistryError(
                f"{label}.minimum_independent_traces must be a positive integer."
            )
        key = (power, speed)
        if key in configured:
            raise PhysicalEvidenceRegistryError(f"Duplicate Stage 1 target {key}.")
        configured[key] = count
    if configured != NIST_STAGE1_TARGETS:
        raise PhysicalEvidenceRegistryError(
            "Configured Stage 1 targets differ from the frozen #76 acceptance contract."
        )


def _validate_process_points(candidate: dict[str, Any], label: str) -> list[dict[str, Any]]:
    raw = candidate.get("process_points")
    if not isinstance(raw, list):
        raise PhysicalEvidenceRegistryError(f"{label}.process_points must be a list.")
    result: list[dict[str, Any]] = []
    for index, point in enumerate(raw):
        point_label = f"{label}.process_points[{index}]"
        if not isinstance(point, dict):
            raise PhysicalEvidenceRegistryError(f"{point_label} must be an object.")
        out = dict(point)
        out["laser_power_w"] = _finite_positive(
            point.get("laser_power_w"), f"{point_label}.laser_power_w"
        )
        out["scan_speed_mm_s"] = _finite_positive(
            point.get("scan_speed_mm_s"), f"{point_label}.scan_speed_mm_s"
        )
        if "independent_track_count" in point:
            count = point["independent_track_count"]
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise PhysicalEvidenceRegistryError(
                    f"{point_label}.independent_track_count must be a positive integer."
                )
        result.append(out)
    return result


def validate_candidate(candidate: Any, index: int) -> dict[str, Any]:
    label = f"candidates[{index}]"
    if not isinstance(candidate, dict):
        raise PhysicalEvidenceRegistryError(f"{label} must be an object.")
    out = dict(candidate)
    required = (
        "candidate_id",
        "title",
        "authority",
        "source_reference",
        "access_date",
        "acquisition_status",
        "extraction_mode",
        "physical_origin",
        "experiment_family_id",
        "machine_id",
        "material_state",
        "power_semantics",
        "calibration_binding",
        "spot_size_semantics",
        "characterization",
        "replication_semantics",
        "comparability_class",
    )
    for key in required:
        out[key] = _required_string(candidate, key, label)

    if candidate.get("doi") is not None:
        out["doi"] = _required_string(candidate, "doi", label)
    out["process_points"] = _validate_process_points(candidate, label)

    checks = candidate.get("provenance_checks")
    if not isinstance(checks, dict) or not checks:
        raise PhysicalEvidenceRegistryError(
            f"{label}.provenance_checks must be a non-empty object."
        )
    out["provenance_checks"] = {
        str(key): _required_string({"value": value}, "value", f"{label}.provenance_checks")
        for key, value in checks.items()
    }

    notes = candidate.get("notes")
    if not isinstance(notes, list) or not all(
        isinstance(note, str) and note.strip() for note in notes
    ):
        raise PhysicalEvidenceRegistryError(f"{label}.notes must be non-blank strings.")
    out["notes"] = [note.strip() for note in notes]
    return out


def validate_registry(registry: Any) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise PhysicalEvidenceRegistryError("Registry root must be an object.")
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise PhysicalEvidenceRegistryError(
            f"schema_version must be exactly {SCHEMA_VERSION!r}."
        )
    if registry.get("registry_id") != REGISTRY_ID:
        raise PhysicalEvidenceRegistryError(f"registry_id must be {REGISTRY_ID!r}.")
    if registry.get("target_material") != "IN625":
        raise PhysicalEvidenceRegistryError("target_material must be exactly IN625.")
    _required_string(registry, "scientific_scope", "registry")
    _validate_stage1_targets(registry)

    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise PhysicalEvidenceRegistryError("candidates must be a non-empty list.")
    candidates = [
        validate_candidate(candidate, index)
        for index, candidate in enumerate(raw_candidates)
    ]
    ids = [candidate["candidate_id"] for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise PhysicalEvidenceRegistryError("candidate_id values must be unique.")

    out = dict(registry)
    out["candidates"] = candidates
    return out


def load_registry(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise PhysicalEvidenceRegistryError(f"Cannot read registry: {source}.") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalEvidenceRegistryError("Registry must be UTF-8 JSON.") from exc
    return validate_registry(value)


def classify_candidate(candidate: dict[str, Any]) -> str:
    """Return the provenance/comparability evidence stratum, fail closed."""
    physical_origin = candidate.get("physical_origin")
    extraction_mode = candidate.get("extraction_mode")
    checks = candidate.get("provenance_checks", {})

    if physical_origin != "physical" or extraction_mode in NON_PHYSICAL_EXTRACTION_MODES:
        return "diagnostic_or_simulated"
    if checks.get("source_identity") != "confirmed" or checks.get("material") != "confirmed":
        return "unusable"

    exact = (
        candidate.get("comparability_class") == "exact_benchmark"
        and candidate.get("machine_id") == "nist-ammt"
        and candidate.get("material_state") == "bare_plate"
        and candidate.get("power_semantics") == "achieved_calibrated_actual"
        and candidate.get("calibration_binding") == "authoritative_for_this_experiment"
        and extraction_mode in RAW_EXTRACTION_MODES
        and checks.get("machine") == "confirmed"
        and checks.get("power") == "confirmed"
        and checks.get("speed") == "confirmed"
        and checks.get("calibration") == "confirmed"
    )
    if exact:
        return "exact_benchmark_compatible"

    # Publication-derived physical evidence remains useful, but its provenance
    # strength is lower than source-bound raw bytes regardless of geometric
    # similarity to the benchmark.
    if extraction_mode in PUBLICATION_EXTRACTION_MODES:
        return "publication_derived_physical"

    if extraction_mode in RAW_EXTRACTION_MODES:
        if candidate.get("comparability_class") == "machine_stratified":
            return "machine_stratified_physical"
        if candidate.get("comparability_class") == "adjacent_process_state":
            return "adjacent_physical"

    return "unusable"


def candidate_stage1_support(candidate: dict[str, Any]) -> dict[str, Any]:
    """Evaluate exact #76 support; nearby points and P/v similarity never count."""
    stratum = classify_candidate(candidate)
    counts = {target: 0 for target in NIST_STAGE1_TARGETS}
    if stratum == "exact_benchmark_compatible":
        for point in candidate.get("process_points", []):
            key = (float(point["laser_power_w"]), float(point["scan_speed_mm_s"]))
            if key not in counts:
                continue
            count = point.get("independent_track_count")
            # Missing replication semantics fail closed. A mean, a repeated
            # measurement, or a single publication row is not three tracks.
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                counts[key] += count

    cells = []
    for target, required in NIST_STAGE1_TARGETS.items():
        observed = counts[target]
        cells.append(
            {
                "actual_laser_power_w": target[0],
                "scan_speed_mm_s": target[1],
                "required_independent_traces": required,
                "eligible_independent_traces": observed,
                "complete": observed >= required,
            }
        )
    return {
        "candidate_id": candidate["candidate_id"],
        "experiment_family_id": candidate["experiment_family_id"],
        "evidence_stratum": stratum,
        "eligible_for_issue_76": stratum == "exact_benchmark_compatible",
        "cells": cells,
        "candidate_completes_stage1": all(cell["complete"] for cell in cells),
    }


def build_support_matrix(registry: dict[str, Any]) -> list[dict[str, Any]]:
    validated = validate_registry(registry)
    rows: list[dict[str, Any]] = []
    for candidate in validated["candidates"]:
        stratum = classify_candidate(candidate)
        points = candidate["process_points"] or [None]
        for point in points:
            row: dict[str, Any] = {
                "candidate_id": candidate["candidate_id"],
                "experiment_family_id": candidate["experiment_family_id"],
                "authority": candidate["authority"],
                "source_reference": candidate["source_reference"],
                "machine_id": candidate["machine_id"],
                "material_state": candidate["material_state"],
                "power_semantics": candidate["power_semantics"],
                "calibration_binding": candidate["calibration_binding"],
                "spot_size_semantics": candidate["spot_size_semantics"],
                "characterization": candidate["characterization"],
                "replication_semantics": candidate["replication_semantics"],
                "extraction_mode": candidate["extraction_mode"],
                "comparability_class": candidate["comparability_class"],
                "evidence_stratum": stratum,
                "row_level_process_point_available": point is not None,
            }
            if point is not None:
                row.update(point)
                key = (float(point["laser_power_w"]), float(point["scan_speed_mm_s"]))
                row["is_exact_stage1_coordinate"] = key in NIST_STAGE1_TARGETS
                row["counts_for_stage1"] = (
                    stratum == "exact_benchmark_compatible"
                    and key in NIST_STAGE1_TARGETS
                    and isinstance(point.get("independent_track_count"), int)
                    and not isinstance(point.get("independent_track_count"), bool)
                )
            else:
                row["is_exact_stage1_coordinate"] = False
                row["counts_for_stage1"] = False
            rows.append(row)
    return rows


def experiment_family_overlaps(registry: dict[str, Any]) -> list[dict[str, Any]]:
    validated = validate_registry(registry)
    grouped: dict[str, list[str]] = defaultdict(list)
    for candidate in validated["candidates"]:
        grouped[candidate["experiment_family_id"]].append(candidate["candidate_id"])
    return [
        {
            "experiment_family_id": family,
            "candidate_ids": sorted(candidate_ids),
            "source_representation_count": len(candidate_ids),
        }
        for family, candidate_ids in sorted(grouped.items())
        if len(candidate_ids) > 1
    ]


def _aggregate_stage1_by_independent_family(
    candidates: list[dict[str, Any]],
) -> dict[tuple[float, float], int]:
    """Count an experiment family once even if paper + repository both expose it."""
    family_counts: dict[str, dict[tuple[float, float], int]] = defaultdict(
        lambda: {target: 0 for target in NIST_STAGE1_TARGETS}
    )
    for candidate in candidates:
        report = candidate_stage1_support(candidate)
        if not report["eligible_for_issue_76"]:
            continue
        family = candidate["experiment_family_id"]
        for cell in report["cells"]:
            key = (
                float(cell["actual_laser_power_w"]),
                float(cell["scan_speed_mm_s"]),
            )
            # Duplicate source representations of one experiment family may
            # differ in reporting completeness. Max preserves evidence without
            # double-counting the physical tracks.
            family_counts[family][key] = max(
                family_counts[family][key],
                int(cell["eligible_independent_traces"]),
            )

    totals = {target: 0 for target in NIST_STAGE1_TARGETS}
    for counts in family_counts.values():
        for target, count in counts.items():
            totals[target] += count
    return totals


def registry_audit(registry: dict[str, Any]) -> dict[str, Any]:
    validated = validate_registry(registry)
    candidates = validated["candidates"]
    classifications = {
        candidate["candidate_id"]: classify_candidate(candidate)
        for candidate in candidates
    }
    counts = Counter(classifications.values())
    overlaps = experiment_family_overlaps(validated)
    stage1_totals = _aggregate_stage1_by_independent_family(candidates)
    stage1_cells = []
    for target, required in NIST_STAGE1_TARGETS.items():
        observed = stage1_totals[target]
        stage1_cells.append(
            {
                "actual_laser_power_w": target[0],
                "scan_speed_mm_s": target[1],
                "required_independent_traces": required,
                "eligible_independent_traces": observed,
                "complete": observed >= required,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": REGISTRY_ID,
        "candidate_count": len(candidates),
        "independent_experiment_family_count": len(
            {candidate["experiment_family_id"] for candidate in candidates}
        ),
        "evidence_stratum_counts": {
            stratum: counts.get(stratum, 0) for stratum in sorted(EVIDENCE_STRATA)
        },
        "candidate_classifications": classifications,
        "experiment_family_overlaps": overlaps,
        "support_matrix": build_support_matrix(validated),
        "issue_76_stage1": {
            "cells": stage1_cells,
            "complete": all(cell["complete"] for cell in stage1_cells),
            "nearby_power_or_speed_counts_as_exact": False,
            "equal_energy_density_counts_as_exact": False,
            "cross_machine_power_relabeling_allowed": False,
            "publication_measurements_count_as_independent_tracks_without_track_identity": False,
        },
        "scientific_boundary": {
            "registry_inclusion_is_scientific_admissibility": False,
            "physical_origin_can_be_proven_by_self_declaration": False,
            "machine_and_material_state_are_explicit_model_factors": True,
            "paper_and_repository_views_of_same_experiment_are_independent": False,
            "issue_76_acceptance_contract_is_isolated": True,
        },
    }
