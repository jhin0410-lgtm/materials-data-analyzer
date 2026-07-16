"""Materials Project runtime adapters for JSON-safe scientific entities."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .entity_serialization import serialize_entity
from .materials_project_acquisition import parse_composition_mapping, reduced_composition_key
from .quantities import ScientificQuantity, build_quantity_value
from .scientific_entities import EntityReference, ScientificEntity
from .uncertainty import UncertaintySpec


ADAPTER_VERSION = "2.2.3"
SPECIES_PATTERN = re.compile(r"^[A-Z][a-z]?$")


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _as_float_matrix(matrix: Any) -> list[list[float]]:
    rows = [[float(value) for value in row] for row in matrix]
    if len(rows) != 3 or any(len(row) != 3 for row in rows):
        raise ValueError("lattice matrix must be 3x3")
    if not all(math.isfinite(value) for row in rows for value in row):
        raise ValueError("lattice matrix contains non-finite values")
    return rows


def _lattice_from_structure(structure: Any) -> dict[str, Any]:
    if hasattr(structure, "as_dict"):
        structure = structure.as_dict()
    if not isinstance(structure, Mapping):
        raise ValueError("structure must be a mapping or expose as_dict")
    lattice = structure.get("lattice", {})
    if hasattr(lattice, "as_dict"):
        lattice = lattice.as_dict()
    if isinstance(lattice, Mapping):
        matrix = lattice.get("matrix") or lattice.get("_matrix")
        lengths = lattice.get("abc") or [lattice.get("a"), lattice.get("b"), lattice.get("c")]
        angles = lattice.get("angles") or [lattice.get("alpha"), lattice.get("beta"), lattice.get("gamma")]
    else:
        matrix = lattice
        lengths = None
        angles = None
    matrix_rows = _as_float_matrix(matrix)
    lengths_out = [float(item) for item in lengths] if lengths and all(item is not None for item in lengths) else _lengths(matrix_rows)
    angles_out = [float(item) for item in angles] if angles and all(item is not None for item in angles) else _angles(matrix_rows)
    return {
        "matrix": matrix_rows,
        "unit": "angstrom",
        "lengths": lengths_out,
        "angles": angles_out,
        "volume": float(abs(np.linalg.det(np.array(matrix_rows, dtype=float)))),
    }


def _sites_from_structure(structure: Any) -> list[dict[str, Any]]:
    if hasattr(structure, "as_dict"):
        structure = structure.as_dict()
    sites = structure.get("sites", []) if isinstance(structure, Mapping) else []
    parsed: list[dict[str, Any]] = []
    for index, site in enumerate(sites):
        if hasattr(site, "as_dict"):
            site = site.as_dict()
        if not isinstance(site, Mapping):
            raise ValueError("site entries must be mappings")
        coords = site.get("abc") or site.get("frac_coords") or site.get("fractional_coordinates")
        if coords is None:
            raise ValueError("site missing fractional coordinates")
        species_raw = site.get("species") or site.get("species_string") or site.get("label")
        species: list[dict[str, Any]] = []
        if isinstance(species_raw, str):
            species = [{"element": species_raw, "occupancy": float(site.get("occupancy", 1.0))}]
        elif isinstance(species_raw, list):
            for item in species_raw:
                if isinstance(item, Mapping):
                    element = item.get("element") or item.get("label") or item.get("species")
                    occupancy = item.get("occu", item.get("occupancy", 1.0))
                    species.append({"element": str(element), "occupancy": float(occupancy)})
                else:
                    species.append({"element": str(item), "occupancy": 1.0})
        else:
            raise ValueError("site missing species")
        parsed.append(
            {
                "site_index": index,
                "species": species,
                "fractional_coordinates": [float(value) for value in coords],
            }
        )
    return parsed


def _lengths(matrix: list[list[float]]) -> list[float]:
    arr = np.array(matrix, dtype=float)
    return [float(np.linalg.norm(arr[index])) for index in range(3)]


def _angles(matrix: list[list[float]]) -> list[float]:
    arr = np.array(matrix, dtype=float)
    values: list[float] = []
    for first, second in ((1, 2), (0, 2), (0, 1)):
        numerator = float(np.dot(arr[first], arr[second]))
        denominator = float(np.linalg.norm(arr[first]) * np.linalg.norm(arr[second]))
        if denominator == 0:
            values.append(90.0)
            continue
        clipped = min(1.0, max(-1.0, numerator / denominator))
        values.append(float(math.degrees(math.acos(clipped))))
    return values


def _composition_from_sites(sites: list[dict[str, Any]]) -> dict[str, float]:
    composition: dict[str, float] = {}
    for site in sites:
        for species in site["species"]:
            element = str(species["element"])
            composition[element] = composition.get(element, 0.0) + float(species["occupancy"])
    return composition


@dataclass(frozen=True)
class MaterialsProjectSummaryAdapter:
    source_collection: str = "materials.summary"

    def to_composition_entity(self, row: Mapping[str, Any]) -> ScientificEntity:
        material_id = str(row["material_id"])
        composition = parse_composition_mapping(row.get("composition_reduced") or row.get("composition"))
        total = sum(composition.values())
        fractions = {key: value / total for key, value in composition.items()} if total else {}
        return ScientificEntity(
            entity_id=f"mp_{material_id}_composition",
            entity_type="MaterialCompositionEntity",
            schema_id="scientific_entity_schema_v2",
            schema_version="2.2.2",
            domain="materials",
            attributes={
                "formula": row.get("formula_pretty"),
                "elements": sorted(composition),
                "stoichiometric_amounts": dict(sorted(composition.items())),
                "atomic_fractions": dict(sorted(fractions.items())),
                "normalization_status": "parsed_from_materials_project_summary",
                "material_id": material_id,
                "source_collection": self.source_collection,
            },
            provenance_refs=("data/processed/materials_project_v1_3_acquisition_manifest.json",),
            created_by="materials_project_adapters.MaterialsProjectSummaryAdapter",
        )


@dataclass(frozen=True)
class MaterialsProjectTargetAdapter:
    target_field: str = "energy_above_hull"
    target_unit: str = "eV/atom"

    def to_quantity(self, row: Mapping[str, Any]) -> ScientificQuantity:
        material_id = str(row["material_id"])
        value = build_quantity_value(
            value=float(row[self.target_field]),
            unit=self.target_unit,
            uncertainty=UncertaintySpec.unavailable(
                method="source_does_not_provide_uncertainty",
                source="Materials Project summary",
            ),
            provenance_refs=("data/processed/materials_project_v1_3_acquisition_manifest.json",),
        )
        return ScientificQuantity(f"mp_{material_id}_{self.target_field}", value=value)


@dataclass(frozen=True)
class MaterialsProjectStructureAdapter:
    source_collection: str = "materials.summary"

    def to_crystal_structure_entity(
        self,
        *,
        material_id: str,
        structure: Any,
        summary_row: Mapping[str, Any] | None = None,
        parent_composition_ref: EntityReference | None = None,
        acquisition_manifest_ref: str = "outputs/materials_project_structure_v2_2/acquisition/acquisition_manifest.json",
    ) -> ScientificEntity:
        lattice = _lattice_from_structure(structure)
        sites = _sites_from_structure(structure)
        site_composition = _composition_from_sites(sites)
        structure_version = hashlib.sha256(
            json.dumps({"material_id": material_id, "lattice": lattice, "sites": sites}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        quantity_fields = {
            "lattice_a": build_quantity_value(value=lattice["lengths"][0], unit="angstrom").to_dict(),
            "lattice_b": build_quantity_value(value=lattice["lengths"][1], unit="angstrom").to_dict(),
            "lattice_c": build_quantity_value(value=lattice["lengths"][2], unit="angstrom").to_dict(),
            "alpha": build_quantity_value(value=lattice["angles"][0], unit="degree").to_dict(),
            "beta": build_quantity_value(value=lattice["angles"][1], unit="degree").to_dict(),
            "gamma": build_quantity_value(value=lattice["angles"][2], unit="degree").to_dict(),
            "cell_volume": build_quantity_value(value=lattice["volume"], unit="angstrom^3").to_dict(),
        }
        density = None if summary_row is None else summary_row.get("density")
        if density is not None:
            quantity_fields["density"] = build_quantity_value(value=float(density), unit="g/cm^3").to_dict()
        attributes = {
            "material_id": material_id,
            "source_collection": self.source_collection,
            "source_query_plan": "materials_project_v1_3_fe_si_containing_summary",
            "adapter_version": ADAPTER_VERSION,
            "lattice": {
                "matrix": lattice["matrix"],
                "unit": "angstrom",
                "periodic_axes": [True, True, True],
            },
            "periodic_boundary_conditions": [True, True, True],
            "sites": sites,
            "structure_derived_composition": dict(sorted(site_composition.items())),
            "reduced_composition": reduced_composition_key(site_composition),
            "total_sites": len(sites),
            "ordered_status": "ordered" if all(len(site["species"]) == 1 and site["species"][0]["occupancy"] == 1.0 for site in sites) else "disordered_or_partial",
            "symmetry": None if summary_row is None else summary_row.get("symmetry"),
        }
        refs = () if parent_composition_ref is None else (parent_composition_ref,)
        return ScientificEntity(
            entity_id=f"mp_{material_id}_structure_{structure_version}",
            entity_type="CrystalStructureEntity",
            schema_id="scientific_entity_schema_v2",
            schema_version="2.2.2",
            domain="materials",
            attributes=attributes,
            quantity_fields=quantity_fields,
            provenance_refs=(acquisition_manifest_ref,),
            parent_entity_refs=refs,
            created_by="materials_project_adapters.MaterialsProjectStructureAdapter",
        )


def crystal_basic_geometry_summary(entity: ScientificEntity) -> dict[str, Any]:
    lattice = entity.attributes["lattice"]
    matrix = _as_float_matrix(lattice["matrix"])
    lengths = _lengths(matrix)
    angles = _angles(matrix)
    volume = float(abs(np.linalg.det(np.array(matrix, dtype=float))))
    sites = entity.attributes.get("sites", [])
    site_count = len(sites)
    return {
        "operator_id": "crystal_basic_geometry_summary_v1",
        "entity_id": entity.entity_id,
        "lattice_a_angstrom": lengths[0],
        "lattice_b_angstrom": lengths[1],
        "lattice_c_angstrom": lengths[2],
        "alpha_degree": angles[0],
        "beta_degree": angles[1],
        "gamma_degree": angles[2],
        "cell_volume_angstrom3": volume,
        "site_count": site_count,
        "volume_per_site_angstrom3": None if site_count == 0 else volume / site_count,
        "ordered_status": entity.attributes.get("ordered_status"),
        "predictive_feature_artifact": False,
    }


def validate_crystal_structure_entity(entity: ScientificEntity) -> dict[str, Any]:
    findings: list[str] = []
    warnings: list[str] = []
    try:
        matrix = _as_float_matrix(entity.attributes["lattice"]["matrix"])
        volume = float(np.linalg.det(np.array(matrix, dtype=float)))
        if volume <= 0:
            findings.append("non_positive_lattice_volume")
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(f"invalid_lattice:{exc}")
        matrix = []
    sites = entity.attributes.get("sites", [])
    if not isinstance(sites, list) or not sites:
        findings.append("missing_sites")
    seen_indices: set[int] = set()
    for site in sites if isinstance(sites, list) else []:
        index = int(site.get("site_index", -1))
        if index in seen_indices:
            findings.append("duplicate_site_index")
        seen_indices.add(index)
        coords = site.get("fractional_coordinates", [])
        if len(coords) != 3 or not all(math.isfinite(float(value)) for value in coords):
            findings.append("invalid_fractional_coordinates")
        occupancy_sum = 0.0
        for species in site.get("species", []):
            element = str(species.get("element", ""))
            occupancy = float(species.get("occupancy", 0.0))
            if not SPECIES_PATTERN.match(element):
                findings.append("invalid_species_identifier")
            if occupancy <= 0:
                findings.append("non_positive_occupancy")
            occupancy_sum += occupancy
        if occupancy_sum > 1.0 + 1e-6:
            warnings.append("site_occupancy_sum_above_one")
    if entity.attributes.get("ordered_status") == "disordered_or_partial":
        warnings.append("unsupported_disorder_for_predictive_use")
    status = "valid" if not findings and not warnings else "valid_with_warnings" if not findings else "invalid"
    return {
        "operator_id": "crystal_structure_integrity_check_v1",
        "entity_id": entity.entity_id,
        "status": status,
        "findings": findings,
        "warnings": warnings,
        "mutated_source": False,
    }


def composition_structure_consistency(
    composition_entity: ScientificEntity,
    structure_entity: ScientificEntity,
    *,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    summary = composition_entity.attributes.get("stoichiometric_amounts", {})
    structure = structure_entity.attributes.get("structure_derived_composition", {})
    summary_reduced = reduced_composition_key({str(k): float(v) for k, v in summary.items()})
    structure_reduced = reduced_composition_key({str(k): float(v) for k, v in structure.items()})
    if not summary_reduced or not structure_reduced:
        status = "unavailable"
    elif summary_reduced.keys() != structure_reduced.keys():
        status = "mismatch"
    elif all(abs(summary_reduced[key] - structure_reduced[key]) <= tolerance for key in summary_reduced):
        status = "reduced_match"
    else:
        status = "mismatch"
    return {
        "operator_id": "composition_structure_consistency_check_v1",
        "composition_entity_id": composition_entity.entity_id,
        "structure_entity_id": structure_entity.entity_id,
        "status": status,
        "summary_reduced_composition": summary_reduced,
        "structure_reduced_composition": structure_reduced,
        "tolerance": tolerance,
        "interpretation": "consistency_check_not_phase_or_causality_claim",
    }


def assess_crystal_graph_eligibility(entity: ScientificEntity) -> dict[str, Any]:
    attrs = entity.attributes
    lattice_available = bool(attrs.get("lattice", {}).get("matrix"))
    sites_available = bool(attrs.get("sites"))
    species_available = all(site.get("species") for site in attrs.get("sites", [])) if sites_available else False
    coords_available = all(site.get("fractional_coordinates") for site in attrs.get("sites", [])) if sites_available else False
    occupancy_status = "supported_ordered" if attrs.get("ordered_status") == "ordered" else "blocked_disorder"
    if not lattice_available:
        status = "blocked_missing_lattice"
    elif not sites_available or not species_available or not coords_available:
        status = "blocked_missing_sites"
    elif occupancy_status == "blocked_disorder":
        status = "blocked_disorder"
    else:
        status = "graph_adapter_candidate"
    return {
        "operator_id": "structure.graph.metadata_contract",
        "entity_id": entity.entity_id,
        "status": status,
        "species_available": species_available,
        "fractional_coordinates_available": coords_available,
        "lattice_available": lattice_available,
        "periodicity_available": bool(attrs.get("periodic_boundary_conditions")),
        "occupancy_support_status": occupancy_status,
        "neighbor_policy_selected": False,
        "graph_constructed": False,
        "gnn_ready": False,
        "claim": "graph-construction contract eligibility only",
    }


def structure_entity_record(entity: ScientificEntity) -> dict[str, Any]:
    return serialize_entity(entity)
