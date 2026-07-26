from __future__ import annotations
import copy, hashlib, json, re
from pathlib import Path

VERSION="2.6.12"
PACKAGE_ID="battery_michigan_formation_provider_package_structure_gate_v1"
CONTRACT_ID="battery_michigan_formation_provider_package_structure_contract_v1"
EVIDENCE_RECORD_ID="battery_michigan_formation_provider_package_evidence_v1"
DEFAULT_CONFIG_PATH="configs/examples/battery_michigan_formation_provider_package_structure_gate.json"
DEFAULT_CONTRACT_PATH="data/platform/battery_michigan_formation_provider_package_structure_contract_v1.json"
DEFAULT_EVIDENCE_PATH="data/platform/battery_michigan_formation_provider_package_evidence_v1.json"
DEFAULT_V2611_PATH="data/processed/battery_v2_6_11_external_cohort_next_source_selection_summary.json"
DEFAULT_OUTPUT_ROOT="outputs/v2_6_battery_michigan_formation_provider_package"
DEFAULT_TRACKED_SUMMARY="data/processed/battery_v2_6_12_michigan_formation_provider_package_summary.json"
EXPECTED_V2611_CHECKSUM="5cbb6b979bd6529e28d24af1ecb0e1579439fef2be710904081d8e81d032747b"
EXPECTED_EVIDENCE_CHECKSUM="079741f6b6082829f4754495e2b1f96433e574049de029f8bef593440402924a"
EXPECTED_CONTRACT_CHECKSUM="bac45b313696cd20502e740d2b29c25ba76e9c5605f38fc7476e75b7de042408"
EXPECTED_RESULT_CHECKSUM="b1ce09e4ce06c9ec90839b63e1f2546d1fd2808f9c8ea6717edc5bc0fe93ce7d"
FALSE_FLAGS=("network_called","credentials_read","provider_dataset_downloaded","provider_file_payload_read","local_archive_read","local_csv_payload_read","filename_metadata_inferred","command_semantics_inferred","missing_metadata_inferred","cross_cohort_comparability_promoted","candidate_admitted","cohort_merge_performed","model_trained","model_evaluated","metrics_recomputed","source_mutation_performed")

def canonical_checksum(payload):
    core=copy.deepcopy(dict(payload)); core.pop("deterministic_result_checksum",None)
    return hashlib.sha256(json.dumps(core,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def _json(path):
    value=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError(f"JSON object required: {path}")
    return value

def _relative(name,value):
    text=str(value).replace("\\","/"); path=Path(text)
    if path.is_absolute() or re.match(r"^[A-Za-z]:",text) or ".." in path.parts:
        raise ValueError(f"{name} must be repository-relative and non-traversing")
    return path.as_posix()

def repo_path(root,value):
    base=Path(root).resolve(); target=(Path(root)/value).resolve()
    try: target.relative_to(base)
    except ValueError as exc: raise ValueError(f"path escapes repository root: {value}") from exc
    return target

def load_config(path=DEFAULT_CONFIG_PATH,repo_root="."):
    value=_json(repo_path(repo_root,path))
    required={"schema_version","package_id","case_study_id","bounded_source_id","contract_path","provider_evidence_path","v2_6_11_next_source_selection_summary_path","expected_v2_6_11_checksum","execution_policy","credential_policy","output_root","tracked_summary_path","output_policy","execution_mode","dry_run"}
    if set(value)!=required or value["schema_version"]!=VERSION or value["package_id"]!=PACKAGE_ID: raise ValueError("config fields changed")
    if value["bounded_source_id"]!="michigan_fast_formation_deep_blue_b2773w109" or value["expected_v2_6_11_checksum"]!=EXPECTED_V2611_CHECKSUM: raise ValueError("config identity changed")
    policy={"network_access":False,"provider_dataset_download":False,"provider_file_payload_read":False,"local_archive_read":False,"local_csv_payload_read":False,"filename_inference":False,"command_inference":False,"cohort_merge":False,"model_execution":False,"metric_recomputation":False}
    if value["execution_policy"]!=policy or value["credential_policy"]!={"network_access_required":False,"store_credentials":False}: raise ValueError("config policy changed")
    paths={"contract_path":DEFAULT_CONTRACT_PATH,"provider_evidence_path":DEFAULT_EVIDENCE_PATH,"v2_6_11_next_source_selection_summary_path":DEFAULT_V2611_PATH,"output_root":DEFAULT_OUTPUT_ROOT,"tracked_summary_path":DEFAULT_TRACKED_SUMMARY}
    for key,expected in paths.items():
        if _relative(key,value[key])!=expected: raise ValueError(f"{key} changed")
    if value["output_policy"]!="tracked_compact_summary_and_local_full_result" or value["execution_mode"]!="verify" or value["dry_run"] is not False: raise ValueError("config execution changed")
    return value

