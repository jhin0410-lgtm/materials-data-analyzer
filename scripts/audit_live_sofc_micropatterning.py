from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.sofc_micropatterning_scientific_intake import (
    SofcMicropatterningScientificIntakeError,
    audit_sofc_micropatterning_archive,
)

ARCHIVE_NAME = "Dataset.zip"
README_NAME = "readme.txt"


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = _json(args.episode_root / "sofc_micropatterning_episode_summary.json")
        manifest = _json(args.episode_root / "acquisition" / "zenodo_acquisition_manifest.json")
        archive = args.episode_root / "acquisition" / "files" / ARCHIVE_NAME
        readme = args.episode_root / "acquisition" / "files" / README_NAME
        archive_body = archive.read_bytes()
        readme_body = readme.read_bytes()
        archive_sha = hashlib.sha256(archive_body).hexdigest()
        readme_sha = hashlib.sha256(readme_body).hexdigest()
        if summary.get("archive_sha256") != archive_sha:
            raise ValueError("archive SHA differs from episode summary")
        if summary.get("readme_sha256") != readme_sha:
            raise ValueError("README SHA differs from episode summary")
        manifest_by_key = {item["key"]: item for item in manifest.get("files", [])}
        if set(manifest_by_key) != {ARCHIVE_NAME, README_NAME}:
            raise ValueError("acquisition manifest file set differs from SOFC contract")
        if manifest_by_key[ARCHIVE_NAME].get("local_sha256") != archive_sha:
            raise ValueError("archive SHA differs from acquisition manifest")
        if manifest_by_key[README_NAME].get("local_sha256") != readme_sha:
            raise ValueError("README SHA differs from acquisition manifest")
        if manifest.get("scientific_status_changed") is not False:
            raise ValueError("acquisition manifest changed scientific status")
        result = audit_sofc_micropatterning_archive(archive_body)
        if result["initial_intake"]["archive_sha256"] != archive_sha:
            raise ValueError("scientific intake is not bound to exact archive bytes")
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        SofcMicropatterningScientificIntakeError,
    ) as exc:
        print(f"SOFC micropatterning scientific intake failed closed: {exc}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    _write(args.output / "sofc_initial_intake.json", result["initial_intake"])
    _write(args.output / "sofc_second_pass_reanalysis.json", result["reanalysis"])
    _write(args.output / "sofc_episode_sequence.json", result["episode_sequence"])
    compact = {
        "archive_sha256": archive_sha,
        "iv_numeric_point_counts": {
            key: item["numeric_point_count"]
            for key, item in result["initial_intake"]["raw_iv"]["conditions"].items()
        },
        "descriptive_peak_power_density_w_cm2": {
            key: item["descriptive_peak_power_density_w_cm2"]
            for key, item in result["initial_intake"]["raw_iv"]["conditions"].items()
        },
        "ocv_time_samples_per_condition": 18000,
        "impedance_raw_points_per_condition": result["initial_intake"]["raw_impedance"][
            "frequency_grid_point_count"
        ],
        "iv_summary_stale_column_anomaly": result["reanalysis"]["iv_summary_reconciliation"][
            "stale_column_anomaly"
        ],
        "iv_summary_information_truncation_present": result["reanalysis"][
            "iv_summary_reconciliation"
        ]["information_truncation_present"],
        "fit_identifiability_warning_present": result["reanalysis"][
            "a_r_equivalent_circuit_fitting"
        ]["fit_identifiability_warning_present"],
        "independent_cell_or_specimen_ids_present": result["initial_intake"][
            "experimental_unit_boundary"
        ]["independent_cell_or_specimen_ids_present"],
        "sem_to_electrochemistry_cell_join_recovered": result["reanalysis"][
            "cell_lineage_reaudit"
        ]["sem_to_electrochemistry_cell_join_recovered"],
        "full_bounded_research_cycle_completed": result["episode_sequence"][
            "full_bounded_research_cycle_completed"
        ],
        "initial_report_sha256": result["initial_intake"]["report_sha256"],
        "reanalysis_sha256": result["reanalysis"]["reanalysis_sha256"],
        "sequence_sha256": result["episode_sequence"]["sequence_sha256"],
        "scientific_status_changed": False,
    }
    _write(args.output / "sofc_scientific_intake_summary.json", compact)
    print(json.dumps(compact, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
