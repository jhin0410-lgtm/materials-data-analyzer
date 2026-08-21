"""Public characterization-to-research workflow for the autonomous scientist.

This composes the existing downstream-use gate with independent L0-L8 replay and a
provenance-bound research evidence-gap artifact. The gap is planning context only;
execution still requires the existing research-loop authorization boundary.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loaders.characterization_bundle import validate_characterization_bundle
from loaders.characterization_evidence_ladder import (
    validate_characterization_evidence_ladder,
)
from loaders.characterization_features import sha256_file

from .characterization_use_workflow import consume_characterization_bundle_for_use
from .research_loop.characterization_evidence_gap import (
    build_characterization_evidence_gap,
)

LADDER_STATE_NAME = "characterization_evidence_ladder_state.json"
EVIDENCE_GAP_NAME = "characterization_research_evidence_gap.json"
WORKFLOW_SCHEMA_VERSION = "1.0"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _report_section(
    ladder_state: dict[str, Any],
    evidence_gap: dict[str, Any] | None,
) -> str:
    if ladder_state["present"]:
        highest = ladder_state["state"]["highest_contiguous_supported_level"]
        blocker = ladder_state["state"]["first_blocking_level"]
        gap_status = evidence_gap["status"] if evidence_gap is not None else "unavailable"
        gap_code = (
            evidence_gap["gap"]["requirement_code"]
            if evidence_gap is not None and evidence_gap["gap"] is not None
            else "none"
        )
    else:
        highest = "not_declared"
        blocker = "not_declared"
        gap_status = "not_constructed_without_ladder"
        gap_code = "none"
    return f"""

## Autonomous Research Scientist Evidence State

- Characterization evidence ladder present: `{str(ladder_state['present']).lower()}`
- Highest contiguous supported level: `{highest}`
- First blocking level: `{blocker}`
- Research evidence-gap status: `{gap_status}`
- Next evidence requirement: `{gap_code}`
- Scientific status promoted by this workflow: `false`
- Downstream use authorized by the ladder: `false`
- Action execution authorized by the gap artifact: `false`

When present, the L0-L8 assessment is independently replayed from its declaration
without importing the producer implementation. The assessment is then cross-bound
to the bundle case, evidence-file SHA-256 values, and represented modality. The
first blocking level is converted into a deterministic planning requirement only.
It is not empirical evidence and cannot bypass the existing research-loop
authorization boundary.
"""


def consume_characterization_bundle_for_autonomous_research(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    process_table_path: str | Path | None = None,
    requested_use: str = "descriptive",
    split_group_field: str | None = None,
) -> dict[str, Path]:
    """Consume characterization evidence and emit a research-planning gap artifact."""
    bundle = validate_characterization_bundle(manifest_path)
    instruments = sorted(set(bundle.feature_table["instrument"].astype(str)))
    ladder = validate_characterization_evidence_ladder(
        manifest=bundle.manifest,
        bundle_root=bundle.manifest_path.resolve().parent,
        evidence_paths=bundle.evidence_paths,
        instruments=instruments,
    )

    outputs = consume_characterization_bundle_for_use(
        manifest_path,
        output_dir,
        process_table_path=process_table_path,
        requested_use=requested_use,
        split_group_field=split_group_field,
    )
    output = Path(output_dir)

    ladder_state = {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "artifact_type": "characterization_evidence_ladder_state",
        "present": ladder is not None,
        "state": ladder,
        "scientific_boundary": {
            "empirical_evidence_created": False,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
        },
    }
    ladder_state_path = output / LADDER_STATE_NAME
    _write_json(ladder_state_path, ladder_state)
    outputs["characterization_evidence_ladder_state"] = ladder_state_path

    evidence_gap: dict[str, Any] | None = None
    if ladder is not None:
        evidence_gap = build_characterization_evidence_gap(ladder)
        evidence_gap_path = output / EVIDENCE_GAP_NAME
        _write_json(evidence_gap_path, evidence_gap)
        outputs["characterization_research_evidence_gap"] = evidence_gap_path

    summary_path = outputs["cross_repository_summary"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("cross-repository summary must contain a JSON object")
    summary["autonomous_research_scientist"] = {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "characterization_evidence_ladder": ladder_state,
        "characterization_research_evidence_gap": evidence_gap,
        "planning_boundary": {
            "empirical_evidence_created": False,
            "scientific_status_promoted": False,
            "downstream_use_authorized_by_ladder": False,
            "action_execution_authorized_by_gap": False,
            "existing_research_loop_authorization_required": True,
        },
    }
    _write_json(summary_path, summary)

    report_path = outputs["cross_repository_report"]
    report_path.write_text(
        report_path.read_text(encoding="utf-8").rstrip()
        + _report_section(ladder_state, evidence_gap),
        encoding="utf-8",
    )

    manifest_output = outputs["cross_repository_manifest"]
    consumer_manifest = json.loads(manifest_output.read_text(encoding="utf-8"))
    if not isinstance(consumer_manifest, dict):
        raise ValueError("cross-repository manifest must contain a JSON object")
    consumer_manifest["autonomous_research_scientist"] = {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "characterization_evidence_ladder": ladder_state,
        "characterization_research_evidence_gap": evidence_gap,
        "planning_boundary": summary["autonomous_research_scientist"]["planning_boundary"],
    }
    manifest_outputs = {
        name: path.name
        for name, path in outputs.items()
        if name != "cross_repository_manifest"
    }
    consumer_manifest["outputs"] = manifest_outputs
    consumer_manifest["output_sha256"] = {
        name: sha256_file(output / filename)
        for name, filename in manifest_outputs.items()
    }
    _write_json(manifest_output, consumer_manifest)
    return outputs


__all__ = [
    "EVIDENCE_GAP_NAME",
    "LADDER_STATE_NAME",
    "WORKFLOW_SCHEMA_VERSION",
    "consume_characterization_bundle_for_autonomous_research",
]
