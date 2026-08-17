"""Run deterministic Phase A-E autonomous research architecture acceptance.

Phase A replays only trusted NIST discovery/metadata/acquisition bytes. Those bytes are
never treated as scientific measurements. Phases B-E then use the repository's tracked
NIST AM-Bench IN625 case and existing representative workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"
for directory in (SCRIPTS_DIR, SRC_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from run_representative_process_characterization_workflow import (  # noqa: E402
    run_representative_workflow,
)
from materials_data_analyzer.research_loop.autonomous_evidence_loop import (  # noqa: E402
    run_autonomous_evidence_loop,
)
from materials_data_analyzer.research_loop.phase_a_e_acceptance import (  # noqa: E402
    build_phase_a_e_acceptance,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (  # noqa: E402
    FetchResult,
)


def _trust_replay_transport():
    """Replay trusted repository metadata/bytes, never a scientific response dataset."""
    workbook = b"phase-a-trust-replay-xlsx-placeholder-bytes"
    readme = b"phase-a-trust-replay-readme"
    metadata = json.dumps(
        {
            "@id": "ark:/88434/mds2-2923",
            "ediid": "mds2-2923",
            "accessLevel": "public",
            "version": "1.0",
            "components": [
                {
                    "@type": ["nrdp:DataFile"],
                    "filepath": "Master_TrackList_Measurements.xlsx",
                    "downloadURL": (
                        "https://data.nist.gov/od/ds/mds2-2923/"
                        "Master_TrackList_Measurements.xlsx"
                    ),
                    "size": len(workbook),
                    "checksum": {
                        "hash": hashlib.sha256(workbook).hexdigest(),
                        "algorithm": {"tag": "sha256"},
                    },
                },
                {
                    "@type": ["nrdp:DataFile"],
                    "filepath": "2923_README.txt",
                    "downloadURL": (
                        "https://data.nist.gov/od/ds/mds2-2923/2923_README.txt"
                    ),
                    "size": len(readme),
                    "checksum": {
                        "hash": hashlib.sha256(readme).hexdigest(),
                        "algorithm": {"tag": "sha256"},
                    },
                },
            ],
        },
        sort_keys=True,
    ).encode("utf-8")
    discovery = json.dumps(
        {
            "ResultCount": 1,
            "PageSize": 1,
            "ResultData": [
                {
                    "@id": "ark:/88434/mds2-2923",
                    "ediid": "mds2-2923",
                    "@type": ["nrdp:PublicDataResource"],
                    "accessLevel": "public",
                    "title": "IN625 single-track melt pool measurements",
                    "description": "laser powder bed fusion melt pool width",
                }
            ],
        },
        sort_keys=True,
    ).encode("utf-8")

    def fetcher(url: str, **kwargs):
        del kwargs
        if url.startswith("https://data.nist.gov/rmm/records?"):
            return FetchResult(discovery, 200, url, "application/json")
        if url == "https://data.nist.gov/od/id/mds2-2923":
            return FetchResult(metadata, 200, url, "application/json")
        if url.endswith("Master_TrackList_Measurements.xlsx"):
            return FetchResult(workbook, 200, url, "application/octet-stream")
        if url.endswith("2923_README.txt"):
            return FetchResult(readme, 200, url, "text/plain")
        raise AssertionError(f"unexpected replay URL: {url}")

    return fetcher


def _prepare_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(
            f"Phase A-E acceptance output must be new or empty: {path}"
        )
    path.mkdir(parents=True, exist_ok=True)


def run_acceptance(output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    _prepare_output(output)
    phase_a_dir = output / "00_phase_a_trust_replay"
    representative_dir = output / "01_real_in625_representative_workflow"
    acceptance_dir = output / "02_phase_a_e_acceptance"

    phase_a_result = run_autonomous_evidence_loop(
        {"material": "IN625", "measurement": "melt pool measurements"},
        output_root=phase_a_dir,
        fetcher=_trust_replay_transport(),
        max_iterations=2,
        max_records_per_iteration=1,
        max_files_per_product=2,
    )
    run_representative_workflow(representative_dir)
    acceptance = build_phase_a_e_acceptance(
        phase_a_result=phase_a_result,
        representative_root=representative_dir,
        repository_root=PROJECT_ROOT,
        output_dir=acceptance_dir,
    )
    run_manifest = output / "phase_a_e_acceptance_run_manifest.json"
    run_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "workflow": "phase_a_e_autonomous_research_acceptance",
                "network_access_performed": False,
                "phase_a_replay_is_scientific_measurement": False,
                "representative_case_uses_tracked_real_nist_rows": True,
                "acceptance_outputs": {
                    name: str(path.relative_to(output))
                    for name, path in acceptance.items()
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {**acceptance, "run_manifest": run_manifest}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        required=True,
        help="New or empty output directory for the deterministic acceptance run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = run_acceptance(args.output)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Phase A-E acceptance failed: {exc}", file=sys.stderr)
        return 1
    print("Phase A-E autonomous research acceptance completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
