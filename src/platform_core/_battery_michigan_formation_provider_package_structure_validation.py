from ._battery_michigan_formation_provider_package_structure_common import (
    CONTRACT_ID,EVIDENCE_RECORD_ID,EXPECTED_CONTRACT_CHECKSUM,EXPECTED_EVIDENCE_CHECKSUM,
    EXPECTED_V2611_CHECKSUM,canonical_checksum,
)

def validate_evidence(value):
    required={"schema_version","evidence_record_id","provider_dataset_id","provider","retrieved_on","dataset_record","study_declarations","provider_package_structure","manifest_observation","repository_api_evidence","battery_archive_binding_evidence","source_references","claim_policy"}
    if set(value)!=required or value["schema_version"]!="1" or value["evidence_record_id"]!=EVIDENCE_RECORD_ID or value["provider_dataset_id"]!="b2773w109": raise ValueError("provider evidence identity changed")
    record=value["dataset_record"]; study=value["study_declarations"]; manifest=value["manifest_observation"]; api=value["repository_api_evidence"]
    if (record["dataset_doi"],record["file_set_count"],record["total_size_human_readable"])!=("10.7302/pa3f-4w30",2,"2.37 GB"): raise ValueError("provider record changed")
    if (study["cell_count"],study["nominal_capacity_ah"],study["cathode"],study["anode"])!=(40,"2.36","NCM111","graphite"): raise ValueError("study metadata changed")
    if {x["folder"] for x in value["provider_package_structure"]}!={"code","data","documents","output"}: raise ValueError("provider folders changed")
    if manifest["exact_provider_package_manifest_status"]!="not_established": raise ValueError("manifest promoted")
    if any(flag is not False for key,flag in manifest.items() if key.endswith("_recovered")): raise ValueError("manifest evidence promoted")
    if not api["dataset_metadata_endpoint_documented"] or not api["file_set_metadata_endpoint_documented"] or api["dataset_metadata_endpoint_retrieved_for_this_record"] or api["file_set_metadata_endpoint_retrieved_for_this_record"]: raise ValueError("API evidence changed")
    if any(value["claim_policy"].values()) or canonical_checksum(value)!=EXPECTED_EVIDENCE_CHECKSUM: raise ValueError("provider evidence checksum or claim changed")

def validate_contract(value):
    required={"schema_version","contract_id","contract_recorded_on","bounded_source_id","scientific_question","upstream_identity","allowed_source_scope","decision_policy","execution_policy","stop_rules","next_authorized_scope","claim_policy"}
    if set(value)!=required or value["schema_version"]!="1" or value["contract_id"]!=CONTRACT_ID: raise ValueError("provider contract identity changed")
    if value["upstream_identity"]!={"v2_6_11_next_source_selection_checksum":EXPECTED_V2611_CHECKSUM,"provider_evidence_checksum":EXPECTED_EVIDENCE_CHECKSUM}: raise ValueError("contract upstream changed")
    allowed={"provider_dataset_identity_may_be_established","provider_package_folder_structure_may_be_established","provider_file_set_count_may_be_recorded","cell_tracker_presence_may_be_recorded_at_document_level","test_schedule_presence_may_be_recorded_at_document_level"}
    if any(flag is not (key in allowed) for key,flag in value["decision_policy"].items()): raise ValueError("decision boundary changed")
    if any(value["execution_policy"].values()) or any(value["claim_policy"].values()) or canonical_checksum(value)!=EXPECTED_CONTRACT_CHECKSUM: raise ValueError("contract policy or checksum changed")

def verify_upstream(value):
    if value.get("deterministic_result_checksum")!=EXPECTED_V2611_CHECKSUM or canonical_checksum(value)!=EXPECTED_V2611_CHECKSUM: raise ValueError("v2.6.11 checksum mismatch")
    d=value.get("selection_decision",{})
    if (d.get("selected_archive"),d.get("selection_status"),d.get("cross_cohort_comparability"),d.get("predictive_validation"))!=("Michigan Formation.zip","selected_for_bounded_source_binding_only","not_admitted","blocked"): raise ValueError("v2.6.11 boundary changed")
    return {"v2_6_11_checksum_verified":True,"v2_6_11_selected_archive_preserved":True,"v2_6_11_non_admission_preserved":True,"model_or_metric_change_performed":False}
