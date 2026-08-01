"""File-system wrapper for Battery Intelligence comparability audits."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .common import BatteryIntelligenceConfig, canonical_json, file_sha256
from .target_comparability import (
    _audit_markdown,
    _update_closeout,
    build_target_comparability_audit,
)


def _config_from_snapshot(path: Path) -> BatteryIntelligenceConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = dict(payload["config"])
    if "lags" in values:
        values["lags"] = tuple(int(value) for value in values["lags"])
    return BatteryIntelligenceConfig(**values)


def audit_battery_intelligence_run(output_dir: str | Path) -> dict[str, Any]:
    """Audit an existing Battery Intelligence output directory in place."""
    output = Path(output_dir)
    tables = output / "tables"
    reports = output / "reports"
    required = {
        "validated_cycle_summary": tables / "validated_cycle_summary.csv",
        "forecast_feature_table": tables / "forecast_feature_table.csv",
        "validation_predictions": tables / "validation_predictions.csv",
        "config_snapshot": output / "config_snapshot.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "battery run is missing required audit artifacts: " + ", ".join(missing)
        )

    config = _config_from_snapshot(required["config_snapshot"])
    audit = build_target_comparability_audit(
        cycle_summary=pd.read_csv(required["validated_cycle_summary"]),
        forecast_table=pd.read_csv(required["forecast_feature_table"]),
        predictions=pd.read_csv(required["validation_predictions"]),
        config=config,
    )
    target_path = tables / "target_integrity_by_battery.csv"
    error_path = tables / "error_concentration_by_battery.csv"
    report_path = reports / "target_comparability_audit.json"
    markdown_path = reports / "target_comparability_audit.md"
    audit["target_integrity_by_battery"].to_csv(target_path, index=False)
    audit["error_concentration_by_battery"].to_csv(error_path, index=False)
    report_path.write_text(canonical_json(audit["summary"]), encoding="utf-8")
    markdown_path.write_text(_audit_markdown(audit["summary"]), encoding="utf-8")
    _update_closeout(output, audit["summary"])

    manifest_path = output / "run_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["target_comparability_audit"] = audit["summary"]
        relative_paths = [
            target_path.relative_to(output).as_posix(),
            error_path.relative_to(output).as_posix(),
            report_path.relative_to(output).as_posix(),
            markdown_path.relative_to(output).as_posix(),
            (reports / "scientific_closeout.json").relative_to(output).as_posix(),
            (reports / "scientific_closeout.md").relative_to(output).as_posix(),
        ]
        artifact_paths = set(manifest.get("artifact_paths", []))
        artifact_paths.update(relative_paths)
        manifest["artifact_paths"] = sorted(artifact_paths)
        checksums = dict(manifest.get("artifact_checksums", {}))
        for relative in relative_paths:
            path = output / relative
            if path.is_file():
                checksums[relative] = file_sha256(path)
        manifest["artifact_checksums"] = checksums
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8")

    return {
        "summary": audit["summary"],
        "outputs": {
            "target_integrity_by_battery": str(target_path),
            "error_concentration_by_battery": str(error_path),
            "target_comparability_audit": str(report_path),
            "target_comparability_markdown": str(markdown_path),
        },
    }
