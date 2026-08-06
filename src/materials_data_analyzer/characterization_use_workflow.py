"""Public characterization-consumption workflow with downstream-use gating."""
from __future__ import annotations

import json
from pathlib import Path

from loaders.characterization_bundle import (
    MANIFEST_NAME,
    REPORT_NAME,
    SUMMARY_NAME,
    consume_characterization_bundle,
)
from loaders.characterization_features import sha256_file

from .characterization_use_contract import (
    CharacterizationUseEligibility,
    require_characterization_use,
    write_characterization_use_eligibility,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _eligibility_section(decision: CharacterizationUseEligibility) -> str:
    warnings = "\n".join(f"- {item}" for item in decision.warnings) or "- None."
    limitations = (
        "\n".join(f"- {item}" for item in decision.limitations) or "- None recorded."
    )
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
- Measurement timing: `{decision.measurement_timing}`

### Warnings

{warnings}

### Limitations

{limitations}

Passing this gate does not establish sample comparability, model validity,
causality, extrapolation safety, or engineering-release readiness.
"""


def _record_eligibility(
    outputs: dict[str, Path],
    decision: CharacterizationUseEligibility,
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
    decision_payload = decision.to_dict()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("cross-repository summary must contain a JSON object")
    summary["downstream_use_eligibility"] = decision_payload
    _write_json(summary_path, summary)

    report = report_path.read_text(encoding="utf-8")
    report_path.write_text(
        report.rstrip() + _eligibility_section(decision),
        encoding="utf-8",
    )

    consumer_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(consumer_manifest, dict):
        raise ValueError("cross-repository manifest must contain a JSON object")
    consumer_manifest["downstream_use_eligibility"] = decision_payload
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
    return outputs


def consume_characterization_bundle_for_use(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    process_table_path: str | Path | None = None,
    requested_use: str = "descriptive",
    split_group_field: str | None = None,
) -> dict[str, Path]:
    """Gate intended use, consume the bundle, and preserve the decision in outputs."""
    decision = require_characterization_use(
        manifest_path,
        requested_use=requested_use,
        split_group_field=split_group_field,
    )
    outputs = consume_characterization_bundle(
        manifest_path,
        output_dir,
        process_table_path=process_table_path,
    )
    return _record_eligibility(outputs, decision)


__all__ = [
    "MANIFEST_NAME",
    "REPORT_NAME",
    "SUMMARY_NAME",
    "consume_characterization_bundle_for_use",
]
