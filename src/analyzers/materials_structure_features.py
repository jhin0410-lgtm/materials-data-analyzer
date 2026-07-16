"""Structure descriptor and periodic crystal graph helpers for v2.2.4.

This module works from JSON-safe CrystalStructureEntity records. It does not
read Materials Project targets, train models, build embeddings, or run GNNs.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from src.platform_core.materials_project_adapters import assess_crystal_graph_eligibility
from src.platform_core.scientific_entities import ScientificEntity


SCHEMA_VERSION = "2.2.4"
FORBIDDEN_DESCRIPTOR_FIELDS = {
    "energy_above_hull",
    "formation_energy_per_atom",
    "energy_per_atom",
    "total_energy",
    "is_stable",
    "equilibrium_reaction_energy",
    "decomposition_products",
    "hull_distance",
    "target",
    "prediction",
}


@dataclass(frozen=True)
class RadiusGraphConfig:
    cutoff_angstrom: float = 4.0
    max_neighbors: int = 24
    max_nodes: int = 512
    max_edges: int = 50_000
    directed: bool = True

    def __post_init__(self) -> None:
        if self.cutoff_angstrom <= 0 or self.cutoff_angstrom > 12:
            raise ValueError("cutoff_angstrom must be in the range (0, 12]")
        if self.max_neighbors <= 0 or self.max_neighbors > 256:
            raise ValueError("max_neighbors must be in the range 1..256")
        if self.max_nodes <= 0:
            raise ValueError("max_nodes must be positive")
        if self.max_edges <= 0:
            raise ValueError("max_edges must be positive")


def structure_descriptor_definitions() -> list[dict[str, Any]]:
    """Return deterministic descriptor metadata."""
    base = {
        "schema_version": SCHEMA_VERSION,
        "required_entity_type": "CrystalStructureEntity",
        "prediction_context": "known_structure_post_relaxation",
        "target_access_policy": "forbidden",
        "uncertainty_policy": "source_uncertainty_unavailable_unless_propagated",
    }
    rows = [
        ("structure_volume_per_atom", "angstrom^3/atom", "structure_feature_candidate", "cell_volume / site_count"),
        ("structure_density", "g/cm^3", "structure_feature_candidate", "source/computed density when available"),
        ("ordered_structure_flag", "unitless", "structure_feature_candidate", "ordered/disordered metadata"),
        ("crystal_system_category", "category", "structure_feature_candidate", "source-provided symmetry metadata only"),
        ("space_group_number_category", "category", "structure_feature_candidate", "source-provided symmetry metadata only"),
        ("nearest_neighbor_distance_mean", "angstrom", "structure_feature_candidate", "radius_graph_v1 neighbor distances"),
        ("nearest_neighbor_distance_std", "angstrom", "structure_feature_candidate", "radius_graph_v1 neighbor distances"),
        ("nearest_neighbor_distance_cv", "unitless", "structure_feature_candidate", "radius_graph_v1 neighbor distances"),
        ("coordination_number_mean", "count", "structure_feature_candidate", "radius_graph_v1 directed out-degree"),
        ("coordination_number_std", "count", "structure_feature_candidate", "radius_graph_v1 directed out-degree"),
        ("packing_fraction_candidate", "unitless", "descriptive_only", "unavailable without explicit radius source"),
        ("site_count", "count", "integrity_only", "unit-cell choice dependent"),
    ]
    return [
        {
            **base,
            "descriptor_id": descriptor_id,
            "version": "1",
            "output_unit": unit,
            "role": role,
            "algorithm": algorithm,
            "invariance_policy": "raw lattice matrix and flattened coordinates are excluded from primary features",
        }
        for descriptor_id, unit, role, algorithm in rows
    ]


def _entity_from_record(record: Mapping[str, Any]) -> ScientificEntity:
    payload = record.get("record", record)
    return ScientificEntity(
        entity_id=str(payload["entity_id"]),
        entity_type=str(payload["entity_type"]),
        schema_id=str(payload["schema_id"]),
        schema_version=str(payload["schema_version"]),
        domain=str(payload["domain"]),
        attributes=payload.get("attributes", {}),
        quantity_fields=payload.get("quantity_fields", {}),
        provenance_refs=tuple(str(item) for item in payload.get("provenance_refs", ())),
        artifact_refs=tuple(str(item) for item in payload.get("artifact_refs", ())),
        created_by=str(payload.get("created_by", "materials_structure_features")),
        validation_status=str(payload.get("validation_status", "valid")),
    )


def load_structure_entities(path: str | Path) -> list[ScientificEntity]:
    source = Path(path)
    if source.suffix == ".jsonl":
        return [
            _entity_from_record(json.loads(line))
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("entities"), list):
        return [_entity_from_record(item) for item in payload["entities"]]
    if isinstance(payload, dict):
        return [_entity_from_record(payload)]
    if isinstance(payload, list):
        return [_entity_from_record(item) for item in payload]
    raise ValueError("entity path must contain JSONL, JSON object, or JSON list")


def _lattice_matrix(entity: ScientificEntity) -> np.ndarray:
    matrix = np.array(entity.attributes["lattice"]["matrix"], dtype=float)
    if matrix.shape != (3, 3):
        raise ValueError("lattice matrix must be 3x3")
    return matrix


def _site_species(site: Mapping[str, Any]) -> str:
    species = site.get("species", [])
    if not species:
        return "unknown"
    return str(species[0].get("element", "unknown"))


def _fractional_coords(entity: ScientificEntity) -> np.ndarray:
    return np.array([site["fractional_coordinates"] for site in entity.attributes.get("sites", [])], dtype=float)


def _cartesian_coords(entity: ScientificEntity) -> np.ndarray:
    return _fractional_coords(entity) @ _lattice_matrix(entity)


def _cell_volume(entity: ScientificEntity) -> float:
    return float(abs(np.linalg.det(_lattice_matrix(entity))))


def _symmetry_field(entity: ScientificEntity, field: str) -> Any:
    symmetry = entity.attributes.get("symmetry")
    if isinstance(symmetry, str):
        try:
            symmetry = json.loads(symmetry)
        except json.JSONDecodeError:
            return None
    if isinstance(symmetry, Mapping):
        return symmetry.get(field)
    return None


def build_radius_graph(entity: ScientificEntity, config: RadiusGraphConfig | None = None) -> dict[str, Any]:
    """Build a deterministic periodic radius graph artifact."""
    if config is None:
        config = RadiusGraphConfig()
    if entity.entity_type != "CrystalStructureEntity":
        raise ValueError("radius graph requires CrystalStructureEntity")
    sites = entity.attributes.get("sites", [])
    if len(sites) > config.max_nodes:
        raise ValueError("structure exceeds max_nodes")
    lattice = _lattice_matrix(entity)
    frac = _fractional_coords(entity)
    nodes = [
        {
            "node_index": index,
            "source_site_index": int(site.get("site_index", index)),
            "species": _site_species(site),
            "fractional_coordinates": [float(value) for value in frac[index]],
            "occupancy": float(sum(float(item.get("occupancy", 0.0)) for item in site.get("species", []))),
        }
        for index, site in enumerate(sites)
    ]
    image_vectors = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)]
    edge_candidates: dict[int, list[dict[str, Any]]] = {index: [] for index in range(len(nodes))}
    for source_index in range(len(nodes)):
        for target_index in range(len(nodes)):
            for image in image_vectors:
                if source_index == target_index and image == (0, 0, 0):
                    continue
                displacement_frac = frac[target_index] + np.array(image, dtype=float) - frac[source_index]
                displacement_cart = displacement_frac @ lattice
                distance = float(np.linalg.norm(displacement_cart))
                if distance <= config.cutoff_angstrom + 1e-12:
                    edge_candidates[source_index].append(
                        {
                            "source": source_index,
                            "target": target_index,
                            "distance_angstrom": round(distance, 12),
                            "periodic_image": list(image),
                            "displacement_cartesian_angstrom": [round(float(value), 12) for value in displacement_cart],
                            "edge_construction_operator": "crystal_structure_to_radius_graph_v1",
                            "cutoff_angstrom": config.cutoff_angstrom,
                        }
                    )
    edges: list[dict[str, Any]] = []
    for source_index in sorted(edge_candidates):
        selected = sorted(
            edge_candidates[source_index],
            key=lambda edge: (edge["distance_angstrom"], edge["target"], edge["periodic_image"]),
        )[: config.max_neighbors]
        edges.extend(selected)
    edges = sorted(edges, key=lambda edge: (edge["source"], edge["distance_angstrom"], edge["target"], edge["periodic_image"]))
    if len(edges) > config.max_edges:
        raise ValueError("graph exceeds max_edges")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "entity_type": "GraphEntity",
        "graph_id": f"{entity.entity_id}_radius_graph_v1",
        "source_entity_id": entity.entity_id,
        "nodes": nodes,
        "edges": edges,
        "graph_construction_metadata": {
            "operator_id": "crystal_structure_to_radius_graph_v1",
            "cutoff_angstrom": config.cutoff_angstrom,
            "max_neighbors": config.max_neighbors,
            "directed": config.directed,
            "self_edges": False,
            "periodic": True,
            "target_values_included": False,
            "gnn_input_ready": False,
        },
    }
    payload["checksum_sha256"] = _canonical_sha(payload)
    return payload


def _canonical_sha(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def descriptor_row(entity: ScientificEntity, graph: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if entity.entity_type != "CrystalStructureEntity":
        raise ValueError("descriptor build requires CrystalStructureEntity")
    attrs = json.dumps(entity.attributes, sort_keys=True)
    lower = attrs.lower()
    forbidden = sorted(field for field in FORBIDDEN_DESCRIPTOR_FIELDS if field in lower)
    if forbidden:
        raise ValueError("target-like field present in structure entity attributes")
    site_count = len(entity.attributes.get("sites", []))
    volume = _cell_volume(entity)
    density = entity.quantity_fields.get("density", {}).get("value") if isinstance(entity.quantity_fields.get("density"), Mapping) else None
    if graph is None:
        try:
            graph = build_radius_graph(entity)
        except ValueError:
            graph = {"edges": []}
    distances = [float(edge["distance_angstrom"]) for edge in graph.get("edges", [])]
    coord_counts = Counter(int(edge["source"]) for edge in graph.get("edges", []))
    coordination = [coord_counts.get(index, 0) for index in range(site_count)]
    nn_mean = float(np.mean(distances)) if distances else None
    nn_std = float(np.std(distances)) if distances else None
    coord_mean = float(np.mean(coordination)) if coordination else None
    coord_std = float(np.std(coordination)) if coordination else None
    return {
        "entity_id": entity.entity_id,
        "material_id": entity.attributes.get("material_id"),
        "structure_volume_per_atom": None if site_count == 0 else volume / site_count,
        "structure_density": density,
        "ordered_structure_flag": 1 if entity.attributes.get("ordered_status") == "ordered" else 0,
        "crystal_system_category": _symmetry_field(entity, "crystal_system"),
        "space_group_number_category": _symmetry_field(entity, "number"),
        "nearest_neighbor_distance_mean": nn_mean,
        "nearest_neighbor_distance_std": nn_std,
        "nearest_neighbor_distance_cv": None if not nn_mean else (nn_std or 0.0) / nn_mean,
        "coordination_number_mean": coord_mean,
        "coordination_number_std": coord_std,
        "packing_fraction_candidate": None,
        "site_count": site_count,
        "raw_lattice_primary_feature": False,
        "target_accessed": False,
    }


def build_structure_descriptor_table(
    entities: list[ScientificEntity],
    *,
    graph_config: RadiusGraphConfig | None = None,
) -> pd.DataFrame:
    rows = []
    for entity in entities:
        graph = build_radius_graph(entity, graph_config)
        rows.append(descriptor_row(entity, graph))
    return pd.DataFrame(rows).sort_values("entity_id").reset_index(drop=True) if rows else pd.DataFrame()


def descriptor_coverage_summary(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if df.empty:
        for definition in structure_descriptor_definitions():
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "descriptor_id": definition["descriptor_id"],
                    "non_missing_count": 0,
                    "total_entities": 0,
                    "coverage": 0.0,
                    "role": definition["role"],
                    "status": "not_generated_no_entities",
                }
            )
        return rows
    total = len(df)
    for definition in structure_descriptor_definitions():
        descriptor_id = definition["descriptor_id"]
        non_missing = int(df[descriptor_id].notna().sum()) if descriptor_id in df else 0
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "descriptor_id": descriptor_id,
                "non_missing_count": non_missing,
                "total_entities": total,
                "coverage": 0.0 if total == 0 else non_missing / total,
                "role": definition["role"],
                "status": "available" if non_missing else "unavailable",
            }
        )
    return rows


def graph_eligibility_summary(entities: list[ScientificEntity], graphs: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    statuses = Counter(assess_crystal_graph_eligibility(entity)["status"] for entity in entities)
    graphs = graphs or []
    checksums = [str(graph.get("checksum_sha256")) for graph in graphs]
    return {
        "schema_version": SCHEMA_VERSION,
        "entity_count": len(entities),
        "graph_eligible_entities": int(statuses.get("graph_adapter_candidate", 0)),
        "status_counts": dict(sorted(statuses.items())),
        "graph_count": len(graphs),
        "all_graph_checksums_unique": len(checksums) == len(set(checksums)),
        "gnn_execution": False,
        "target_values_included": False,
    }


def write_structure_descriptors(path: str | Path, df: pd.DataFrame) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.name}.tmp")
    df.to_csv(temp, index=False)
    temp.replace(output)


def write_graph_jsonl(path: str | Path, graphs: Iterable[Mapping[str, Any]]) -> int:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.name}.tmp")
    count = 0
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for graph in graphs:
            handle.write(json.dumps(graph, sort_keys=True, separators=(",", ":")) + "\n")
            count += 1
    temp.replace(output)
    return count
