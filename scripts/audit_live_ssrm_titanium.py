from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import materials_data_analyzer.research_loop.ssrm_titanium_scientific_intake as intake
from materials_data_analyzer.research_loop.ssrm_titanium_description_contract import (
    validate_ssrm_description_contract,
)
from materials_data_analyzer.research_loop.ssrm_titanium_logger_contract import (
    audit_ssrm_logger_with_source_unavailable_tokens,
)

ARCHIVE_NAME = "SSRM of Ti, Ti6Al4V, Ti5553.zip"


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
        summary = _json(args.episode_root / "ssrm_titanium_episode_summary.json")
        manifest = _json(
            args.episode_root / "acquisition" / "zenodo_acquisition_manifest.json"
        )
        archive = args.episode_root / "acquisition" / "files" / ARCHIVE_NAME
        body = archive.read_bytes()
        observed_sha = hashlib.sha256(body).hexdigest()
        if observed_sha != summary.get("archive_sha256"):
            raise ValueError("archive SHA-256 differs from episode summary")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) != 1:
            raise ValueError("acquisition manifest must contain one selected archive")
        record = files[0]
        if record.get("local_sha256") != observed_sha:
            raise ValueError("archive SHA-256 differs from acquisition manifest")
        if manifest.get("scientific_status_changed") is not False:
            raise ValueError("acquisition manifest changed scientific status")

        # Both adaptations are source-specific and exact.  The description workbook
        # supplies aliases through same-row file/physical-description pairs, and the
        # Ti logger explicitly uses paired ``**`` tokens for two unavailable P/T rows.
        # Neither path infers sample identity or imputes missing measurements.
        with patch.object(
            intake,
            "_description_contract",
            validate_ssrm_description_contract,
        ), patch.object(
            intake,
            "_logger_audit",
            audit_ssrm_logger_with_source_unavailable_tokens,
        ):
            result = intake.audit_ssrm_titanium_archive(body)
        if result["initial_intake"]["archive_sha256"] != observed_sha:
            raise ValueError("scientific intake is not bound to exact archive bytes")
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        intake.SsrmTitaniumScientificIntakeError,
    ) as exc:
        print(f"SSRM titanium scientific intake failed closed: {exc}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    _write(args.output / "ssrm_initial_intake.json", result["initial_intake"])
    _write(args.output / "ssrm_second_pass_reanalysis.json", result["reanalysis"])
    _write(args.output / "ssrm_episode_sequence.json", result["episode_sequence"])
    compact = {
        "archive_sha256": observed_sha,
        "alias_binding_basis": result["initial_intake"]["description_contract"][
            "alias_binding_basis"
        ],
        "filename_alone_used_as_sample_identity": result["initial_intake"][
            "description_contract"
        ]["filename_alone_used_as_sample_identity"],
        "elemental_condition_count": result["initial_intake"]["elemental_nitrogen"][
            "condition_count"
        ],
        "elemental_source_measurement_rows": result["initial_intake"][
            "elemental_nitrogen"
        ]["source_measurement_rows"],
        "eds_point_count": result["initial_intake"]["eds_line_scan"]["point_count"],
        "raman_offset_copy_pairs": sum(
            item["display_column_pair_count"]
            for item in result["initial_intake"]["raman_processed_representation"].values()
        ),
        "logger_span_hours": {
            material: item["logger_span_hours"]
            for material, item in result["initial_intake"][
                "temperature_pressure_loggers"
            ].items()
        },
        "logger_source_unavailable_pair_rows": {
            material: item["source_unavailable_pair_row_count"]
            for material, item in result["initial_intake"][
                "temperature_pressure_loggers"
            ].items()
        },
        "logger_unavailable_rows_imputed": any(
            item["source_unavailable_rows_interpolated_or_imputed"]
            for item in result["initial_intake"]["temperature_pressure_loggers"].values()
        ),
        "full_bounded_research_cycle_completed": result["episode_sequence"][
            "full_bounded_research_cycle_completed"
        ],
        "initial_report_sha256": result["initial_intake"]["report_sha256"],
        "reanalysis_sha256": result["reanalysis"]["reanalysis_sha256"],
        "sequence_sha256": result["episode_sequence"]["sequence_sha256"],
        "scientific_status_changed": False,
    }
    _write(args.output / "ssrm_scientific_intake_summary.json", compact)
    print(json.dumps(compact, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
