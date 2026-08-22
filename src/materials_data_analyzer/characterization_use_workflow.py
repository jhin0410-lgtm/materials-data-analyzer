"""Public characterization-consumption workflow with downstream-use gating."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from loaders.characterization_bundle import (
    MANIFEST_NAME,
    REPORT_NAME,
    SUMMARY_NAME,
    consume_characterization_bundle,
    validate_characterization_bundle,
)
from loaders.characterization_features import sha256_file

from .characterization_research_gap import (
    build_characterization_research_evidence_gap,
)
from .characterization_use_contract import (
    CharacterizationUseEligibility,
    require_characterization_use,
    write_characterization_use_eligibility,
)

RESEARCH_GAP_FILE_NAME = "characterization_research_evidence_gap.json"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalized_group_values(
    series: pd.Series,
    *,
    field: str,
    label: str,
) -> pd.Series:
    values = series.astype("string").str.strip()
    if values.isna().any() or values.eq("").any():
        raise ValueError(f"{label} contains blank {field} values.")
    return values.astype(str)


def _verify_split_group_binding(
    manifest_path: str | Path,
    process_table_path: str | Path | None,
    *,
    split_group_field: str | None,
) -> dict[str, object]:
    """Protect the producer-declared split group from consumer-side redefinition."""
    if split_group_field is None:
        return {
            "required": False,
            "field": None,
            "source": "not_required",
            "external_values_compared": False,
            "mismatch_count": 0,
        }

    bundle = validate_characterization_bundle(manifest_path)
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
    process_values = compared[f"{split_group_field}_process"]
    bundle_values = compared[f"{split_group_field}_bundle"]
    unequal = ~process_values.eq(bundle_values)
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


def _eligibility_section(
    decision: CharacterizationUseEligibility,
    split_group_binding: dict[str, object],
) -> str:
    warnings = "\n".join(f"- {item}" for item in decision.warnings) or "- None."
    limitations = (
        "\n".join(f"- {item}" for item in decision.limitations) or "- None recorded."
    )
    binding_source = split_group_binding["source"]
    return f"""

## Downstream Use Eligibility

- Requested use: `{decision.requested_use}`
- Maximum allowed use: `{decision.maximum_allowed_use}`
- Policy source: `{decision.policy_source}`
- Eligibility: `allowed`
- Evidence level: `{decision.evidence_level}`
- Feature stage: `{decision.feature_stage}`
- Review status: `{decision.review_status}`
- Declared independence group: `{decision.independence_group_field}`
- Consumer split group: `{decision.split_group_field}`
- Split-group binding source: `{binding_source}`
- Measurement timing: `{decision.measurement_timing}`

### Warnings

{warnings}

### Limitations

{limitations}

Passing this gate does not establish sample comparability, model validity,
causality, extrapolation safety, or engineering-release readiness. When an
independence split is required, its group labels remain bound to the producer's
checksum-verified sample context and cannot be redefined by a consumer process
table.
"""


def _research_gap_section(gap: dict[str, object]) -> str:
    next_requirement = gap.get("next_requirement")
    if isinstance(next_requirement, dict):
        requirement_id = next_requirement.get("requirement_id")
        category = next_requirement.get("category")
        description = next_requirement.get("description")
    else:
        requirement_id = None
        category = None
        description = "No unresolved characterization ladder level remains."
    return f"""

## Autonomous Research Evidence Gap

- Ladder present: `{str(gap['ladder_present']).lower()}`
- Highest contiguous supported level: `{gap['highest_contiguous_supported_level']}`
- First blocking level: `{gap['first_blocking_level']}`
- Next requirement ID: `{requirement_id}`
- Next requirement category: `{category}`
- Gap SHA-256: `{gap['characterization_evidence_gap_sha256']}`
- Scientific status promoted: `{str(gap['scientific_status_promoted']).lower()}`
- Downstream use authorized: `{str(gap['downstream_use_authorized']).lower()}`

{description}

This artifact is a provenance-bound planning requirement, not scientific evidence.
It cannot close the blocker, promote a characterization claim, or bypass the
separate downstream-use and action-authorization boundaries.
"""


def _refresh_consumer_manifest_outputs(
    outputs: dict[str, Path],
    consumer_manifest: dict[str, object],
) -> None:
    manifest_path = outputs["cross_repository_manifest"]
    output_dir = manifest_path.parent
    manifest_outputs = {
        name: path.name
        for name, path in outputs.items()
        if name != "cross_repository_manifest"
    }
    consumer_manifest["outputs"] = manifest_outputs
    consumer_manifest["output_sha256"] = {
        name: sha256_file(output_dir / filename)
        for name, filename in manifest_outputs.items()
    }
    _write_json(manifest_path, consumer_manifest)


def _record_research_gap(
    outputs: dict[str, Path],
    producer_manifest_path: str | Path,
) -> dict[str, Path]:
    summary_path = outputs["cross_repository_summary"]
    report_path = outputs["cross_repository_report"]
    consumer_manifest_path = outputs["cross_repository_manifest"]
    output_dir = summary_path.parent

    bundle = validate_characterization_bundle(producer_manifest_path)
    instruments = sorted(set(bundle.feature_table["instrument"].astype(str)))
    gap = build_characterization_research_evidence_gap(
        bundle_manifest_path=bundle.manifest_path,
        instruments=instruments,
        ladder=bundle.scientific_evidence_ladder,
    )
    gap_path = output_dir / RESEARCH_GAP_FILE_NAME
    if gap_path.exists():
        raise FileExistsError(f"Refusing to overwrite research-gap artifact: {gap_path}")
    _write_json(gap_path, gap)
    outputs["characterization_research_evidence_gap"] = gap_path

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("cross-repository summary must contain a JSON object")
    summary["autonomous_research_evidence_gap"] = gap
    _write_json(summary_path, summary)

    report = report_path.read_text(encoding="utf-8")
    report_path.write_text(
        report.rstrip() + _research_gap_section(gap),
        encoding="utf-8",
    )

    consumer_manifest = json.loads(consumer_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(consumer_manifest, dict):
        raise ValueError("cross-repository manifest must contain a JSON object")
    consumer_manifest["autonomous_research_evidence_gap"] = gap
    _refresh_consumer_manifest_outputs(outputs, consumer_manifest)
    return outputs


def _record_eligibility(
    outputs: dict[str, Path],
    decision: CharacterizationUseEligibility,
    split_group_binding: dict[str, object],
) -> dict[str, Path]:
    summary_path = outputs["cross_repository_summary"]
    report_path = outputs["cross_repository_report"]
    manifest_path = outputs["cross_repository_manifest"]
    output_dir = summary_path.parent

    eligibility_path = write_characterization_use_eligibility(
        output_dir,
        decision,
    )
    outputs["use_eligibility"] = eligibility_path
    eligibility_payload = json.loads(eligibility_path.read_text(encoding="utf-8"))
    if not isinstance(eligibility_payload, dict):
        raise ValueError("characterization use eligibility must contain a JSON object")
    eligibility_payload["split_group_binding"] = split_group_binding
    _write_json(eligibility_path, eligibility_payload)

    decision_payload = decision.to_dict()
    decision_payload["split_group_binding"] = split_group_binding

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("cross-repository summary must contain a JSON object")
    summary["downstream_use_eligibility"] = decision_payload
    _write_json(summary_path, summary)

    report = report_path.read_text(encoding="utf-8")
    report_path.write_text(
        report.rstrip() + _eligibility_section(decision, split_group_binding),
        encoding="utf-8",
    )

    consumer_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(consumer_manifest, dict):
        raise ValueError("cross-repository manifest must contain a JSON object")
    consumer_manifest["downstream_use_eligibility"] = decision_payload
    _refresh_consumer_manifest_outputs(outputs, consumer_manifest)
    return outputs


def consume_characterization_bundle_for_use(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    process_table_path: str | Path | None = None,
    requested_use: str = "descriptive",
    split_group_field: str | None = None,
) -> dict[str, Path]:
    """Gate use, consume evidence, and emit the autonomous next-evidence requirement."""
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
    outputs = consume_characterization_bundle(
        manifest_path,
        output_dir,
        process_table_path=process_table_path,
    )
    outputs = _record_research_gap(outputs, manifest_path)
    return _record_eligibility(outputs, decision, split_group_binding)


__all__ = [
    "MANIFEST_NAME",
    "REPORT_NAME",
    "RESEARCH_GAP_FILE_NAME",
    "SUMMARY_NAME",
    "consume_characterization_bundle_for_use",
]
