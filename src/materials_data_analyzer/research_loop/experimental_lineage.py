"""Physical lineage model for samples, experiments, acquisitions, and measurements.

The purpose of this module is to prevent pseudoreplication.  Different rows are not
independent observations merely because they have different measurement IDs.  The
classifier is intentionally conservative and returns ``unresolved`` whenever the lineage
needed to establish a stronger independence level is absent.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from .kernel import ResearchLoopError

EXPERIMENTAL_LINEAGE_SCHEMA_VERSION = "1.0"


class ExperimentalLineageError(ResearchLoopError):
    """Raised when physical lineage cannot be represented without inference."""


class IndependenceLevel(str, Enum):
    SAME_MEASUREMENT = "same_measurement"
    SAME_ACQUISITION = "same_acquisition"
    SAME_SPECIMEN = "same_specimen"
    INDEPENDENT_SPECIMEN_SAME_BUILD = "independent_specimen_same_build"
    INDEPENDENT_BUILD_SAME_LOT = "independent_build_same_lot"
    INDEPENDENT_LOT_SAME_SOURCE = "independent_lot_same_source"
    INDEPENDENT_SOURCE = "independent_source"
    UNRESOLVED = "unresolved"


def _text(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ExperimentalLineageError(f"{field} must be non-empty text")
    if value != value.strip():
        raise ExperimentalLineageError(f"{field} must not contain edge whitespace")
    return value


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExperimentalLineageError(
            "lineage must be canonical-JSON serializable"
        ) from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class ObservationLineage:
    source_id: str
    lab_id: str | None
    material_lot_id: str | None
    build_or_synthesis_id: str | None
    specimen_id: str
    process_run_id: str | None
    acquisition_id: str
    measurement_id: str
    derived_feature_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("source_id", "specimen_id", "acquisition_id", "measurement_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in (
            "lab_id",
            "material_lot_id",
            "build_or_synthesis_id",
            "process_run_id",
            "derived_feature_id",
        ):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field, optional=True),
            )

    @property
    def lineage_id(self) -> str:
        return "lineage:" + canonical_sha256(asdict(self))[:24]

    @property
    def lineage_sha256(self) -> str:
        return canonical_sha256(self.record())

    def record(self) -> dict[str, Any]:
        return {
            "schema_version": EXPERIMENTAL_LINEAGE_SCHEMA_VERSION,
            "lineage_id": self.lineage_id,
            **asdict(self),
            "identity_inferred": False,
        }


def _same_non_null(left: str | None, right: str | None) -> bool:
    return left is not None and right is not None and left == right


def _different_non_null(left: str | None, right: str | None) -> bool:
    return left is not None and right is not None and left != right


def classify_observation_independence(
    left: ObservationLineage,
    right: ObservationLineage,
) -> dict[str, Any]:
    """Classify the strongest independence level directly supported by lineage IDs."""
    if left.measurement_id == right.measurement_id:
        level = IndependenceLevel.SAME_MEASUREMENT
        reason = "identical_measurement_id"
    elif left.acquisition_id == right.acquisition_id:
        level = IndependenceLevel.SAME_ACQUISITION
        reason = "different_measurements_same_acquisition"
    elif left.specimen_id == right.specimen_id:
        level = IndependenceLevel.SAME_SPECIMEN
        reason = "different_acquisitions_same_specimen"
    elif _same_non_null(left.build_or_synthesis_id, right.build_or_synthesis_id):
        level = IndependenceLevel.INDEPENDENT_SPECIMEN_SAME_BUILD
        reason = "different_specimens_same_build_or_synthesis"
    elif (
        _same_non_null(left.material_lot_id, right.material_lot_id)
        and _different_non_null(
            left.build_or_synthesis_id,
            right.build_or_synthesis_id,
        )
    ):
        level = IndependenceLevel.INDEPENDENT_BUILD_SAME_LOT
        reason = "different_builds_same_material_lot"
    elif (
        _different_non_null(left.material_lot_id, right.material_lot_id)
        and left.source_id == right.source_id
        and left.lab_id is not None
        and right.lab_id is not None
        and left.lab_id == right.lab_id
    ):
        level = IndependenceLevel.INDEPENDENT_LOT_SAME_SOURCE
        reason = "different_material_lots_same_source_and_lab"
    elif (
        left.source_id != right.source_id
        and left.lab_id is not None
        and right.lab_id is not None
        and left.lab_id != right.lab_id
        and _different_non_null(left.material_lot_id, right.material_lot_id)
        and _different_non_null(
            left.build_or_synthesis_id,
            right.build_or_synthesis_id,
        )
    ):
        level = IndependenceLevel.INDEPENDENT_SOURCE
        reason = "different_sources_labs_lots_and_builds"
    else:
        level = IndependenceLevel.UNRESOLVED
        reason = "lineage_is_insufficient_for_stronger_independence_claim"
    return {
        "schema_version": EXPERIMENTAL_LINEAGE_SCHEMA_VERSION,
        "left_lineage_id": left.lineage_id,
        "right_lineage_id": right.lineage_id,
        "independence_level": level.value,
        "reason": reason,
        "statistically_independent_for_naive_row_count": level
        in {
            IndependenceLevel.INDEPENDENT_BUILD_SAME_LOT,
            IndependenceLevel.INDEPENDENT_LOT_SAME_SOURCE,
            IndependenceLevel.INDEPENDENT_SOURCE,
        },
        "external_source_independence_established": (
            level == IndependenceLevel.INDEPENDENT_SOURCE
        ),
        "identity_inferred": False,
    }


def effective_independent_unit(
    lineages: list[ObservationLineage],
) -> dict[str, Any]:
    """Report conservative unique counts at each physical lineage level."""
    if not lineages:
        raise ExperimentalLineageError("lineages must not be empty")

    def count(field: str) -> int | None:
        values = [getattr(item, field) for item in lineages]
        if any(value is None for value in values):
            return None
        return len(set(values))

    return {
        "schema_version": EXPERIMENTAL_LINEAGE_SCHEMA_VERSION,
        "row_count": len(lineages),
        "unique_measurements": len({item.measurement_id for item in lineages}),
        "unique_acquisitions": len({item.acquisition_id for item in lineages}),
        "unique_specimens": len({item.specimen_id for item in lineages}),
        "unique_builds_or_syntheses": count("build_or_synthesis_id"),
        "unique_material_lots": count("material_lot_id"),
        "unique_sources": len({item.source_id for item in lineages}),
        "unique_labs": count("lab_id"),
        "naive_row_count_is_independence_count": False,
        "missing_lineage_prevents_inference": any(
            item.material_lot_id is None
            or item.build_or_synthesis_id is None
            or item.lab_id is None
            for item in lineages
        ),
    }


__all__ = [
    "EXPERIMENTAL_LINEAGE_SCHEMA_VERSION",
    "ExperimentalLineageError",
    "IndependenceLevel",
    "ObservationLineage",
    "canonical_sha256",
    "classify_observation_independence",
    "effective_independent_unit",
]
