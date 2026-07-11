"""Composition-only descriptors and readiness audits for Materials Project v1.3."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from pymatgen.core import Composition, Element


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET_COLUMN = "energy_above_hull"
IDENTIFIER_COLUMN = "material_id"
COMPOSITION_SOURCE_PRIORITY = ["composition_reduced", "composition", "formula_pretty"]
METADATA_COLUMNS = ["material_id", "formula_pretty"]
GROUPING_COLUMNS = ["reduced_formula_group", "chemical_system_group"]
STRUCTURE_GROUPING_COLUMNS = ["crystal_system_group", "space_group_number_group"]
EVALUATION_ONLY_COLUMNS = ["theoretical"]
ANALYSIS_ONLY_CALCULATED_PROPERTIES = [
    "formation_energy_per_atom",
    "density",
    "volume",
    "nsites",
    "band_gap",
    "is_metal",
]
FORBIDDEN_FEATURES = [
    "material_id",
    "formula_pretty",
    "elements",
    "chemsys",
    "energy_above_hull",
    "is_stable",
    "formation_energy_per_atom",
    "density",
    "volume",
    "nsites",
    "band_gap",
    "is_metal",
    "theoretical",
    "symmetry",
    "last_updated",
    "origins",
    "database_IDs",
]
STOICHIOMETRIC_FEATURES = [
    "composition_element_count",
    "composition_fraction_min",
    "composition_fraction_max",
    "composition_fraction_range",
    "composition_fraction_mean",
    "composition_fraction_std",
    "composition_fraction_entropy",
    "composition_fraction_l2_norm",
    "composition_dominant_fraction",
]
ELEMENTAL_PROPERTY_SPECS = {
    "atomic_number": {
        "attribute": "Z",
        "unit": "atomic number",
        "definition": "Atomic number from pymatgen.core.Element.Z.",
        "preferred_for_mismatch": True,
    },
    "atomic_mass": {
        "attribute": "atomic_mass",
        "unit": "amu",
        "definition": "Standard atomic mass from pymatgen.core.Element.atomic_mass.",
        "preferred_for_mismatch": True,
    },
    "periodic_row": {
        "attribute": "row",
        "unit": "period",
        "definition": "Periodic table row from pymatgen.core.Element.row.",
        "preferred_for_mismatch": False,
    },
    "periodic_group": {
        "attribute": "group",
        "unit": "group",
        "definition": "Periodic table group from pymatgen.core.Element.group.",
        "preferred_for_mismatch": False,
    },
    "electronegativity": {
        "attribute": "X",
        "unit": "Pauling",
        "definition": "Pauling electronegativity from pymatgen.core.Element.X.",
        "preferred_for_mismatch": True,
    },
    "mendeleev_number": {
        "attribute": "mendeleev_no",
        "unit": "ordinal",
        "definition": "Mendeleev number from pymatgen.core.Element.mendeleev_no.",
        "preferred_for_mismatch": False,
    },
    "atomic_radius": {
        "attribute": "atomic_radius",
        "unit": "angstrom",
        "definition": "Element.atomic_radius as provided by pymatgen; not an inferred ionic radius.",
        "preferred_for_mismatch": True,
    },
    "first_ionization_energy": {
        "attribute": "ionization_energy",
        "unit": "eV",
        "definition": "First ionization energy from pymatgen.core.Element.ionization_energy.",
        "preferred_for_mismatch": True,
    },
}
AGGREGATIONS = ["weighted_mean", "minimum", "maximum", "range", "weighted_std"]
CATEGORY_DESCRIPTOR_COLUMNS = [
    "s_block_fraction",
    "p_block_fraction",
    "d_block_fraction",
    "f_block_fraction",
    "transition_metal_fraction",
    "metalloid_fraction",
]


@dataclass(frozen=True)
class ParsedComposition:
    """Parsed composition and row-level provenance."""

    composition: Composition | None
    source: str
    status: str
    issues: tuple[str, ...]


def calculate_file_sha256(path: str | Path) -> str:
    """Calculate SHA-256 without modifying a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_descriptor_spec() -> dict[str, Any]:
    """Build the credential-free descriptor specification."""
    return {
        "schema_version": "1.0",
        "dataset_version": "v1.3",
        "descriptor_version": "v1.3.3",
        "execution_status": "specified",
        "composition_source_priority": list(COMPOSITION_SOURCE_PRIORITY),
        "identifier_column": IDENTIFIER_COLUMN,
        "target_column": TARGET_COLUMN,
        "metadata_columns": list(METADATA_COLUMNS),
        "grouping_columns": list(GROUPING_COLUMNS),
        "evaluation_only_columns": list(EVALUATION_ONLY_COLUMNS),
        "stoichiometric_features": {
            "columns": list(STOICHIOMETRIC_FEATURES),
            "entropy_log_base": "natural_log",
            "zero_fraction_policy": "ignore zero fractions in entropy sum",
        },
        "elemental_properties": [
            {
                "name": name,
                "pymatgen_attribute": meta["attribute"],
                "property_source": "pymatgen.core.Element",
                "property_definition": meta["definition"],
                "unit": meta["unit"],
            }
            for name, meta in ELEMENTAL_PROPERTY_SPECS.items()
        ],
        "elemental_aggregations": list(AGGREGATIONS),
        "mismatch_features": {
            "formula": "sum_{i<j} x_i * x_j * abs(p_i - p_j)",
            "candidate_properties": [
                name
                for name, meta in ELEMENTAL_PROPERTY_SPECS.items()
                if meta["preferred_for_mismatch"]
            ],
        },
        "categorical_composition_features": list(CATEGORY_DESCRIPTOR_COLUMNS),
        "forbidden_features": list(FORBIDDEN_FEATURES),
        "missing_property_policy": "Do not zero-fill missing elemental properties; exclude property families with incomplete observed-element coverage.",
        "nonfinite_policy": "Nonfinite descriptor values are flagged and preserved as missing values.",
        "deterministic_ordering": "Sort output rows by material_id and descriptor columns by deterministic specification order.",
        "local_output_path": "data/processed/materials_project_v1_3_analysis_ready.csv",
        "tracked_output_paths": [
            "data/processed/materials_project_v1_3_descriptor_inventory.csv",
            "data/processed/materials_project_v1_3_descriptor_redundancy_summary.csv",
            "data/processed/materials_project_v1_3_composition_ambiguity_summary.csv",
            "data/processed/materials_project_v1_3_target_suitability_summary.csv",
            "data/processed/materials_project_v1_3_split_readiness_summary.csv",
            "data/processed/materials_project_v1_3_group_inventory.csv",
        ],
        "stop_conditions": [
            "source acquired CSV row count does not match acquisition manifest",
            "meaningful composition parse failure",
            "forbidden/leakage feature included as a primary descriptor",
            "primary descriptor generation fails",
            "target distribution is effectively constant",
            "reduced-formula or chemical-system groups are insufficient",
            "credential-like value or absolute path appears in outputs",
        ],
        "limitations": [
            "Composition-only descriptors cannot distinguish all polymorph-specific Materials Project targets.",
            "Descriptor values are not causal evidence.",
            "No model training, SHAP/LIME, split execution, or candidate screening is performed in v1.3.3.",
        ],
    }


def write_descriptor_spec(path: str | Path) -> None:
    """Write descriptor spec JSON."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_descriptor_spec(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def classify_acquired_schema(columns: Iterable[str]) -> pd.DataFrame:
    """Classify acquired v1.3 columns by role."""
    role_by_column = {
        "material_id": ("identifier", "Identifier only; forbidden as model feature."),
        "formula_pretty": ("display metadata", "Human-readable formula; no raw text encoding."),
        "chemsys": ("grouping metadata", "Chemical-system grouping source; not a primary feature."),
        "elements": ("composition source", "Element list used for scope validation; not raw encoded."),
        "nelements": ("composition source", "Element count source for consistency check."),
        "theoretical": ("evaluation-only metadata", "Subgroup/evaluation metadata only."),
        "deprecated": ("evaluation-only metadata", "Acquisition quality metadata."),
        "energy_above_hull": ("target", "Regression target; forbidden as feature."),
        "composition": ("composition source", "Structured composition fallback."),
        "composition_reduced": ("composition source", "Primary structured composition source."),
        "formation_energy_per_atom": ("analysis-only calculated property", "MP computed property; not primary composition feature."),
        "density": ("analysis-only calculated property", "MP computed property; not primary composition feature."),
        "volume": ("analysis-only calculated property", "MP computed property; not primary composition feature."),
        "nsites": ("analysis-only calculated property", "MP computed property; not primary composition feature."),
        "band_gap": ("analysis-only calculated property", "MP computed property; not primary composition feature."),
        "is_metal": ("analysis-only calculated property", "MP computed property; not primary composition feature."),
        "symmetry": ("provenance/nested field", "Nested symmetry metadata; structure split feasibility only."),
        "is_stable": ("forbidden feature", "Target-derived stability label; forbidden."),
        "origins": ("provenance/nested field", "Nested provenance."),
        "last_updated": ("provenance/nested field", "Record timestamp metadata."),
        "database_IDs": ("provenance/nested field", "Nested database cross references."),
    }
    rows = []
    for column in columns:
        role, note = role_by_column.get(column, ("unclassified", "Review before use."))
        rows.append({"column_name": column, "column_role": role, "policy_note": note})
    return pd.DataFrame(rows)


def build_analysis_ready_table(
    acquired_df: pd.DataFrame,
    manifest: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create composition-only analysis-ready descriptors without dropping rows."""
    source = acquired_df.copy()
    source = source.sort_values(
        by=IDENTIFIER_COLUMN,
        key=lambda series: series.astype(str),
        kind="mergesort",
    ).reset_index(drop=True)
    _validate_manifest_shape(source, manifest)

    parsed_rows = [parse_composition_row(row) for _, row in source.iterrows()]
    element_property_catalog = build_elemental_property_catalog(parsed_rows)
    included_properties = [
        name
        for name, item in element_property_catalog.items()
        if item["coverage_status"] == "complete"
    ]
    excluded_properties = [
        name
        for name, item in element_property_catalog.items()
        if item["coverage_status"] != "complete"
    ]

    descriptor_rows: list[dict[str, Any]] = []
    for (_, row), parsed in zip(source.iterrows(), parsed_rows):
        descriptor_rows.append(
            build_descriptor_row(
                row,
                parsed,
                included_properties=included_properties,
            )
        )
    descriptors = pd.DataFrame(descriptor_rows)
    structure_groups = pd.DataFrame(
        [_parse_symmetry_groups(value) for value in source.get("symmetry", [])]
    )

    output = pd.concat(
        [
            source[[IDENTIFIER_COLUMN, "formula_pretty"]].reset_index(drop=True),
            descriptors.reset_index(drop=True),
            structure_groups.reset_index(drop=True),
            source[[TARGET_COLUMN, "theoretical"]].reset_index(drop=True),
        ],
        axis=1,
    )
    primary_features = primary_feature_columns(output)
    forbidden_in_features = sorted(set(primary_features).intersection(FORBIDDEN_FEATURES))
    metadata = {
        "input_row_count": int(len(acquired_df)),
        "output_row_count": int(len(output)),
        "composition_source_priority": list(COMPOSITION_SOURCE_PRIORITY),
        "parse_status_counts": output["composition_parse_status"].value_counts(dropna=False).to_dict(),
        "descriptor_quality_status_counts": output["descriptor_quality_status"].value_counts(dropna=False).to_dict(),
        "primary_feature_count": int(len(primary_features)),
        "included_elemental_properties": included_properties,
        "excluded_elemental_properties": excluded_properties,
        "elemental_property_catalog": element_property_catalog,
        "forbidden_features_in_primary_features": forbidden_in_features,
        "execution_status": "failed" if forbidden_in_features else "success",
    }
    return output, metadata


def parse_composition_row(row: pd.Series) -> ParsedComposition:
    """Parse one acquired row using structured composition before formula fallback."""
    issues: list[str] = []
    for source in COMPOSITION_SOURCE_PRIORITY:
        raw_value = row.get(source)
        composition = _composition_from_value(raw_value)
        if composition is not None:
            return ParsedComposition(
                composition=composition,
                source=source,
                status="parsed",
                issues=tuple(issues),
            )
        issues.append(f"parse_failed:{source}")
    return ParsedComposition(
        composition=None,
        source="none",
        status="failed",
        issues=tuple(issues + ["composition_parse_failure"]),
    )


def build_descriptor_row(
    row: pd.Series,
    parsed: ParsedComposition,
    *,
    included_properties: list[str],
) -> dict[str, Any]:
    """Build one descriptor row."""
    issues = list(parsed.issues)
    result: dict[str, Any] = {
        "composition_parse_status": parsed.status,
        "composition_parse_source": parsed.source,
    }
    if parsed.composition is None:
        for column in GROUPING_COLUMNS + STOICHIOMETRIC_FEATURES + CATEGORY_DESCRIPTOR_COLUMNS:
            result[column] = np.nan
        for property_name in included_properties:
            for aggregation in AGGREGATIONS:
                result[f"{property_name}_{aggregation}"] = np.nan
            if ELEMENTAL_PROPERTY_SPECS[property_name]["preferred_for_mismatch"]:
                result[f"pairwise_mismatch_{property_name}"] = np.nan
        result.update(_quality_fields(issues, "invalid"))
        return result

    composition = parsed.composition
    fractions = _element_fractions(composition)
    elements = list(fractions)
    values = np.array(list(fractions.values()), dtype=float)
    fraction_sum = float(values.sum())
    reduced_formula = composition.reduced_formula
    chemical_system = composition.chemical_system
    source_nelements = _safe_int(row.get("nelements"))
    derived_count = len(elements)

    if abs(fraction_sum - 1.0) > 1e-8:
        issues.append("fraction_sum_not_one")
    if source_nelements is not None and source_nelements != derived_count:
        issues.append("source_nelements_mismatch")
    if "Fe" not in elements:
        issues.append("missing_fe")
    if "Si" not in elements:
        issues.append("missing_si")

    result.update(
        {
            "reduced_formula_group": reduced_formula,
            "chemical_system_group": chemical_system,
            "derived_element_count": derived_count,
            "fraction_sum": fraction_sum,
            "composition_element_count": derived_count,
            "composition_fraction_min": float(values.min()),
            "composition_fraction_max": float(values.max()),
            "composition_fraction_range": float(values.max() - values.min()),
            "composition_fraction_mean": float(values.mean()),
            "composition_fraction_std": float(values.std(ddof=0)),
            "composition_fraction_entropy": _entropy(values),
            "composition_fraction_l2_norm": float(np.sqrt(np.sum(values**2))),
            "composition_dominant_fraction": float(values.max()),
        }
    )

    for property_name in included_properties:
        property_values = {
            element: _element_property_value(element, property_name) for element in elements
        }
        result.update(_aggregate_property(property_name, fractions, property_values))
        if ELEMENTAL_PROPERTY_SPECS[property_name]["preferred_for_mismatch"]:
            result[f"pairwise_mismatch_{property_name}"] = _pairwise_mismatch(
                fractions,
                property_values,
            )

    result.update(_category_fractions(fractions))
    status = "valid" if not issues else "warning"
    result.update(_quality_fields(issues, status))
    return result


def build_elemental_property_catalog(
    parsed_rows: list[ParsedComposition],
) -> dict[str, dict[str, Any]]:
    """Inspect pymatgen Element property coverage for observed elements."""
    observed_elements = sorted(
        {
            element.symbol
            for parsed in parsed_rows
            if parsed.composition is not None
            for element in parsed.composition.elements
        }
    )
    catalog: dict[str, dict[str, Any]] = {}
    for property_name, meta in ELEMENTAL_PROPERTY_SPECS.items():
        values = {
            element: _element_property_value(element, property_name)
            for element in observed_elements
        }
        missing_elements = sorted(
            element for element, value in values.items() if value is None or not math.isfinite(value)
        )
        element_level_coverage = (
            (len(observed_elements) - len(missing_elements)) / len(observed_elements)
            if observed_elements
            else 0.0
        )
        coverage_status = "complete" if not missing_elements and observed_elements else "excluded"
        catalog[property_name] = {
            "property_source": "pymatgen.core.Element",
            "pymatgen_attribute": meta["attribute"],
            "property_definition": meta["definition"],
            "unit": meta["unit"],
            "observed_element_count": len(observed_elements),
            "element_level_coverage": element_level_coverage,
            "row_level_coverage": element_level_coverage,
            "missing_count": len(missing_elements),
            "missing_elements": missing_elements,
            "coverage_status": coverage_status,
        }
    return catalog


def primary_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return columns used as primary composition-only descriptors."""
    excluded_prefixes = (
        "composition_parse_",
        "descriptor_quality_",
        "descriptor_issue",
        "descriptor_issues",
    )
    excluded = {
        IDENTIFIER_COLUMN,
        "formula_pretty",
        "reduced_formula_group",
        "chemical_system_group",
        TARGET_COLUMN,
        "theoretical",
        "composition_parse_status",
        "composition_parse_source",
        "descriptor_quality_status",
        "descriptor_issue_count",
        "descriptor_issues",
        "derived_element_count",
        "fraction_sum",
        *STRUCTURE_GROUPING_COLUMNS,
    }
    columns: list[str] = []
    for column in df.columns:
        if column in excluded or column.startswith(excluded_prefixes):
            continue
        if pd.api.types.is_numeric_dtype(df[column]):
            columns.append(column)
    return columns


def build_descriptor_inventory(
    analysis_df: pd.DataFrame,
    metadata: dict[str, Any],
) -> pd.DataFrame:
    """Build one inventory row per metadata/descriptor column plus property coverage."""
    primary_features = set(primary_feature_columns(analysis_df))
    rows: list[dict[str, Any]] = []
    for column in analysis_df.columns:
        series = analysis_df[column]
        numeric = pd.to_numeric(series, errors="coerce") if pd.api.types.is_numeric_dtype(series) else None
        column_role, family, elemental_property, aggregation = _column_descriptor_metadata(column)
        rows.append(
            {
                "column_name": column,
                "column_role": column_role,
                "descriptor_family": family,
                "elemental_property": elemental_property,
                "aggregation": aggregation,
                "formula_or_definition": _formula_or_definition(column, elemental_property, aggregation),
                "property_source": _property_source(elemental_property),
                "property_definition": _property_definition(elemental_property),
                "unit": _unit(elemental_property, column),
                "dtype": str(series.dtype),
                "non_null_count": int(series.notna().sum()),
                "null_count": int(series.isna().sum()),
                "null_percentage": _percentage(int(series.isna().sum()), len(series)),
                "finite_count": int(np.isfinite(numeric.dropna()).sum()) if numeric is not None else pd.NA,
                "unique_count": int(series.nunique(dropna=True)),
                "minimum": float(numeric.min()) if numeric is not None and numeric.notna().any() else pd.NA,
                "median": float(numeric.median()) if numeric is not None and numeric.notna().any() else pd.NA,
                "maximum": float(numeric.max()) if numeric is not None and numeric.notna().any() else pd.NA,
                "variance": float(numeric.var(ddof=0)) if numeric is not None and numeric.notna().any() else pd.NA,
                "constant": bool(series.nunique(dropna=False) <= 1),
                "near_constant": _is_near_constant(series),
                "primary_feature": column in primary_features,
                "forbidden_feature": column in FORBIDDEN_FEATURES or column == TARGET_COLUMN,
                "evaluation_only": column in EVALUATION_ONLY_COLUMNS,
                "physical_rationale": _physical_rationale(column, family),
                "interpretation_limit": _interpretation_limit(column, family),
                "coverage_status": "complete" if int(series.isna().sum()) == 0 else "partial",
                "quality_note": _quality_note(column),
            }
        )

    for property_name, catalog in metadata["elemental_property_catalog"].items():
        if catalog["coverage_status"] == "complete":
            continue
        rows.append(
            {
                "column_name": f"excluded_elemental_property:{property_name}",
                "column_role": "excluded_property",
                "descriptor_family": "elemental_property_coverage",
                "elemental_property": property_name,
                "aggregation": "not_generated",
                "formula_or_definition": "Excluded because observed-element coverage is incomplete.",
                "property_source": catalog["property_source"],
                "property_definition": catalog["property_definition"],
                "unit": catalog["unit"],
                "dtype": "not_generated",
                "non_null_count": 0,
                "null_count": 0,
                "null_percentage": 0.0,
                "finite_count": 0,
                "unique_count": 0,
                "minimum": pd.NA,
                "median": pd.NA,
                "maximum": pd.NA,
                "variance": pd.NA,
                "constant": False,
                "near_constant": False,
                "primary_feature": False,
                "forbidden_feature": False,
                "evaluation_only": False,
                "physical_rationale": "Coverage audit only.",
                "interpretation_limit": "Property was not used to generate descriptors.",
                "coverage_status": "excluded",
                "quality_note": "missing_elements=" + ",".join(catalog["missing_elements"]),
            }
        )
    return pd.DataFrame(rows)


def build_descriptor_redundancy_summary(
    analysis_df: pd.DataFrame,
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    """Audit duplicate, constant, near-constant, and highly correlated features."""
    primary_features = primary_feature_columns(analysis_df)
    feature_family = dict(zip(inventory["column_name"], inventory["descriptor_family"]))
    rows: list[dict[str, Any]] = []
    for feature in primary_features:
        series = analysis_df[feature]
        if series.nunique(dropna=False) <= 1:
            rows.append(_redundancy_row("constant_feature", feature, None, feature_family, None, "warning", "Review before modeling; do not auto-drop in v1.3.3."))
        elif _is_near_constant(series):
            rows.append(_redundancy_row("near_constant_feature", feature, None, feature_family, None, "warning", "Review before modeling; do not auto-drop in v1.3.3."))

    duplicate_pairs = _exact_duplicate_feature_pairs(analysis_df, primary_features)
    for feature_a, feature_b in duplicate_pairs:
        rows.append(_redundancy_row("exact_duplicate_feature_pair", feature_a, feature_b, feature_family, 1.0, "warning", "Feature columns are exact duplicates; review preprocessing policy in v1.3.4."))

    corr = analysis_df[primary_features].corr(method="spearman") if primary_features else pd.DataFrame()
    high_corr_count = 0
    for idx, feature_a in enumerate(primary_features):
        for feature_b in primary_features[idx + 1 :]:
            value = corr.loc[feature_a, feature_b]
            if pd.notna(value) and abs(float(value)) >= 0.95:
                high_corr_count += 1
                rows.append(_redundancy_row("spearman_abs_ge_0.95", feature_a, feature_b, feature_family, float(value), "info", "High correlation is logged for later preprocessing review, not auto-removal."))

    duplicate_vector_rows = int(
        analysis_df[primary_features].duplicated(keep=False).sum()
    ) if primary_features else 0
    duplicate_vector_groups = int(
        analysis_df[primary_features].drop_duplicates().shape[0]
    ) if primary_features else 0
    rows.extend(
        [
            _redundancy_metric("primary_feature_count", len(primary_features), "info", "Number of primary composition-only descriptor columns."),
            _redundancy_metric("high_correlation_pair_count", high_corr_count, "info", "Spearman absolute correlation >= 0.95 feature pairs."),
            _redundancy_metric("duplicate_descriptor_vector_rows", duplicate_vector_rows, "warning" if duplicate_vector_rows else "info", "Rows sharing a descriptor vector with another material."),
            _redundancy_metric("unique_descriptor_vector_count", duplicate_vector_groups, "info", "Unique primary descriptor vectors."),
        ]
    )
    return pd.DataFrame(rows)


def build_composition_ambiguity_summary(analysis_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Quantify same-composition target ambiguity without merging polymorph rows."""
    primary_features = primary_feature_columns(analysis_df)
    rows: list[dict[str, Any]] = []
    total_abs_error = 0.0
    total_sq_error = 0.0
    total_weight = 0
    for formula, group in analysis_df.groupby("reduced_formula_group", dropna=False):
        targets = pd.to_numeric(group[TARGET_COLUMN], errors="coerce").dropna()
        if targets.empty:
            target_min = target_median = target_max = target_mean = target_std = target_mad = np.nan
            target_range = np.nan
        else:
            target_min = float(targets.min())
            target_median = float(targets.median())
            target_max = float(targets.max())
            target_mean = float(targets.mean())
            target_std = float(targets.std(ddof=0))
            target_mad = float((targets - target_median).abs().median())
            target_range = float(target_max - target_min)
            total_abs_error += float((targets - target_median).abs().sum())
            total_sq_error += float(((targets - target_mean) ** 2).sum())
            total_weight += int(len(targets))
        descriptor_vectors = group[primary_features].round(12).astype(str) if primary_features else pd.DataFrame(index=group.index)
        unique_descriptor_vector_count = int(descriptor_vectors.drop_duplicates().shape[0])
        zero_count = int((targets == 0).sum())
        positive_count = int((targets > 0).sum())
        ambiguity_flag = bool(len(group) > unique_descriptor_vector_count and (target_range or 0.0) > 1e-12)
        rows.append(
            {
                "reduced_formula_group": formula,
                "row_count": int(len(group)),
                "unique_material_id_count": int(group[IDENTIFIER_COLUMN].nunique(dropna=True)),
                "unique_descriptor_vector_count": unique_descriptor_vector_count,
                "target_min": target_min,
                "target_median": target_median,
                "target_max": target_max,
                "target_range": target_range,
                "target_mean": target_mean,
                "target_std": target_std,
                "target_mad": target_mad,
                "target_zero_count": zero_count,
                "mixed_zero_positive_status": "mixed_zero_positive" if zero_count and positive_count else "not_mixed",
                "theoretical_false_count": int(group["theoretical"].eq(False).sum()),
                "theoretical_true_count": int(group["theoretical"].eq(True).sum()),
                "polymorph_count": int(group[IDENTIFIER_COLUMN].nunique(dropna=True)),
                "ambiguity_flag": ambiguity_flag,
            }
        )
    summary = pd.DataFrame(rows).sort_values(
        by=["ambiguity_flag", "target_range", "row_count"],
        ascending=[False, False, False],
        kind="mergesort",
    )
    ambiguous_groups = summary[summary["ambiguity_flag"]]
    overall = {
        "multi_row_formula_groups": int(summary["row_count"].gt(1).sum()),
        "ambiguous_formula_groups": int(summary["ambiguity_flag"].sum()),
        "mixed_zero_positive_formula_groups": int(summary["mixed_zero_positive_status"].eq("mixed_zero_positive").sum()),
        "rows_in_ambiguous_groups": int(ambiguous_groups["row_count"].sum()) if not ambiguous_groups.empty else 0,
        "weighted_within_formula_mae_to_formula_median": float(total_abs_error / total_weight) if total_weight else np.nan,
        "weighted_within_formula_rmse_to_formula_mean": float(math.sqrt(total_sq_error / total_weight)) if total_weight else np.nan,
        "maximum_target_range_within_same_formula": float(summary["target_range"].max()) if not summary.empty else np.nan,
    }
    return summary, overall


def build_target_suitability_summary(analysis_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize target distribution and suitability without transforming target."""
    rows: list[dict[str, Any]] = []
    _append_target_metrics(rows, "overall", analysis_df[TARGET_COLUMN])
    for subgroup_value in [False, True]:
        subgroup = analysis_df[analysis_df["theoretical"].eq(subgroup_value)]
        _append_target_metrics(rows, f"theoretical={subgroup_value}", subgroup[TARGET_COLUMN])
    top_chemsys = analysis_df["chemical_system_group"].value_counts().head(10).index.tolist()
    for chemsys in top_chemsys:
        subgroup = analysis_df[analysis_df["chemical_system_group"].eq(chemsys)]
        _append_target_metrics(rows, f"chemical_system={chemsys}", subgroup[TARGET_COLUMN])
    singleton_mask = analysis_df.groupby("reduced_formula_group")[IDENTIFIER_COLUMN].transform("size").eq(1)
    _append_target_metrics(rows, "reduced_formula_singleton", analysis_df.loc[singleton_mask, TARGET_COLUMN])
    _append_target_metrics(rows, "reduced_formula_multi_row", analysis_df.loc[~singleton_mask, TARGET_COLUMN])
    overall = pd.to_numeric(analysis_df[TARGET_COLUMN], errors="coerce").dropna()
    zero_rate = float((overall == 0).mean()) if len(overall) else np.nan
    variance = float(overall.var(ddof=0)) if len(overall) else np.nan
    rows.extend(
        [
            _target_note("direct_regression_suitability", "conditional" if variance > 0 else "stop", "Direct regression is possible only as a computed-property validation task."),
            _target_note("zero_heavy_concern", "moderate" if zero_rate > 0.1 else "low", "Zero mass is recorded; no transformation or classification label is created in v1.3.3."),
            _target_note("target_transformation_needed", "review_later", "Transformation policy is deferred to modeling design; no transformed target is generated."),
            _target_note("two_stage_modeling_review", "review_later", "Two-stage modeling may be reviewed later because exact-zero and positive values coexist."),
            _target_note("screening_metric_review", "review_later", "Ranking/screening metrics are not selected in v1.3.3."),
        ]
    )
    return pd.DataFrame(rows)


def build_group_inventory(analysis_df: pd.DataFrame) -> pd.DataFrame:
    """Build per-group inventory for formula, chemical-system, and structure groups."""
    rows: list[dict[str, Any]] = []
    for group_type, column in [
        ("reduced_formula_group", "reduced_formula_group"),
        ("chemical_system_group", "chemical_system_group"),
    ]:
        rows.extend(_group_inventory_rows(analysis_df, group_type, column))
    for column in STRUCTURE_GROUPING_COLUMNS:
        if column in analysis_df.columns and analysis_df[column].notna().any():
            rows.extend(_group_inventory_rows(analysis_df, column, column))
    return pd.DataFrame(rows)


def build_split_readiness_summary(
    analysis_df: pd.DataFrame,
    redundancy_summary: pd.DataFrame,
    ambiguity_overall: dict[str, Any],
) -> pd.DataFrame:
    """Build split-readiness metrics without assigning train/test membership."""
    primary_features = primary_feature_columns(analysis_df)
    total_rows = len(analysis_df)
    formula_counts = analysis_df["reduced_formula_group"].value_counts(dropna=False)
    chemsys_counts = analysis_df["chemical_system_group"].value_counts(dropna=False)
    target = pd.to_numeric(analysis_df[TARGET_COLUMN], errors="coerce")
    features_with_missing = int(analysis_df[primary_features].isna().any().sum()) if primary_features else 0
    constant_count = int(sum(analysis_df[col].nunique(dropna=False) <= 1 for col in primary_features))
    near_constant_count = int(sum(_is_near_constant(analysis_df[col]) for col in primary_features))
    high_corr_count = int(
        redundancy_summary["metric"].eq("spearman_abs_ge_0.95").sum()
        if "metric" in redundancy_summary.columns
        else 0
    )
    duplicate_vector_rows = _redundancy_value(redundancy_summary, "duplicate_descriptor_vector_rows")
    random_status = _readiness_status(total_rows >= 100 and target.var(ddof=0) > 0)
    formula_status = _readiness_status(len(formula_counts) >= 5 and formula_counts.max() / total_rows < 0.8)
    chemsys_status = _readiness_status(len(chemsys_counts) >= 5 and chemsys_counts.max() / total_rows < 0.8)
    optional_structure = _structure_split_feasibility(analysis_df)
    stop_reasons: list[str] = []
    if features_with_missing:
        stop_reasons.append("primary descriptors contain missing values")
    if target.var(ddof=0) == 0:
        stop_reasons.append("target variance is zero")
    if formula_status == "stop":
        stop_reasons.append("reduced-formula group split structurally weak")
    if chemsys_status == "stop":
        stop_reasons.append("chemical-system group split structurally weak")
    overall_status = "stop" if stop_reasons else "conditional" if ambiguity_overall["ambiguous_formula_groups"] else "ready"

    rows = [
        _split_metric("total_rows", total_rows),
        _split_metric("descriptor_valid_rows", int(analysis_df["descriptor_quality_status"].eq("valid").sum())),
        _split_metric("descriptor_warning_rows", int(analysis_df["descriptor_quality_status"].eq("warning").sum())),
        _split_metric("descriptor_invalid_rows", int(analysis_df["descriptor_quality_status"].eq("invalid").sum())),
        _split_metric("parse_success_rows", int(analysis_df["composition_parse_status"].eq("parsed").sum())),
        _split_metric("parse_failure_rows", int(analysis_df["composition_parse_status"].eq("failed").sum())),
        _split_metric("primary_feature_count", len(primary_features)),
        _split_metric("features_with_missing_values", features_with_missing),
        _split_metric("constant_feature_count", constant_count),
        _split_metric("near_constant_feature_count", near_constant_count),
        _split_metric("highly_correlated_pair_count", high_corr_count),
        _split_metric("duplicate_descriptor_vector_rows", duplicate_vector_rows),
        _split_metric("reduced_formula_group_count", len(formula_counts)),
        _split_metric("reduced_formula_singleton_count", int((formula_counts == 1).sum())),
        _split_metric("reduced_formula_singleton_rate", float((formula_counts == 1).sum() / len(formula_counts)) if len(formula_counts) else np.nan),
        _split_metric("maximum_formula_group_size", int(formula_counts.max())),
        _split_metric("maximum_formula_group_share", float(formula_counts.max() / total_rows)),
        _split_metric("chemical_system_group_count", len(chemsys_counts)),
        _split_metric("chemical_system_singleton_count", int((chemsys_counts == 1).sum())),
        _split_metric("chemical_system_singleton_rate", float((chemsys_counts == 1).sum() / len(chemsys_counts)) if len(chemsys_counts) else np.nan),
        _split_metric("maximum_chemical_system_group_size", int(chemsys_counts.max())),
        _split_metric("maximum_chemical_system_group_share", float(chemsys_counts.max() / total_rows)),
        _split_metric("ambiguous_formula_group_count", ambiguity_overall["ambiguous_formula_groups"]),
        _split_metric("composition_diagnostic_mae", ambiguity_overall["weighted_within_formula_mae_to_formula_median"]),
        _split_metric("composition_diagnostic_rmse", ambiguity_overall["weighted_within_formula_rmse_to_formula_mean"]),
        _split_metric("target_zero_rate", float(target.eq(0).mean())),
        _split_metric("target_variance", float(target.var(ddof=0))),
        _split_metric("theoretical_false_count", int(analysis_df["theoretical"].eq(False).sum())),
        _split_metric("theoretical_true_count", int(analysis_df["theoretical"].eq(True).sum())),
        _split_metric("random_split_readiness", random_status),
        _split_metric("formula_group_split_readiness", formula_status),
        _split_metric("chemical_system_split_readiness", chemsys_status),
        _split_metric("optional_structure_split_feasibility", optional_structure),
        _split_metric("overall_modeling_readiness", overall_status),
        _split_metric("stop_reasons", ";".join(stop_reasons) if stop_reasons else ""),
    ]
    return pd.DataFrame(rows)


def run_descriptor_pipeline(
    *,
    acquired_path: str | Path,
    manifest_path: str | Path,
    analysis_ready_output: str | Path,
    inventory_output: str | Path,
    redundancy_output: str | Path,
    ambiguity_output: str | Path,
    target_output: str | Path,
    split_output: str | Path,
    group_inventory_output: str | Path,
) -> dict[str, Any]:
    """Run the v1.3.3 descriptor pipeline and write all outputs."""
    input_sha_before = calculate_file_sha256(acquired_path)
    acquired = pd.read_csv(acquired_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    analysis_ready, metadata = build_analysis_ready_table(acquired, manifest)
    inventory = build_descriptor_inventory(analysis_ready, metadata)
    redundancy = build_descriptor_redundancy_summary(analysis_ready, inventory)
    ambiguity, ambiguity_overall = build_composition_ambiguity_summary(analysis_ready)
    target = build_target_suitability_summary(analysis_ready)
    group_inventory = build_group_inventory(analysis_ready)
    split = build_split_readiness_summary(analysis_ready, redundancy, ambiguity_overall)

    _write_csv(analysis_ready, analysis_ready_output)
    _write_csv(inventory, inventory_output)
    _write_csv(redundancy, redundancy_output)
    _write_csv(ambiguity, ambiguity_output)
    _write_csv(target, target_output)
    _write_csv(split, split_output)
    _write_csv(group_inventory, group_inventory_output)
    input_sha_after = calculate_file_sha256(acquired_path)
    if input_sha_before != input_sha_after:
        raise RuntimeError("Source acquired CSV changed during descriptor generation.")

    return {
        **metadata,
        "input_sha256_before": input_sha_before,
        "input_sha256_after": input_sha_after,
        "analysis_ready_output": str(analysis_ready_output),
        "inventory_output": str(inventory_output),
        "redundancy_output": str(redundancy_output),
        "ambiguity_output": str(ambiguity_output),
        "target_output": str(target_output),
        "split_output": str(split_output),
        "group_inventory_output": str(group_inventory_output),
        "redundancy_rows": int(len(redundancy)),
        "high_correlation_pair_count": int(redundancy["metric"].eq("spearman_abs_ge_0.95").sum()),
        "duplicate_descriptor_vector_rows": _redundancy_value(redundancy, "duplicate_descriptor_vector_rows"),
        "ambiguous_formula_group_count": ambiguity_overall["ambiguous_formula_groups"],
        "composition_diagnostic_mae": ambiguity_overall["weighted_within_formula_mae_to_formula_median"],
        "composition_diagnostic_rmse": ambiguity_overall["weighted_within_formula_rmse_to_formula_mean"],
        "target_zero_rate": float(pd.to_numeric(analysis_ready[TARGET_COLUMN]).eq(0).mean()),
        "target_skew": float(pd.to_numeric(analysis_ready[TARGET_COLUMN]).skew()),
        "reduced_formula_group_count": int(analysis_ready["reduced_formula_group"].nunique(dropna=True)),
        "chemical_system_group_count": int(analysis_ready["chemical_system_group"].nunique(dropna=True)),
        "overall_modeling_readiness": str(split.loc[split["metric"].eq("overall_modeling_readiness"), "value"].iloc[0]),
        "output_sizes": {
            str(path): Path(path).stat().st_size
            for path in [
                analysis_ready_output,
                inventory_output,
                redundancy_output,
                ambiguity_output,
                target_output,
                split_output,
                group_inventory_output,
            ]
        },
    }


def _composition_from_value(value: Any) -> Composition | None:
    if value is None or pd.isna(value):
        return None
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        parsed = value
    try:
        if isinstance(parsed, dict):
            cleaned = {str(key): float(amount) for key, amount in parsed.items() if float(amount) > 0}
            return Composition(cleaned) if cleaned else None
        if isinstance(parsed, str) and parsed.strip():
            return Composition(parsed.strip())
    except Exception:
        return None
    return None


def _validate_manifest_shape(df: pd.DataFrame, manifest: dict[str, Any] | None) -> None:
    if not manifest:
        return
    if int(manifest.get("table_row_count", len(df))) != len(df):
        raise ValueError("Acquired CSV row count does not match acquisition manifest.")
    if int(manifest.get("column_count", len(df.columns))) != len(df.columns):
        raise ValueError("Acquired CSV column count does not match acquisition manifest.")


def _element_fractions(composition: Composition) -> dict[str, float]:
    fractional = composition.fractional_composition
    return {
        element.symbol: float(fractional[element])
        for element in sorted(fractional.elements, key=lambda item: item.symbol)
    }


def _element_property_value(element_symbol: str, property_name: str) -> float | None:
    try:
        value = getattr(Element(element_symbol), ELEMENTAL_PROPERTY_SPECS[property_name]["attribute"])
    except Exception:
        return None
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _aggregate_property(
    property_name: str,
    fractions: dict[str, float],
    property_values: dict[str, float | None],
) -> dict[str, float]:
    values = np.array([property_values[element] for element in fractions], dtype=float)
    weights = np.array([fractions[element] for element in fractions], dtype=float)
    weighted_mean = float(np.sum(weights * values))
    return {
        f"{property_name}_weighted_mean": weighted_mean,
        f"{property_name}_minimum": float(np.min(values)),
        f"{property_name}_maximum": float(np.max(values)),
        f"{property_name}_range": float(np.max(values) - np.min(values)),
        f"{property_name}_weighted_std": float(np.sqrt(np.sum(weights * (values - weighted_mean) ** 2))),
    }


def _pairwise_mismatch(
    fractions: dict[str, float],
    property_values: dict[str, float | None],
) -> float:
    elements = list(fractions)
    total = 0.0
    for i, element_i in enumerate(elements):
        for element_j in elements[i + 1 :]:
            value_i = property_values[element_i]
            value_j = property_values[element_j]
            if value_i is None or value_j is None:
                return np.nan
            total += fractions[element_i] * fractions[element_j] * abs(value_i - value_j)
    return float(total)


def _category_fractions(fractions: dict[str, float]) -> dict[str, float]:
    categories = {column: 0.0 for column in CATEGORY_DESCRIPTOR_COLUMNS}
    for element_symbol, fraction in fractions.items():
        element = Element(element_symbol)
        block = str(element.block).lower()
        if block in {"s", "p", "d", "f"}:
            categories[f"{block}_block_fraction"] += fraction
        if bool(element.is_transition_metal):
            categories["transition_metal_fraction"] += fraction
        if bool(element.is_metalloid):
            categories["metalloid_fraction"] += fraction
    return {key: float(value) for key, value in categories.items()}


def _entropy(values: np.ndarray) -> float:
    positive = values[values > 0]
    return float(-np.sum(positive * np.log(positive)))


def _quality_fields(issues: list[str], status: str) -> dict[str, Any]:
    return {
        "descriptor_quality_status": status,
        "descriptor_issue_count": len(issues),
        "descriptor_issues": ";".join(issues),
    }


def _column_descriptor_metadata(column: str) -> tuple[str, str, str, str]:
    if column == IDENTIFIER_COLUMN:
        return "identifier", "metadata", "", ""
    if column == "formula_pretty":
        return "display_metadata", "metadata", "", ""
    if column in GROUPING_COLUMNS:
        return "grouping_metadata", "composition_group", "", ""
    if column in STRUCTURE_GROUPING_COLUMNS:
        return "evaluation_only", "structure_group_feasibility", "", ""
    if column in EVALUATION_ONLY_COLUMNS:
        return "evaluation_only", "evaluation_metadata", "", ""
    if column == TARGET_COLUMN:
        return "target", "computed_property_target", "", ""
    if column.startswith("composition_parse") or column.startswith("descriptor_"):
        return "quality_metadata", "quality", "", ""
    if column in {"derived_element_count", "fraction_sum"}:
        return "quality_metadata", "composition_parse_quality", "", ""
    if column in STOICHIOMETRIC_FEATURES:
        return "primary_descriptor", "stoichiometric", "", ""
    if column in CATEGORY_DESCRIPTOR_COLUMNS:
        return "primary_descriptor", "composition_category_fraction", "", ""
    if column.startswith("pairwise_mismatch_"):
        return "primary_descriptor", "pairwise_mismatch", column.replace("pairwise_mismatch_", ""), "pairwise_mismatch"
    for property_name in ELEMENTAL_PROPERTY_SPECS:
        prefix = f"{property_name}_"
        if column.startswith(prefix):
            return "primary_descriptor", "elemental_aggregation", property_name, column.replace(prefix, "")
    return "metadata", "unknown", "", ""


def _formula_or_definition(column: str, elemental_property: str, aggregation: str) -> str:
    if column == "composition_fraction_entropy":
        return "-sum(x_i * ln(x_i)) for positive fractions."
    if column.startswith("pairwise_mismatch_"):
        return "sum_{i<j} x_i * x_j * abs(p_i - p_j)."
    if elemental_property and aggregation:
        return f"{aggregation} of elemental property {elemental_property} using atomic fractions."
    if column in CATEGORY_DESCRIPTOR_COLUMNS:
        return "Sum of atomic fractions for elements matching this category."
    return "Derived from parsed composition or metadata."


def _property_source(elemental_property: str) -> str:
    return "pymatgen.core.Element" if elemental_property else "derived"


def _property_definition(elemental_property: str) -> str:
    return ELEMENTAL_PROPERTY_SPECS.get(elemental_property, {}).get("definition", "")


def _unit(elemental_property: str, column: str) -> str:
    if elemental_property:
        return ELEMENTAL_PROPERTY_SPECS[elemental_property]["unit"]
    if column == TARGET_COLUMN:
        return "eV/atom"
    if "fraction" in column or "entropy" in column or "l2_norm" in column:
        return "unitless"
    return "unitless"


def _physical_rationale(column: str, family: str) -> str:
    if family == "stoichiometric":
        return "Captures composition balance and concentration spread."
    if family == "elemental_aggregation":
        return "Summarizes element-level physical property distribution by atomic fractions."
    if family == "pairwise_mismatch":
        return "Captures pairwise contrast between constituent element properties."
    if family == "composition_category_fraction":
        return "Captures broad periodic-table block/category makeup."
    if column == TARGET_COLUMN:
        return "Materials Project computed target, not a descriptor."
    return "Metadata or audit field."


def _interpretation_limit(column: str, family: str) -> str:
    if family in {"stoichiometric", "elemental_aggregation", "pairwise_mismatch", "composition_category_fraction"}:
        return "Descriptor is composition-only and does not encode crystal structure, synthesis, or causality."
    if column == TARGET_COLUMN:
        return "Computed stability proxy; not experimental stability."
    return "Use for grouping, quality audit, or interpretation only."


def _quality_note(column: str) -> str:
    if column in FORBIDDEN_FEATURES or column == TARGET_COLUMN:
        return "Not a primary feature."
    if column == "theoretical":
        return "Evaluation subgroup metadata only."
    return ""


def _is_near_constant(series: pd.Series) -> bool:
    counts = series.value_counts(dropna=False)
    if counts.empty:
        return False
    return bool(counts.iloc[0] / len(series) >= 0.99)


def _exact_duplicate_feature_pairs(df: pd.DataFrame, features: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for idx, feature_a in enumerate(features):
        for feature_b in features[idx + 1 :]:
            if df[feature_a].equals(df[feature_b]):
                pairs.append((feature_a, feature_b))
    return pairs


def _redundancy_row(
    metric: str,
    feature_a: str,
    feature_b: str | None,
    family: dict[str, str],
    correlation: float | None,
    severity: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "record_type": "feature_pair" if feature_b else "feature",
        "metric": metric,
        "value": "",
        "feature_a": feature_a,
        "feature_b": feature_b or "",
        "descriptor_family_a": family.get(feature_a, ""),
        "descriptor_family_b": family.get(feature_b, "") if feature_b else "",
        "correlation": correlation,
        "duplicate_status": "exact_duplicate" if metric == "exact_duplicate_feature_pair" else "",
        "severity": severity,
        "recommendation": recommendation,
    }


def _redundancy_metric(metric: str, value: Any, severity: str, recommendation: str) -> dict[str, Any]:
    return {
        "record_type": "metric",
        "metric": metric,
        "value": value,
        "feature_a": "",
        "feature_b": "",
        "descriptor_family_a": "",
        "descriptor_family_b": "",
        "correlation": "",
        "duplicate_status": "",
        "severity": severity,
        "recommendation": recommendation,
    }


def _append_target_metrics(rows: list[dict[str, Any]], scope: str, series: pd.Series) -> None:
    target = pd.to_numeric(series, errors="coerce")
    finite = target[np.isfinite(target)]
    near_zero_threshold = 1e-6
    if finite.empty:
        stats = {name: np.nan for name in ["min", "p01", "p05", "p10", "p25", "median", "p75", "p90", "p95", "p99", "max", "mean", "variance", "standard_deviation", "skewness"]}
        zero_count = near_zero_count = positive_count = outlier_count = 0
    else:
        quantiles = finite.quantile([0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
        stats = {
            "min": float(finite.min()),
            "p01": float(quantiles.loc[0.01]),
            "p05": float(quantiles.loc[0.05]),
            "p10": float(quantiles.loc[0.10]),
            "p25": float(quantiles.loc[0.25]),
            "median": float(quantiles.loc[0.50]),
            "p75": float(quantiles.loc[0.75]),
            "p90": float(quantiles.loc[0.90]),
            "p95": float(quantiles.loc[0.95]),
            "p99": float(quantiles.loc[0.99]),
            "max": float(finite.max()),
            "mean": float(finite.mean()),
            "variance": float(finite.var(ddof=0)),
            "standard_deviation": float(finite.std(ddof=0)),
            "skewness": float(finite.skew()),
        }
        zero_count = int(finite.eq(0).sum())
        near_zero_count = int(finite.abs().le(near_zero_threshold).sum())
        positive_count = int(finite.gt(0).sum())
        iqr = stats["p75"] - stats["p25"]
        upper = stats["p75"] + 3.0 * iqr
        outlier_count = int(finite.gt(upper).sum())
    base = {
        "scope": scope,
        "count": int(len(series)),
        "null_or_nonfinite_count": int(len(series) - len(finite)),
        "zero_count": zero_count,
        "zero_rate": float(zero_count / len(finite)) if len(finite) else np.nan,
        "near_zero_count": near_zero_count,
        "near_zero_rate": float(near_zero_count / len(finite)) if len(finite) else np.nan,
        "positive_count": positive_count,
        "outlier_count": outlier_count,
        "robust_outlier_rule": "value > p75 + 3*IQR",
    }
    for metric, value in {**base, **stats}.items():
        rows.append(
            {
                "scope": scope,
                "metric": metric,
                "value": value,
                "severity": "info",
                "description": "Target suitability diagnostic; no target transformation is applied.",
            }
        )


def _target_note(metric: str, value: str, description: str) -> dict[str, Any]:
    return {
        "scope": "overall_assessment",
        "metric": metric,
        "value": value,
        "severity": "warning" if "review" in value or value == "conditional" else "info",
        "description": description,
    }


def _group_inventory_rows(
    analysis_df: pd.DataFrame,
    group_type: str,
    column: str,
) -> list[dict[str, Any]]:
    counts = analysis_df[column].value_counts(dropna=False)
    dominant_threshold = counts.max() if not counts.empty else 0
    rows: list[dict[str, Any]] = []
    for group_name, group in analysis_df.groupby(column, dropna=False):
        target = pd.to_numeric(group[TARGET_COLUMN], errors="coerce").dropna()
        rows.append(
            {
                "group_type": group_type,
                "group_name": group_name,
                "row_count": int(len(group)),
                "unique_material_id_count": int(group[IDENTIFIER_COLUMN].nunique(dropna=True)),
                "target_min": float(target.min()) if not target.empty else np.nan,
                "target_median": float(target.median()) if not target.empty else np.nan,
                "target_max": float(target.max()) if not target.empty else np.nan,
                "target_variance": float(target.var(ddof=0)) if not target.empty else np.nan,
                "target_zero_count": int(target.eq(0).sum()),
                "theoretical_false_count": int(group["theoretical"].eq(False).sum()),
                "theoretical_true_count": int(group["theoretical"].eq(True).sum()),
                "singleton_flag": bool(len(group) == 1),
                "dominant_group_flag": bool(len(group) == dominant_threshold and dominant_threshold > 1),
            }
        )
    return rows


def _readiness_status(condition: bool) -> str:
    return "ready" if condition else "stop"


def _structure_split_feasibility(analysis_df: pd.DataFrame) -> str:
    if "crystal_system_group" not in analysis_df.columns:
        return "not_available"
    counts = analysis_df["crystal_system_group"].value_counts(dropna=True)
    if len(counts) < 2:
        return "not_enough_structure_groups"
    return json.dumps(
        {
            "crystal_system_group_count": int(len(counts)),
            "max_crystal_system_group_size": int(counts.max()),
            "max_crystal_system_group_share": float(counts.max() / len(analysis_df)),
            "policy": "feasibility_only_no_split_assignment",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _split_metric(metric: str, value: Any) -> dict[str, Any]:
    return {"metric": metric, "value": value}


def _redundancy_value(redundancy_summary: pd.DataFrame, metric: str) -> int:
    if redundancy_summary.empty or "metric" not in redundancy_summary.columns:
        return 0
    matches = redundancy_summary.loc[redundancy_summary["metric"].eq(metric), "value"]
    if matches.empty:
        return 0
    try:
        return int(float(matches.iloc[0]))
    except (TypeError, ValueError):
        return 0


def _safe_int(value: Any) -> int | None:
    try:
        if pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _percentage(count: int, total: int) -> float:
    return round(float(count / total * 100.0), 6) if total else 0.0


def _write_csv(df: pd.DataFrame, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)


def _parse_symmetry_groups(value: Any) -> dict[str, str | pd.NA]:
    if value is None or pd.isna(value):
        return {
            "crystal_system_group": pd.NA,
            "space_group_number_group": pd.NA,
        }
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    crystal_system = parsed.get("crystal_system")
    number = parsed.get("number")
    return {
        "crystal_system_group": str(crystal_system) if crystal_system not in {None, ""} else pd.NA,
        "space_group_number_group": str(number) if number not in {None, ""} else pd.NA,
    }


def contains_credential_or_absolute_path(paths: Iterable[str | Path]) -> dict[str, int]:
    """Scan text outputs for credential-like values or absolute local paths."""
    pattern = re.compile(r"api[_-]?key|token|secret|credential|password|sk-[A-Za-z0-9]|[A-Za-z]:\\|^/Users|^/", re.IGNORECASE | re.MULTILINE)
    result: dict[str, int] = {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        result[str(path)] = len(pattern.findall(text))
    return result
