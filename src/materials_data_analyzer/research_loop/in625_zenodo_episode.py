"""Independent LPBF IN625 publication-data episode using Zenodo record 20503603.

The episode is intentionally separate from the exact AMMT Stage-1 requirement.  It may
acquire publication-linked original data and inventory quantitative files, but it cannot
promote them beyond publication-supplement evidence until sample/acquisition lineage,
semantics, calibration, comparability, and human-review requirements are satisfied.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from platform_core.output_safety import transactional_output_directory

from .evidence_federation import (
    EvidenceClass,
    EvidenceTrustVector,
    FederatedEvidenceCandidate,
    maximum_evidence_use,
)
from .evidence_harvester import harvest_evidence
from .kernel import ResearchLoopError
from .public_data_acquisition import PublicAcquisitionError, PublicFetcher, fetch_https_bytes
from .research_episode import (
    checkpoint_episode,
    create_research_episode,
    validate_episode_state,
)
from .safe_archive_inventory import inspect_zip_archive
from .zenodo_evidence_acquisition import (
    AUTO,
    REVIEW_REQUIRED,
    ZenodoEvidenceAcquisitionError,
    acquire_zenodo_files,
    fetch_zenodo_record_metadata,
    normalize_zenodo_record_metadata,
    plan_zenodo_file_acquisition,
)

IN625_ZENODO_EPISODE_SCHEMA_VERSION = "1.0"


class In625ZenodoEpisodeError(ResearchLoopError):
    """Raised when the configured independent IN625 episode is internally inconsistent."""


MetadataFetcher = Callable[[str | int], tuple[bytes, str]]
HarvesterCallable = Callable[..., dict[str, Any]]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise In625ZenodoEpisodeError(f"{field} must be non-empty text")
    if value != value.strip():
        raise In625ZenodoEpisodeError(f"{field} must not contain edge whitespace")
    return value


def _strings(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise In625ZenodoEpisodeError(f"{field} must be a non-empty list")
    result: list[str] = []
    for item in value:
        text = _text(item, f"{field} item")
        if text in result:
            raise In625ZenodoEpisodeError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def validate_in625_episode_config(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise In625ZenodoEpisodeError("episode config must be an object")
    required = {
        "schema_version",
        "episode_id",
        "mission_id",
        "research_question",
        "objectives",
        "query_aliases",
        "providers",
        "zenodo",
        "scientific_boundaries",
        "episode_budget",
    }
    if set(value) != required:
        raise In625ZenodoEpisodeError("episode config keys do not match schema")
    if value["schema_version"] != "1.0":
        raise In625ZenodoEpisodeError("unsupported episode config schema_version")
    zenodo = value["zenodo"]
    if not isinstance(zenodo, Mapping) or set(zenodo) != {
        "record_id",
        "version_doi",
        "related_article_doi",
        "selected_files",
        "archive_file",
    }:
        raise In625ZenodoEpisodeError("zenodo config keys do not match schema")
    record_id = zenodo["record_id"]
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        raise In625ZenodoEpisodeError("zenodo.record_id must be positive integer")
    selected_files = _strings(zenodo["selected_files"], "zenodo.selected_files")
    archive_file = _text(zenodo["archive_file"], "zenodo.archive_file")
    if archive_file not in selected_files:
        raise In625ZenodoEpisodeError("zenodo.archive_file must be selected for acquisition")
    boundaries = value["scientific_boundaries"]
    if not isinstance(boundaries, Mapping):
        raise In625ZenodoEpisodeError("scientific_boundaries must be object")
    if boundaries.get("issue_76_eligible") is not False:
        raise In625ZenodoEpisodeError("independent Zenodo episode must not satisfy issue #76")
    if boundaries.get("automatic_scientific_promotion") is not False:
        raise In625ZenodoEpisodeError("automatic scientific promotion must remain disabled")
    budget = value["episode_budget"]
    if not isinstance(budget, Mapping) or set(budget) != {"max_iterations", "cost_budget"}:
        raise In625ZenodoEpisodeError("episode_budget keys do not match schema")
    max_iterations = budget["max_iterations"]
    cost_budget = budget["cost_budget"]
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise In625ZenodoEpisodeError("episode_budget.max_iterations must be positive")
    if isinstance(cost_budget, bool) or not isinstance(cost_budget, (int, float)) or cost_budget < 0:
        raise In625ZenodoEpisodeError("episode_budget.cost_budget must be non-negative")
    return {
        "schema_version": "1.0",
        "episode_id": _text(value["episode_id"], "episode_id"),
        "mission_id": _text(value["mission_id"], "mission_id"),
        "research_question": _text(value["research_question"], "research_question"),
        "objectives": _strings(value["objectives"], "objectives"),
        "query_aliases": _strings(value["query_aliases"], "query_aliases", allow_empty=True),
        "providers": _strings(value["providers"], "providers"),
        "zenodo": {
            "record_id": record_id,
            "version_doi": _text(zenodo["version_doi"], "zenodo.version_doi").lower(),
            "related_article_doi": _text(
                zenodo["related_article_doi"], "zenodo.related_article_doi"
            ).lower(),
            "selected_files": selected_files,
            "archive_file": archive_file,
        },
        "scientific_boundaries": dict(boundaries),
        "episode_budget": {
            "max_iterations": max_iterations,
            "cost_budget": float(cost_budget),
        },
    }


def _related_identifiers(metadata_bytes: bytes) -> list[str]:
    try:
        root = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625ZenodoEpisodeError("could not inspect Zenodo related identifiers") from exc
    metadata = root.get("metadata") if isinstance(root, dict) else None
    if not isinstance(metadata, dict):
        return []
    raw = metadata.get("related_identifiers") or metadata.get("relatedIdentifiers")
    result: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            identifier = item.get("identifier") or item.get("relatedIdentifier")
            if isinstance(identifier, str) and identifier.strip():
                text = identifier.strip().lower()
                if text not in result:
                    result.append(text)
    return sorted(result)


def _seed_episode(
    config: Mapping[str, Any],
    *,
    evidence_refs: list[str],
    gaps: list[str],
    review_queue: list[str],
    blockers: list[str],
    status: str,
) -> dict[str, Any]:
    budget = config["episode_budget"]
    state = create_research_episode(
        episode_id=config["episode_id"],
        research_question=config["research_question"],
        mission_id=config["mission_id"],
        objectives=config["objectives"],
        max_iterations=budget["max_iterations"],
        cost_budget=budget["cost_budget"],
    )
    state["evidence_refs"] = evidence_refs
    state["unresolved_gaps"] = gaps
    state["review_queue"] = review_queue
    state["blockers"] = blockers
    state["status"] = status
    return validate_episode_state(state)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_in625_zenodo_episode(
    *,
    config: Mapping[str, Any],
    output_dir: str | Path,
    metadata_fetcher: MetadataFetcher | None = None,
    content_fetcher: PublicFetcher = fetch_https_bytes,
    harvester: HarvesterCallable = harvest_evidence,
    overwrite: bool = False,
) -> dict[str, Any]:
    cfg = validate_in625_episode_config(config)
    fetch_metadata = metadata_fetcher or (
        lambda record_id: fetch_zenodo_record_metadata(record_id)
    )
    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        recognized_markers=("live_in625_evidence_summary.json",),
    ) as staging:
        harvest_report = harvester(
            {
                "material": "IN625",
                "process": "LPBF",
                "research_question": cfg["research_question"],
            },
            providers=cfg["providers"],
            query_aliases=cfg["query_aliases"],
        )
        _write_json(staging / "evidence_harvest_report.json", harvest_report)

        record_cfg = cfg["zenodo"]
        try:
            metadata_bytes, metadata_url = fetch_metadata(record_cfg["record_id"])
        except (PublicAcquisitionError, ZenodoEvidenceAcquisitionError) as exc:
            blockers = ["live_zenodo_metadata_unavailable"]
            episode = _seed_episode(
                cfg,
                evidence_refs=[],
                gaps=[
                    "Live Zenodo record metadata could not be retrieved; this is not negative scientific evidence.",
                    "Exact AMMT Stage 1 evidence remains unresolved under issue #76.",
                ],
                review_queue=[],
                blockers=blockers,
                status="blocked",
            )
            checkpoint_episode(staging / "research_episode.json", episode)
            summary = {
                "schema_version": IN625_ZENODO_EPISODE_SCHEMA_VERSION,
                "status": "network_or_provider_unavailable",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "scientific_negative_evidence": False,
                "issue_76_eligible": False,
                "scientific_status_changed": False,
            }
            _write_json(staging / "live_in625_evidence_summary.json", summary)
            return summary

        normalized = normalize_zenodo_record_metadata(
            metadata_bytes=metadata_bytes,
            request_url=metadata_url,
            expected_record_id=record_cfg["record_id"],
            expected_doi=record_cfg["version_doi"],
        )
        related = _related_identifiers(metadata_bytes)
        related_article_verified = record_cfg["related_article_doi"] in related
        _write_json(staging / "zenodo_record_normalized.json", normalized)
        plan = plan_zenodo_file_acquisition(
            normalized,
            selected_files=record_cfg["selected_files"],
        )
        _write_json(staging / "zenodo_acquisition_plan.json", plan)

        if normalized["record_decision"] != AUTO or any(
            item["decision"] != AUTO for item in plan["items"]
        ):
            reasons = sorted(
                {
                    *normalized["record_reason_codes"],
                    *(
                        reason
                        for item in plan["items"]
                        for reason in item["reason_codes"]
                    ),
                }
            )
            episode = _seed_episode(
                cfg,
                evidence_refs=[],
                gaps=[
                    "Zenodo publication dataset is discovered but automatic content acquisition is not policy-authorized.",
                    "Exact AMMT Stage 1 evidence remains unresolved under issue #76.",
                ],
                review_queue=[
                    f"zenodo:{record_cfg['record_id']}:{reason}" for reason in reasons
                ],
                blockers=["human_or_rights_review_required"],
                status="blocked",
            )
            checkpoint_episode(staging / "research_episode.json", episode)
            summary = {
                "schema_version": IN625_ZENODO_EPISODE_SCHEMA_VERSION,
                "status": "review_required_before_acquisition",
                "record_id": normalized["record_id"],
                "doi": normalized["doi"],
                "record_reason_codes": reasons,
                "related_article_doi": record_cfg["related_article_doi"],
                "related_article_relation_verified_from_record": related_article_verified,
                "scientific_negative_evidence": False,
                "issue_76_eligible": False,
                "scientific_status_changed": False,
            }
            _write_json(staging / "live_in625_evidence_summary.json", summary)
            return summary

        try:
            acquisition = acquire_zenodo_files(
                metadata_bytes=metadata_bytes,
                normalized_record=normalized,
                selected_files=record_cfg["selected_files"],
                output_dir=staging / "acquisition",
                fetcher=content_fetcher,
            )
        except PublicAcquisitionError as exc:
            episode = _seed_episode(
                cfg,
                evidence_refs=[],
                gaps=[
                    "Zenodo record passed metadata policy but content transfer was unavailable; this is not negative scientific evidence.",
                    "Exact AMMT Stage 1 evidence remains unresolved under issue #76.",
                ],
                review_queue=[],
                blockers=["live_content_transfer_unavailable"],
                status="blocked",
            )
            checkpoint_episode(staging / "research_episode.json", episode)
            summary = {
                "schema_version": IN625_ZENODO_EPISODE_SCHEMA_VERSION,
                "status": "content_network_unavailable",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "scientific_negative_evidence": False,
                "issue_76_eligible": False,
                "scientific_status_changed": False,
            }
            _write_json(staging / "live_in625_evidence_summary.json", summary)
            return summary

        archive_path = (
            staging / "acquisition" / "files" / record_cfg["archive_file"]
        )
        archive_inventory = inspect_zip_archive(archive_path)
        _write_json(staging / "archive_inventory.json", archive_inventory)
        archive_file = next(
            item
            for item in acquisition["files"]
            if item["key"] == record_cfg["archive_file"]
        )
        candidate = FederatedEvidenceCandidate(
            provider="zenodo",
            source_id=f"zenodo:{normalized['record_id']}",
            title=normalized["title"],
            evidence_class=EvidenceClass.E2_PUBLICATION_SUPPLEMENT,
            trust=EvidenceTrustVector(
                source_authority="repository_curated",
                representation="supplementary",
                sample_identity="unknown",
                acquisition_identity="unknown",
                calibration="unknown",
                independence="unresolved",
                comparability="adjacent",
                reuse="allowed",
                extraction="underlying_data",
            ),
            source_locator=normalized["record_metadata_url"],
            artifact_sha256=archive_file["local_sha256"],
            related_identifiers=(record_cfg["related_article_doi"],),
        )
        candidate_record = candidate.record()
        use_ceiling = maximum_evidence_use(candidate)
        _write_json(staging / "federated_evidence_candidate.json", candidate_record)
        _write_json(staging / "federated_evidence_use_ceiling.json", use_ceiling)
        blockers = [
            "sample_acquisition_lineage_not_yet_bound",
            "measurement_semantics_and_calibration_not_yet_audited",
            "cross_source_comparability_not_yet_established",
            "human_scientific_review_not_yet_released",
            "issue_76_exact_ammt_requirement_remains_separate",
        ]
        episode = _seed_episode(
            cfg,
            evidence_refs=[candidate.candidate_id],
            gaps=[
                "Publication supplement has been acquired and structurally inventoried, but sample/acquisition lineage and measurement semantics remain unresolved.",
                "Exact AMMT Stage 1 evidence remains unresolved under issue #76.",
            ],
            review_queue=[f"scientific-intake:{candidate.candidate_id}"],
            blockers=blockers,
            status="blocked",
        )
        checkpoint_episode(staging / "research_episode.json", episode)
        summary = {
            "schema_version": IN625_ZENODO_EPISODE_SCHEMA_VERSION,
            "status": "acquired_pending_semantic_lineage_and_review_intake",
            "record_id": normalized["record_id"],
            "doi": normalized["doi"],
            "license_ids": normalized["license_ids"],
            "related_article_doi": record_cfg["related_article_doi"],
            "related_article_relation_verified_from_record": related_article_verified,
            "acquired_file_count": len(acquisition["files"]),
            "archive_member_count": archive_inventory["member_count"],
            "archive_text_candidate_count": archive_inventory["text_candidate_count"],
            "archive_text_hashed_count": archive_inventory["text_hashed_count"],
            "evidence_candidate_id": candidate.candidate_id,
            "evidence_class": candidate.evidence_class.value,
            "maximum_use_before_additional_intake": use_ceiling["maximum_use"],
            "remaining_blocker_codes": blockers,
            "issue_76_eligible": False,
            "scientific_hypothesis_verified": False,
            "scientific_status_changed": False,
        }
        _write_json(staging / "live_in625_evidence_summary.json", summary)
        return summary


__all__ = [
    "IN625_ZENODO_EPISODE_SCHEMA_VERSION",
    "In625ZenodoEpisodeError",
    "run_in625_zenodo_episode",
    "validate_in625_episode_config",
]
