"""Compatibility adapters between legacy dict/DataFrame data and entities."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import pandas as pd

from .quantities import ScientificQuantity, build_quantity_value
from .scientific_entities import ScientificEntity


def composition_row_to_entity(
    row: Mapping[str, Any],
    *,
    entity_id: str | None = None,
    formula_field: str = "formula",
    domain: str = "materials",
) -> ScientificEntity:
    formula = str(row.get(formula_field, "")).strip()
    elements = row.get("elements")
    amounts = row.get("stoichiometric_amounts", row.get("amounts"))
    fractions = row.get("atomic_fractions")
    if isinstance(elements, str):
        elements = [item.strip() for item in elements.split(",") if item.strip()]
    if not isinstance(elements, list):
        elements = []
    if not isinstance(amounts, Mapping):
        amounts = {}
    if not isinstance(fractions, Mapping):
        fractions = {}
    stable_suffix = hashlib.sha256(formula.encode("utf-8")).hexdigest()[:12]
    return ScientificEntity(
        entity_id=entity_id or f"composition_{stable_suffix}",
        entity_type="MaterialCompositionEntity",
        schema_id="scientific_entity_schema_v2",
        schema_version="2.2.2",
        domain=domain,
        attributes={
            "formula": formula,
            "elements": elements,
            "stoichiometric_amounts": dict(amounts),
            "atomic_fractions": dict(fractions),
            "normalization_status": row.get("normalization_status", "declared_or_derived"),
        },
        provenance_refs=tuple(str(item) for item in row.get("provenance_refs", ())) if not isinstance(row.get("provenance_refs"), str) else (str(row.get("provenance_refs")),),
        created_by="entity_adapters.composition_row_to_entity",
    )


def entity_to_compact_dict(entity: ScientificEntity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "schema_id": entity.schema_id,
        "schema_version": entity.schema_version,
        "domain": entity.domain,
        "validation_status": entity.validation_status,
        "artifact_count": len(entity.artifact_refs),
        "provenance_count": len(entity.provenance_refs),
    }


def measurement_dataframe_metadata_to_entity(
    frame: pd.DataFrame,
    *,
    entity_id: str,
    independent_variable: str,
    dependent_variable: str,
    artifact_ref: str | None = None,
) -> ScientificEntity:
    return ScientificEntity(
        entity_id=entity_id,
        entity_type="MeasurementSeriesEntity",
        schema_id="scientific_entity_schema_v2",
        schema_version="2.2.2",
        domain="generic",
        attributes={
            "independent_variable": independent_variable,
            "dependent_variable": dependent_variable,
            "axis_metadata": {
                "row_count": int(len(frame)),
                "columns": list(map(str, frame.columns)),
            },
            "measurement_conditions": {},
            "calibration_metadata": {},
        },
        artifact_refs=() if artifact_ref is None else (artifact_ref,),
        created_by="entity_adapters.measurement_dataframe_metadata_to_entity",
    )


def quantity_to_legacy_value(quantity: ScientificQuantity) -> dict[str, Any]:
    if quantity.value is None:
        assert quantity.array_metadata is not None
        return {
            "artifact_ref": quantity.array_metadata.artifact_ref,
            "unit": quantity.array_metadata.unit,
            "shape": list(quantity.array_metadata.shape),
        }
    return {
        "value": quantity.value.value,
        "unit": quantity.value.original_unit,
        "canonical_value": quantity.value.canonical_value,
        "canonical_unit": quantity.value.canonical_unit,
    }


def legacy_scientific_input_to_quantities(inputs: list[Mapping[str, Any]]) -> dict[str, ScientificQuantity]:
    quantities: dict[str, ScientificQuantity] = {}
    for item in inputs:
        quantity_id = str(item["variable_id"])
        value = build_quantity_value(
            value=float(item["value"]),
            unit=str(item["unit"]),
            uncertainty=item.get("uncertainty"),
        )
        quantities[quantity_id] = ScientificQuantity(quantity_id, value=value)
    return quantities
