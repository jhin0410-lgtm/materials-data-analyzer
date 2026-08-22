"""Downstream-use workflow for legacy and L0-L8 characterization research bundles."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from loaders.characterization_research_bundle import (
    consume_characterization_research_bundle,
    validate_characterization_research_bundle,
)

from .characterization_use_contract import require_characterization_use
from .characterization_use_workflow import _normalized_group_values, _record_eligibility


def _verify_split_group_binding(
    manifest_path: str | Path,
    process_table_path: str | Path | None,
    *,
    split_group_field: str | None,
) -> dict[str, object]:
    if split_group_field is None:
        return {
            "required": False,
            "field": None,
            "source": "not_required",
            "external_values_compared": False,
            "mismatch_count": 0,
        }

    bundle = validate_characterization_research_bundle(manifest_path)
    context = bundle.sample_context.copy()
    if split_group_field not in context.columns:
        raise ValueError(
            "Consumer split group is absent from the checksum-bound bundle sample context: "
            f"{split_group_field}"
        )
    context["sample_id"] = context["sample_id"].astype("string").str.strip()
    context[split_group_field] = _normalized_group_values(
        context[split_group_field],
        field=split_group_field,
        label="Bundle sample context",
    )

    if process_table_path is None:
        return {
            "required": True,
            "field": split_group_field,
            "source": "bundle_sample_context",
            "external_values_compared": False,
            "mismatch_count": 0,
            "sample_count": int(len(context)),
        }

    process_path = Path(process_table_path)
    if process_path.is_symlink():
        raise ValueError("External process table must not be a symbolic link.")
    if not process_path.is_file():
        raise FileNotFoundError(f"External process table not found: {process_path}")
    process = pd.read_csv(process_path)
    if "sample_id" not in process.columns:
        raise ValueError("External process table is missing required sample_id column.")
    process["sample_id"] = process["sample_id"].astype("string").str.strip()
    if (
        process["sample_id"].isna().any()
        or process["sample_id"].eq("").any()
        or process["sample_id"].duplicated().any()
    ):
        raise ValueError(
            "External process table requires non-blank unique sample_id values before "
            "split-group binding can be verified."
        )

    process_ids = set(process["sample_id"].astype(str))
    context_ids = set(context["sample_id"].astype(str))
    if process_ids != context_ids:
        raise ValueError(
            "External process table and bundle sample context sample_id sets must match "
            "exactly before split-group binding can be verified."
        )

    if split_group_field not in process.columns:
        return {
            "required": True,
            "field": split_group_field,
            "source": "bundle_context_injected",
            "external_values_compared": False,
            "mismatch_count": 0,
            "sample_count": int(len(context)),
        }

    process[split_group_field] = _normalized_group_values(
        process[split_group_field],
        field=split_group_field,
        label="External process table",
    )
    compared = process[["sample_id", split_group_field]].merge(
        context[["sample_id", split_group_field]],
        on="sample_id",
        how="inner",
        validate="one_to_one",
        suffixes=("_process", "_bundle"),
        sort=True,
    )
    unequal = ~compared[f"{split_group_field}_process"].eq(
        compared[f"{split_group_field}_bundle"]
    )
    mismatches = compared.loc[unequal, "sample_id"].astype(str).tolist()
    if mismatches:
        preview = ", ".join(mismatches[:20])
        suffix = "..." if len(mismatches) > 20 else ""
        raise ValueError(
            "External process table attempts to redefine the checksum-bound split group "
            f"{split_group_field!r} for sample(s): {preview}{suffix}."
        )
    return {
        "required": True,
        "field": split_group_field,
        "source": "external_process_matches_bundle_context",
        "external_values_compared": True,
        "mismatch_count": 0,
        "sample_count": int(len(compared)),
    }


def consume_characterization_bundle_for_use(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    process_table_path: str | Path | None = None,
    requested_use: str = "descriptive",
    split_group_field: str | None = None,
) -> dict[str, Path]:
    """Gate use, independently validate maturity, consume features, and record both."""
    decision = require_characterization_use(
        manifest_path,
        requested_use=requested_use,
        split_group_field=split_group_field,
    )
    split_group_binding = _verify_split_group_binding(
        manifest_path,
        process_table_path,
        split_group_field=decision.split_group_field,
    )
    outputs = consume_characterization_research_bundle(
        manifest_path,
        output_dir,
        process_table_path=process_table_path,
    )
    return _record_eligibility(outputs, decision, split_group_binding)


__all__ = ["consume_characterization_bundle_for_use"]
