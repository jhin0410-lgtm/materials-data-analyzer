"""Build a deterministic v2.7.0 public-release candidate closeout.

The audit is offline. It selects a release boundary from tracked evidence but does
not change public version metadata, create tags/releases, rerun scientific
models, or access external data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("configs/v2_7_public_release_candidate.json")
SUMMARY_NAME = "v2_7_public_release_candidate.json"
REPORT_NAME = "v2_7_public_release_candidate.md"
MANIFEST_NAME = "v2_7_public_release_candidate_manifest.json"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
PLATFORM_VERSION = re.compile(
    r'^PLATFORM_VERSION\s*=\s*["\'](\d+\.\d+\.\d+)["\']', re.MULTILINE
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required tracked file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def cff_version(text: str) -> str | None:
    match = re.search(r"^version:\s*[\"']?([^\n\"']+)", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def build_summary(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config = json.loads(read_text(root, str(CONFIG_PATH)))
    candidate = config["candidate_version"]
    if not SEMVER.fullmatch(candidate):
        raise ValueError(f"Invalid candidate version: {candidate}")

    required = [
        *config["required_core_artifacts"],
        *config["required_post_v2_6_artifacts"],
    ]
    missing = [path for path in required if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError(f"Release candidate inputs are missing: {missing}")

    public_version = read_text(root, "PUBLIC_RELEASE_VERSION").strip()
    runtime_match = PLATFORM_VERSION.search(
        read_text(root, "src/platform_core/version.py")
    )
    if runtime_match is None:
        raise ValueError("Unable to parse PLATFORM_VERSION")
    runtime_version = runtime_match.group(1)
    citation_version = cff_version(read_text(root, "CITATION.cff"))

    v25_roadmap = read_text(root, "docs/PLATFORM_V2_5_ROADMAP.md")
    v26_roadmap = read_text(root, "docs/PLATFORM_V2_6_ROADMAP.md")
    closeout_doc = read_text(
        root, "docs/BATTERY_V2_6_EXTERNAL_EVIDENCE_LINE_CLOSEOUT.md"
    )
    closeout = json.loads(
        read_text(
            root,
            "data/processed/battery_v2_6_14_external_evidence_line_closeout_summary.json",
        )
    )
    changelog = read_text(root, "CHANGELOG.md")

    actual_stages = [item["version"] for item in closeout["stage_results"]]
    expected_stages = [f"2.6.{index}" for index in range(1, 14)]
    old_candidate_paths = (
        "configs/v2_6_public_release_candidate.json",
        "scripts/audit_v2_6_public_release_candidate.py",
        "docs/V2_6_PUBLIC_RELEASE_CANDIDATE.md",
        "tests/test_v2_6_public_release_candidate.py",
        ".github/workflows/v2-6-public-release-candidate.yml",
    )
    checks = {
        "current_public_metadata_consistent": (
            public_version
            == runtime_version
            == citation_version
            == config["current_public_version_before_promotion"]
        ),
        "v2_5_feature_line_complete": (
            "v2.5.2_retrieval_reproducibility_feature_stage_complete" in v25_roadmap
            and "compatible_with_restrictions" in v25_roadmap
            and "insufficient_evidence" in v25_roadmap
        ),
        "v2_6_stage_chain_complete": actual_stages == expected_stages,
        "v2_6_closeout_integrity_verified": (
            closeout["decision"]["evidence_line_integrity"] == "verified"
            and closeout["verified_stage_count"] == 13
            and closeout["schema_version"] == "2.6.14"
        ),
        "v2_6_line_explicitly_closed": (
            closeout["next_action"]["v2_6_status"] == "closed"
            and closeout["next_action"]["automatic_next_feature_stage_authorized"]
            is False
            and "v2.6 is closed" in closeout_doc
            and "No automatic v2.6.15" in closeout_doc
        ),
        "post_v2_6_scope_present": all(
            (root / path).is_file()
            for path in config["required_post_v2_6_artifacts"]
        ),
        "negative_results_preserved": (
            closeout["decision"]["ridge_generalization"] == "unsupported"
            and closeout["decision"]["predictive_validation_readiness"]
            == "not_ready"
            and closeout["scientific_closeout"]["status"] == "inconclusive"
        ),
        "no_scientific_reexecution": all(
            closeout[field] is False
            for field in (
                "model_trained",
                "model_evaluated",
                "metrics_recomputed",
                "network_called",
                "cohort_merge_performed",
            )
        ),
        "candidate_release_heading_not_yet_promoted": f"## v{candidate}" not in changelog,
        "candidate_release_notes_not_yet_promoted": not (
            root / f"docs/releases/V{candidate.replace('.', '_')}.md"
        ).is_file(),
        "roadmaps_not_yet_promoted": (
            "current public release" in v25_roadmap
            and "current public release" in v26_roadmap
        ),
        "superseded_v2_6_candidate_removed": not any(
            (root / path).exists() for path in old_candidate_paths
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"Release candidate contract failed: {failed}")

    promotion_actions = [
        "Create a complete v2.7.0 changelog section covering v2.5.1-v2.5.2, v2.6.1-v2.6.14, and all post-v2.6 integration/public-repository work.",
        "Add docs/releases/V2_7_0.md with every Supported, Diagnostic, Inconclusive, Unsupported, blocked, and restricted outcome preserved.",
        "Update PUBLIC_RELEASE_VERSION, PLATFORM_VERSION, and CITATION.cff together to 2.7.0 and add date-released.",
        "Update v2.5 and v2.6 roadmaps to released-within-v2.7.0 and explicitly retain the v2.6.14 line-closeout boundary.",
        "Rerun complete CI, the v2.6.14 checksum closeout, representative NIST workflows, and the pinned cross-repository release-readiness audit.",
        "Create or verify external tags/releases only after the promotion commit is reviewed.",
    ]

    return {
        "schema_version": "1.0",
        "workflow": "v2_7_public_release_candidate_closeout",
        "status": "completed",
        "decision": config["release_decision"],
        "candidate_version": candidate,
        "superseded_candidate_version": config["superseded_candidate_version"],
        "audited_main_commit": config["audited_main_commit"],
        "v2_6_core_closeout_commit": config["v2_6_core_closeout_commit"],
        "post_v2_6_commit_count_at_audit": config[
            "post_v2_6_commit_count_at_audit"
        ],
        "included_internal_stage_versions": config[
            "included_internal_stage_versions"
        ],
        "separate_v2_5_or_v2_6_public_release_authorized": False,
        "version_rationale": (
            "v2.6.14 explicitly closed the internal v2.6 evidence line; the "
            "subsequent integration and public-repository scope is therefore a "
            "distinct additive minor release boundary."
        ),
        "software_validation": {
            "status": "supported",
            "checks": checks,
            "required_inputs_missing": missing,
            "v2_6_stage_count": closeout["verified_stage_count"],
            "v2_6_manifest_checksum": closeout["manifest_checksum"],
            "v2_6_closeout_result_checksum": closeout[
                "deterministic_result_checksum"
            ],
        },
        "scientific_closeout": {
            "status": "inconclusive",
            "ridge_generalization": "unsupported",
            "v2_5_compatibility_software_verdict": "supported",
            "v2_5_provenance_portability": "diagnostic",
            "predictive_validation_readiness": "not_ready",
            "post_v2_6_process_characterization_status": "diagnostic",
            "strongest_evidence": closeout["scientific_closeout"][
                "strongest_evidence"
            ],
            "primary_limitation": closeout["scientific_closeout"][
                "primary_limitation"
            ],
        },
        "public_metadata_promotion_performed": False,
        "tag_or_release_created": False,
        "promotion_actions": promotion_actions,
    }


def build_report(summary: dict[str, Any]) -> str:
    actions = "\n".join(
        f"{index}. {item}"
        for index, item in enumerate(summary["promotion_actions"], 1)
    )
    return f"""# v2.7.0 Public Release Candidate Closeout

## Decision

**{summary['decision']}**

The selected next stable version is **v{summary['candidate_version']}**. The
previous v{summary['superseded_candidate_version']} candidate is superseded.
Internal v2.5.x and v2.6.x labels are included as development history, not
separate public releases.

## Rationale

{summary['version_rationale']}

## Software validation

- v2.6 tracked stages verified: `{summary['software_validation']['v2_6_stage_count']}`
- post-v2.6 commits at audited boundary: `{summary['post_v2_6_commit_count_at_audit']}`
- v2.6 evidence-line integrity: `verified`
- public metadata promotion performed: `{summary['public_metadata_promotion_performed']}`
- tag or release created: `{summary['tag_or_release_created']}`

## Scientific closeout

- overall evidence status: `{summary['scientific_closeout']['status']}`
- Ridge generalization: `{summary['scientific_closeout']['ridge_generalization']}`
- predictive-validation readiness: `{summary['scientific_closeout']['predictive_validation_readiness']}`
- post-v2.6 process-characterization status: `{summary['scientific_closeout']['post_v2_6_process_characterization_status']}`

Software and checksum integrity do not establish cross-cohort comparability,
mechanism, causality, predictive generalization, optimization, or engineering
release readiness.

## Required promotion actions

{actions}
"""


def prepare_output(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Output directory must be new or empty; existing files preserved: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def run(root: Path, output_dir: Path) -> dict[str, Path]:
    prepare_output(output_dir)
    summary = build_summary(root)
    summary_path = output_dir / SUMMARY_NAME
    report_path = output_dir / REPORT_NAME
    manifest_path = output_dir / MANIFEST_NAME
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_path.write_text(build_report(summary), encoding="utf-8")
    outputs = {"summary": summary_path, "report": report_path}
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generation_status": "completed",
                "outputs": {name: path.name for name, path in outputs.items()},
                "output_sha256": {
                    name: sha256_file(path) for name, path in outputs.items()
                },
                "public_metadata_promotion_performed": False,
                "tag_or_release_created": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {**outputs, "manifest": manifest_path}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for name, path in run(args.repo_root, args.output).items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
