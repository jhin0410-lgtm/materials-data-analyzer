from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.cocr_corrosion_scientific_intake import (
    CocrCorrosionScientificIntakeError,
    audit_cocr_corrosion_files,
)

FILES = (
    "EIS CONTROL RAW DATA.xlsx",
    "EIS WEAR RAW DATA.xlsx",
    "lpr control cocr.xlsx",
    "LPR WEAR.xlsx",
    "LPR_Control_Converted.xlsx",
    "PDP CONTROL VS WEAR.xlsx",
)


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = _json(args.episode_root / "cocr_corrosion_episode_summary.json")
        manifest = _json(args.episode_root / "acquisition" / "zenodo_acquisition_manifest.json")
        acquired = summary.get("acquired_files")
        if not isinstance(acquired, list) or len(acquired) != 6:
            raise ValueError("episode summary must bind exactly six acquired files")
        summary_by_key = {item["key"]: item for item in acquired}
        manifest_by_key = {item["key"]: item for item in manifest.get("files", [])}
        if set(summary_by_key) != set(FILES) or set(manifest_by_key) != set(FILES):
            raise ValueError("summary/manifest file set differs from scientific intake contract")
        files: dict[str, bytes] = {}
        for name in FILES:
            body = (args.episode_root / "acquisition" / "files" / name).read_bytes()
            observed_sha = hashlib.sha256(body).hexdigest()
            if summary_by_key[name].get("local_sha256") != observed_sha:
                raise ValueError(f"summary SHA mismatch for {name}")
            if manifest_by_key[name].get("local_sha256") != observed_sha:
                raise ValueError(f"manifest SHA mismatch for {name}")
            files[name] = body
        if manifest.get("scientific_status_changed") is not False:
            raise ValueError("acquisition manifest changed scientific status")
        result = audit_cocr_corrosion_files(files)
        for name, body in files.items():
            if result["initial_intake"]["source_bindings"][name]["sha256"] != hashlib.sha256(body).hexdigest():
                raise ValueError(f"intake source binding mismatch for {name}")
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        CocrCorrosionScientificIntakeError,
    ) as exc:
        print(f"Co-Cr corrosion scientific intake failed closed: {exc}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    _write(args.output / "cocr_initial_intake.json", result["initial_intake"])
    _write(args.output / "cocr_second_pass_reanalysis.json", result["reanalysis"])
    _write(args.output / "cocr_episode_sequence.json", result["episode_sequence"])
    compact = {
        "eis_control_acquisitions": result["initial_intake"]["eis"]["control"]["acquisition_count"],
        "eis_wear_acquisitions": result["initial_intake"]["eis"]["wear"]["acquisition_count"],
        "eis_points_per_acquisition": 56,
        "common_eis_times_h": result["initial_intake"]["eis"]["common_immersion_times_h"],
        "lpr_control_traces": result["initial_intake"]["lpr"]["control"]["trace_count"],
        "lpr_wear_traces": result["initial_intake"]["lpr"]["wear"]["trace_count"],
        "lpr_points_per_trace": 21,
        "common_lpr_times_h": result["initial_intake"]["lpr"]["common_immersion_times_h"],
        "converted_control_potential_shift_v": result["reanalysis"]["exact_conversion_reaudit"]["potential_shift_v"],
        "converted_control_current_factor": result["reanalysis"]["exact_conversion_reaudit"]["current_factor"],
        "converted_control_is_independent_measurement": result["reanalysis"]["exact_conversion_reaudit"]["converted_representation_is_independent_measurement"],
        "replicate_independence_established": result["initial_intake"]["experimental_unit_boundary"]["replicate_independence_established"],
        "full_bounded_research_cycle_completed": result["episode_sequence"]["full_bounded_research_cycle_completed"],
        "initial_report_sha256": result["initial_intake"]["report_sha256"],
        "reanalysis_sha256": result["reanalysis"]["reanalysis_sha256"],
        "sequence_sha256": result["episode_sequence"]["sequence_sha256"],
        "scientific_status_changed": False,
    }
    _write(args.output / "cocr_scientific_intake_summary.json", compact)
    print(json.dumps(compact, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
