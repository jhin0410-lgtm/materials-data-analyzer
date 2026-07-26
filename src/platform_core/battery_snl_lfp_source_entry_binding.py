from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

VERSION = "2.6.7"
PACKAGE_ID = "battery_snl_lfp_source_entry_binding_review_v1"
DEFAULT_CONFIG_PATH = "configs/examples/battery_snl_lfp_source_entry_binding_review.json"
DEFAULT_MANIFEST_PATH = "data/platform/battery_snl_lfp_source_entry_binding_manifest_v1.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_6_battery_snl_lfp_source_entry_binding"
DEFAULT_TRACKED_SUMMARY = "data/processed/battery_v2_6_7_snl_lfp_source_entry_binding_summary.json"
V265_SUMMARY = "data/processed/battery_v2_6_5_snl_lfp_source_evidence_summary.json"
V266_SUMMARY = "data/processed/battery_v2_6_6_snl_lfp_artifact_binding_summary.json"
EXPECTED_ARCHIVE_SHA256 = "006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d"
EXPECTED_ENTRY_MANIFEST_CHECKSUM = "f85e6f1ac333f7ff20b7bfd01b8599cfe86e8950c4971e9fc074a367da86a75c"
EVIDENCE_FIELDS = (
    "chemistry", "nominal_capacity", "ambient_temperature", "charge_protocol",
    "discharge_protocol", "cutoff_voltage", "measurement_calibration", "source_snapshot",
)
BINDING_DIMENSIONS = (
    "publication_to_repository", "repository_filename_nomenclature",
    "study_to_condition_group", "condition_group_to_entry_pattern",
    "physical_cell_to_entry", "cycle_command_to_rows",
    "instrument_channel_to_columns", "official_distribution_snapshot",
)
SOURCE_IDS = (
    "battery_archive_snl_study_page", "battery_archive_metadata_rules",
    "battery_archive_access_policy", "osti_1650174_article_record",
    "sandia_sand2020_8433j_record",
)
FALSE_FLAGS = (
    "network_called", "credentials_read", "raw_archive_read", "archives_extracted",
    "entry_payloads_read", "csv_headers_read", "csv_rows_read",
    "source_mutation_performed", "model_trained", "model_evaluated",
    "metrics_recomputed", "data_inference_performed",
    "physical_cell_binding_inferred", "cycle_command_binding_inferred",
    "instrument_channel_binding_inferred", "official_snapshot_inferred",
    "filename_labels_promoted_to_measurements",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_checksum(payload: Any) -> str:
    core = dict(payload) if isinstance(payload, Mapping) else payload
    if isinstance(core, dict):
        core.pop("deterministic_result_checksum", None)
    raw = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _relative(name: str, value: Any) -> str:
    text = str(value).replace("\\", "/")
    path = Path(text)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", text) or ".." in path.parts:
        raise ValueError(f"{name} must be repository-relative and non-traversing")
    return path.as_posix()


def repo_path(root: str | Path, value: str | Path) -> Path:
    base, target = Path(root).resolve(), (Path(root) / value).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value}") from exc
    return target


@dataclass(frozen=True)
class ReviewConfig:
    case_study_id: str
    bounded_source_id: str
    manifest_path: str
    v2_6_5_summary_path: str
    v2_6_6_summary_path: str
    expected_v2_6_5_checksum: str
    expected_v2_6_6_checksum: str
    output_root: str
    tracked_summary_path: str

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "ReviewConfig":
        required = {
            "schema_version", "package_id", "case_study_id", "bounded_source_id",
            "source_entry_binding_manifest_path", "v2_6_5_source_evidence_summary_path",
            "v2_6_6_artifact_binding_summary_path", "expected_v2_6_5_checksum",
            "expected_v2_6_6_checksum", "required_evidence_fields",
            "required_binding_dimensions", "read_policy", "credential_policy",
            "output_root", "tracked_summary_path", "output_policy", "dry_run",
        }
        if set(p) != required:
            raise ValueError("config fields changed")
        if p["schema_version"] != VERSION or p["package_id"] != PACKAGE_ID:
            raise ValueError("unsupported source-to-entry binding package")
        if tuple(p["required_evidence_fields"]) != EVIDENCE_FIELDS:
            raise ValueError("evidence field contract changed")
        if tuple(p["required_binding_dimensions"]) != BINDING_DIMENSIONS:
            raise ValueError("binding dimension contract changed")
        if p["read_policy"] != {
            "allow_tracked_json_reads": True, "allow_raw_archive_read": False,
            "allow_entry_payload_read": False, "allow_csv_header_read": False,
            "allow_csv_row_read": False, "allow_archive_extraction": False,
        }:
            raise ValueError("read policy changed")
        if p["credential_policy"] != {"store_credentials": False, "network_access_required": False}:
            raise ValueError("credential policy changed")
        if p["output_policy"] != "tracked_compact_summary_and_local_full_result" or p["dry_run"] is not True:
            raise ValueError("output policy changed")
        checks = (str(p["expected_v2_6_5_checksum"]), str(p["expected_v2_6_6_checksum"]))
        if not all(HEX64.fullmatch(x) for x in checks):
            raise ValueError("expected source checksums must be SHA-256")
        paths = {key: _relative(key, p[key]) for key in (
            "source_entry_binding_manifest_path", "v2_6_5_source_evidence_summary_path",
            "v2_6_6_artifact_binding_summary_path", "output_root", "tracked_summary_path",
        )}
        if paths != {
            "source_entry_binding_manifest_path": DEFAULT_MANIFEST_PATH,
            "v2_6_5_source_evidence_summary_path": V265_SUMMARY,
            "v2_6_6_artifact_binding_summary_path": V266_SUMMARY,
            "output_root": DEFAULT_OUTPUT_ROOT,
            "tracked_summary_path": DEFAULT_TRACKED_SUMMARY,
        }:
            raise ValueError("bounded paths changed")
        return cls(
            str(p["case_study_id"]), str(p["bounded_source_id"]), DEFAULT_MANIFEST_PATH,
            V265_SUMMARY, V266_SUMMARY, checks[0], checks[1],
            DEFAULT_OUTPUT_ROOT, DEFAULT_TRACKED_SUMMARY,
        )


def load_config(path: str | Path = DEFAULT_CONFIG_PATH, repo_root: str | Path = ".") -> ReviewConfig:
    return ReviewConfig.from_dict(_json(repo_path(repo_root, path)))


def _verify_summary(payload: Mapping[str, Any], expected: str, version: str) -> None:
    checksum = payload.get("deterministic_result_checksum")
    if checksum != expected or checksum != canonical_checksum(payload):
        raise ValueError(f"v{version} source summary checksum mismatch")


def preservation(v265: Mapping[str, Any], v266: Mapping[str, Any], c: ReviewConfig) -> dict[str, Any]:
    _verify_summary(v265, c.expected_v2_6_5_checksum, "2.6.5")
    _verify_summary(v266, c.expected_v2_6_6_checksum, "2.6.6")
    if v265.get("recovery_decision", {}).get("overall_status") != "source_evidence_recovered_gate_not_passed":
        raise ValueError("v2.6.5 boundary changed")
    if v266.get("binding_decision", {}).get("overall_status") != "local_artifact_inventory_bound_gate_not_passed":
        raise ValueError("v2.6.6 boundary changed")
    audit = v266.get("archive_audit", {})
    if audit.get("archive_sha256") != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("bounded archive identity changed")
    if audit.get("entry_manifest_checksum") != EXPECTED_ENTRY_MANIFEST_CHECKSUM:
        raise ValueError("entry-manifest identity changed")
    if audit.get("inventory", {}).get("inventory_contract_match") is not True:
        raise ValueError("inventory contract changed")
    metrics = v265.get("preservation_checks", {}).get("preserved_metrics")
    expected_metrics = [
        {"mae": 3.425575369058076, "model": "persistence"},
        {"mae": 4.15369918179312, "model": "ridge"},
    ]
    if metrics != expected_metrics:
        raise ValueError("preserved model metrics changed")
    return {
        "v2_6_5_checksum_verified": True, "v2_6_6_checksum_verified": True,
        "archive_identity_verified": True, "entry_manifest_identity_verified": True,
        "inventory_contract_preserved": True,
        "prior_v2_6_5_status": "source_evidence_recovered_gate_not_passed",
        "prior_v2_6_6_status": "local_artifact_inventory_bound_gate_not_passed",
        "prior_boundaries_preserved": True, "model_metrics_unchanged": True,
        "model_or_metric_change_performed": False, "preserved_metrics": metrics,
    }


def validate_manifest(m: Mapping[str, Any], c: ReviewConfig) -> None:
    required = {
        "schema_version", "manifest_id", "bounded_source_id", "review_recorded_on",
        "review_scope", "archive_identity", "source_register", "binding_dimensions",
        "condition_group_bindings", "evidence_field_assessments", "claim_policy",
    }
    if set(m) != required or m["schema_version"] != "1":
        raise ValueError("binding manifest fields changed")
    if m["manifest_id"] != "battery_snl_lfp_source_entry_binding_manifest_v1":
        raise ValueError("binding manifest identity changed")
    if m["bounded_source_id"] != c.bounded_source_id:
        raise ValueError("bounded source changed")
    identity = m["archive_identity"]
    if identity.get("archive_sha256") != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("manifest archive checksum changed")
    if identity.get("entry_manifest_checksum") != EXPECTED_ENTRY_MANIFEST_CHECKSUM:
        raise ValueError("manifest entry checksum changed")
    if identity.get("observed_entry_count") != 60 or identity.get("observed_cell_pair_count") != 30:
        raise ValueError("manifest inventory totals changed")
    if identity.get("row_level_manifest_committed") is not False:
        raise ValueError("row-level manifest may not be committed")
    if identity.get("provider_published_archive_checksum") is not False:
        raise ValueError("provider checksum was silently claimed")
    if identity.get("provider_versioned_distribution_id") is not None:
        raise ValueError("provider distribution ID was silently claimed")

    sources = m["source_register"]
    if tuple(x.get("source_id") for x in sources) != SOURCE_IDS:
        raise ValueError("source register changed")
    if any(x.get("versioned_dataset_snapshot") is not False for x in sources):
        raise ValueError("source document was promoted to a snapshot")
    if any(x.get("official_archive_checksum_published") is not False for x in sources):
        raise ValueError("official archive checksum was silently claimed")

    dimensions = m["binding_dimensions"]
    if tuple(x.get("dimension") for x in dimensions) != BINDING_DIMENSIONS:
        raise ValueError("binding dimensions changed")
    allowed = {"established", "established_condition_group_only",
               "established_repository_nomenclature_only", "not_established"}
    known_sources = set(SOURCE_IDS)
    for row in dimensions:
        if row.get("status") not in allowed:
            raise ValueError("unsupported binding status")
        if not set(row.get("evidence_source_ids", [])).issubset(known_sources):
            raise ValueError("undeclared source reference")

    groups = m["condition_group_bindings"]
    if len(groups) != 12:
        raise ValueError("expected exactly 12 condition groups")
    if len({x.get("group_id") for x in groups}) != 12 or len({x.get("entry_pattern") for x in groups}) != 12:
        raise ValueError("duplicate condition group or pattern")
    if sum(int(x.get("observed_cell_count", -1)) for x in groups) != 30:
        raise ValueError("condition-group cell total changed")
    if sum(int(x.get("observed_entry_pair_count", -1)) for x in groups) != 30:
        raise ValueError("condition-group pair total changed")
    for row in groups:
        if (row.get("institution_code"), row.get("form_factor"), row.get("chemistry_label")) != ("SNL", "18650", "LFP"):
            raise ValueError("bounded cohort token changed")
        if float(row.get("charge_rate_c")) != 0.5:
            raise ValueError("charge-rate token changed")
        if row.get("mapping_level") != "condition_group_entry_pattern":
            raise ValueError("mapping level changed")
        if row.get("physical_cell_identity_established") is not False:
            raise ValueError("physical-cell identity was silently claimed")
        if row.get("exact_cycle_command_binding_established") is not False:
            raise ValueError("cycle-command binding was silently claimed")
        if row.get("exact_cutoff_value_bound_to_entries") is not False:
            raise ValueError("exact cutoff was silently bound")
        soc, family = row.get("soc_window_percent"), str(row.get("study_protocol_family", ""))
        if (soc == "0-100" and "CCCV" not in family
                or soc == "20-80" and "voltage limits" not in family
                or soc == "40-60" and "capacity limits" not in family):
            raise ValueError("SOC protocol family changed")

    fields = m["evidence_field_assessments"]
    if tuple(x.get("evidence_field") for x in fields) != EVIDENCE_FIELDS:
        raise ValueError("evidence field assessment changed")
    for row in fields:
        if row.get("promotion_requirement_satisfied") is not False:
            raise ValueError("condition labels were silently promoted")
        if row.get("cross_cohort_equivalence_established") is not False:
            raise ValueError("cross-cohort equivalence was silently claimed")
        if not set(row.get("source_document_ids", [])).issubset(known_sources):
            raise ValueError("undeclared evidence source")
    if any(m["claim_policy"].values()):
        raise ValueError("claim-policy boundary changed")


def build_result(c: ReviewConfig, m: Mapping[str, Any], v265: Mapping[str, Any],
                 v266: Mapping[str, Any]) -> dict[str, Any]:
    validate_manifest(m, c)
    groups = m["condition_group_bindings"]
    matrix = [{**row, "source_to_entry_reviewed": True,
               "scientific_promotion_permitted": False,
               "same_condition_assumption_made": False,
               "causal_interpretation_permitted": False}
              for row in m["evidence_field_assessments"]]
    result: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_kind": "battery_snl_lfp_source_entry_binding_review_result",
        "package_id": PACKAGE_ID, "case_study_id": c.case_study_id,
        "bounded_source_id": c.bounded_source_id, "manifest_id": m["manifest_id"],
        "manifest_checksum": canonical_checksum(m), "archive_identity": m["archive_identity"],
        "source_register": m["source_register"], "binding_dimensions": m["binding_dimensions"],
        "condition_group_bindings": groups, "evidence_binding_matrix": matrix,
        "coverage_summary": {
            "official_source_count": 5, "binding_dimension_count": 8,
            "condition_group_count": 12,
            "represented_cell_count": sum(x["observed_cell_count"] for x in groups),
            "represented_entry_pair_count": sum(x["observed_entry_pair_count"] for x in groups),
            "publication_repository_links_established": 1,
            "repository_nomenclature_bindings_established": 1,
            "condition_group_pattern_bindings_established": 12,
            "physical_cell_entry_bindings_established": 0,
            "cycle_command_row_bindings_established": 0,
            "instrument_channel_column_bindings_established": 0,
            "official_distribution_snapshots_established": 0,
            "promotion_requirement_satisfied_count": 0,
            "remaining_blocking_field_count": 8,
        },
        "binding_decision": {
            "local_archive_identity": "bound",
            "publication_to_repository": "established",
            "repository_filename_nomenclature": "established",
            "study_to_condition_groups": "established_condition_group_only",
            "condition_group_to_entry_patterns": "established_repository_nomenclature_only",
            "physical_cell_to_entry": "not_established",
            "cycle_command_to_rows": "not_established",
            "instrument_channel_to_columns": "not_established",
            "official_distribution_snapshot": "not_established",
            "cross_cohort_comparability": "not_admitted",
            "predictive_validation": "blocked",
            "overall_status": "condition_group_nomenclature_bound_gate_not_passed",
        },
        "preservation_checks": preservation(v265, v266, c),
        "scientific_closeout": {
            "status": "diagnostic",
            "result": "condition_group_nomenclature_binding_established",
            "evidence_level": "official_repository_nomenclature_plus_checksum_bound_local_archive_inventory",
            "strongest_evidence": (
                "The publication is officially linked to Battery Archive, the repository defines the "
                "observed filename-token semantics, and the checksum-bound local archive contains "
                "30 cell pairs aggregated into 12 documented condition-group patterns."
            ),
            "primary_limitation": (
                "No provider-published release identifier or archive checksum, physical cell-to-file "
                "map, cycle-command log, instrument-channel map, calibration evidence, or CSV review exists."
            ),
            "what_would_change_conclusion": [
                "provider-issued versioned distribution identifier and checksum",
                "official cell or channel mapping for each entry stem",
                "bounded command-step and CSV-schema provenance contract",
                "calibration or measurement-uncertainty records",
            ],
            "suitable_for": ["source attribution", "condition-group provenance",
                             "bounded schema-review planning", "evidence-gap prioritization"],
            "unsuitable_for": ["scientific metadata promotion", "cross-cohort equivalence",
                               "predictive validation", "model selection", "mechanism claims",
                               "engineering decisions"],
        },
        "recommendations": [
            "retain the 12 condition-group pattern map and archive checksums as provenance evidence",
            "request a provider-issued distribution identifier or checksum",
            "defer CSV reads until a bounded schema-read contract is approved",
            "do not merge cohorts or rerun models",
        ],
        "source_references": {"manifest": c.manifest_path,
                              "v2_6_5_summary": c.v2_6_5_summary_path,
                              "v2_6_6_summary": c.v2_6_6_summary_path},
    }
    for flag in FALSE_FLAGS:
        result[flag] = False
    result["deterministic_result_checksum"] = canonical_checksum(result)
    return result


def compact(result: Mapping[str, Any]) -> dict[str, Any]:
    keep = ("schema_version", "package_id", "case_study_id", "bounded_source_id",
            "manifest_id", "manifest_checksum", "archive_identity", "coverage_summary",
            "binding_decision", "preservation_checks", "scientific_closeout",
            "recommendations", "source_references", *FALSE_FLAGS)
    out = {key: result[key] for key in keep}
    out["artifact_kind"] = "battery_snl_lfp_source_entry_binding_review_compact_summary"
    out["binding_dimension_statuses"] = [
        {"dimension": row["dimension"], "status": row["status"]}
        for row in result["binding_dimensions"]
    ]
    out["condition_group_summary"] = [
        {key: row[key] for key in (
            "group_id", "entry_pattern", "environment_temperature_c",
            "soc_window_percent", "charge_rate_c", "discharge_rate_c",
            "replicate_labels", "observed_cell_count", "observed_entry_pair_count",
            "mapping_level", "physical_cell_identity_established",
            "exact_cycle_command_binding_established",
        )}
        for row in result["condition_group_bindings"]
    ]
    out["evidence_field_statuses"] = [
        {"evidence_field": row["evidence_field"],
         "source_to_entry_status": row["source_to_entry_status"],
         "promotion_requirement_satisfied": False}
        for row in result["evidence_binding_matrix"]
    ]
    out["deterministic_result_checksum"] = canonical_checksum(out)
    return out


def validate_result(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != VERSION or payload.get("package_id") != PACKAGE_ID:
        raise ValueError("unsupported result")
    decision = payload.get("binding_decision", {})
    expected = {
        "physical_cell_to_entry": "not_established",
        "cycle_command_to_rows": "not_established",
        "instrument_channel_to_columns": "not_established",
        "official_distribution_snapshot": "not_established",
        "cross_cohort_comparability": "not_admitted",
        "predictive_validation": "blocked",
        "overall_status": "condition_group_nomenclature_bound_gate_not_passed",
    }
    if any(decision.get(k) != v for k, v in expected.items()):
        raise ValueError("scientific boundary changed")
    coverage = payload.get("coverage_summary", {})
    zero_keys = (
        "promotion_requirement_satisfied_count", "physical_cell_entry_bindings_established",
        "cycle_command_row_bindings_established", "official_distribution_snapshots_established",
    )
    if any(coverage.get(key) != 0 for key in zero_keys):
        raise ValueError("evidence was silently promoted")
    if any(payload.get(flag) is not False for flag in FALSE_FLAGS):
        raise ValueError("prohibited execution flag changed")
    if payload.get("deterministic_result_checksum") != canonical_checksum(payload):
        raise ValueError("deterministic result checksum mismatch")


def execute(c: ReviewConfig, repo_root: str | Path = ".", write_outputs: bool = True) -> dict[str, Any]:
    result = build_result(
        c, _json(repo_path(repo_root, c.manifest_path)),
        _json(repo_path(repo_root, c.v2_6_5_summary_path)),
        _json(repo_path(repo_root, c.v2_6_6_summary_path)),
    )
    validate_result(result)
    if write_outputs:
        root = repo_path(repo_root, c.output_root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "source_entry_binding_review.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tracked = repo_path(repo_root, c.tracked_summary_path)
        tracked.parent.mkdir(parents=True, exist_ok=True)
        value = compact(result)
        validate_result(value)
        tracked.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result


def preview(c: ReviewConfig, repo_root: str | Path = ".") -> dict[str, Any]:
    manifest = _json(repo_path(repo_root, c.manifest_path))
    validate_manifest(manifest, c)
    groups = manifest["condition_group_bindings"]
    return {
        "schema_version": VERSION, "package_id": PACKAGE_ID,
        "bounded_source_id": c.bounded_source_id, "manifest_id": manifest["manifest_id"],
        "condition_group_count": len(groups),
        "represented_cell_count": sum(x["observed_cell_count"] for x in groups),
        "allowed_reads": ["tracked JSON evidence packages"],
        "prohibited_reads": ["raw archive bytes", "entry payloads", "CSV headers",
                             "CSV rows", "archive extraction", "network", "credentials"],
        "write_outputs": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preview")
    sub.add_parser("run")
    validator = sub.add_parser("validate")
    validator.add_argument("result_path")
    args = parser.parse_args(argv)
    config = load_config(args.config, args.repo_root)
    if args.command == "preview":
        value = preview(config, args.repo_root)
    elif args.command == "run":
        value = execute(config, args.repo_root, True)
    else:
        value = _json(repo_path(args.repo_root, args.result_path))
        validate_result(value)
        value = {"valid": True,
                 "deterministic_result_checksum": value["deterministic_result_checksum"]}
    print(json.dumps(value, ensure_ascii=False, sort_keys=True)
          if args.json else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
