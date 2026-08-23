#!/usr/bin/env python3
"""Acquire exact official IN625 condition-mapping evidence for reviewed promotion.

This is a development reconnaissance utility, not a production scientific gate. It downloads
only the exact NIST URLs declared in the repository configuration, records raw SHA-256/size,
and verifies short predeclared semantic anchors. It deliberately does not persist source PDFs
or HTML and does not emit copyrighted excerpts; matched source text is represented only by
its SHA-256, length, and page index where applicable.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ReconError(ValueError):
    """Raised when exact source reconnaissance violates its bounded contract."""


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


class _RestrictedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        _validate_url(newurl, self.allowed_hosts, "redirect URL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReconError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReconError(f"invalid reconnaissance JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReconError("reconnaissance root must be an object")
    return value


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReconError(f"{field} must be a positive integer")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ReconError(f"{field} must be non-empty trimmed text")
    return value


def _validate_url(url: str, allowed_hosts: set[str], field: str) -> None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ReconError(f"{field} has invalid port") from exc
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in allowed_hosts
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ReconError(f"{field} left exact HTTPS host authority: {url}")


def _fetch(
    url: str,
    *,
    allowed_hosts: set[str],
    max_bytes: int,
    timeout_seconds: int,
) -> tuple[bytes, str, str | None]:
    _validate_url(url, allowed_hosts, "source URL")
    opener = build_opener(_RestrictedRedirectHandler(allowed_hosts))
    request = Request(url, headers={"User-Agent": "materials-data-analyzer/condition-recon/1.0"})
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            _validate_url(final_url, allowed_hosts, "final URL")
            body = response.read(max_bytes + 1)
            content_type = response.headers.get_content_type()
    except OSError as exc:
        raise ReconError(f"source fetch failed for {url}: {exc}") from exc
    if len(body) > max_bytes:
        raise ReconError(f"source exceeded max byte budget: {url}")
    if not body:
        raise ReconError(f"source returned empty body: {url}")
    return body, final_url, content_type


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _html_text(body: bytes) -> str:
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError:
        decoded = body.decode("utf-8", errors="replace")
    parser = _TextCollector()
    parser.feed(decoded)
    return _normalize_text(" ".join(parser.parts))


def _pdf_pages(body: bytes) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - workflow installs the recon dependency.
        raise ReconError("PDF reconnaissance requires pypdf") from exc
    from io import BytesIO

    try:
        reader = PdfReader(BytesIO(body), strict=True)
    except Exception as exc:  # pragma: no cover - external source parser errors vary.
        raise ReconError(f"failed to parse PDF: {exc}") from exc
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover - external source parser errors vary.
            raise ReconError(f"failed to extract PDF text: {exc}") from exc
        pages.append(_normalize_text(text))
    if not any(pages):
        raise ReconError("PDF produced no extractable text")
    return pages


def _anchor_result(
    *,
    anchor: dict[str, Any],
    pages: list[str],
    is_pdf: bool,
) -> dict[str, Any]:
    claim_id = _strict_text(anchor.get("claim_id"), "claim_id")
    pattern = _strict_text(anchor.get("anchor_regex"), f"{claim_id}.anchor_regex")
    scope = _strict_text(anchor.get("scope"), f"{claim_id}.scope")
    try:
        compiled = re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    except re.error as exc:
        raise ReconError(f"invalid anchor regex for {claim_id}: {exc}") from exc
    matches: list[dict[str, Any]] = []
    for page_index, text in enumerate(pages):
        match = compiled.search(text)
        if match is None:
            continue
        matched = match.group(0).encode("utf-8")
        matches.append(
            {
                "page_index_zero_based": page_index if is_pdf else None,
                "matched_text_sha256": _sha256(matched),
                "matched_text_utf8_bytes": len(matched),
            }
        )
    return {
        "claim_id": claim_id,
        "scope": scope,
        "anchor_regex_sha256": _sha256(pattern.encode("utf-8")),
        "matched": bool(matches),
        "match_count": len(matches),
        "matches": matches,
        "source_text_persisted": False,
    }


def run(config_path: Path) -> dict[str, Any]:
    config = _load_json(config_path)
    if config.get("schema_version") != "1.0":
        raise ReconError("unsupported reconnaissance schema_version")
    network = config.get("network_policy")
    if not isinstance(network, dict):
        raise ReconError("network_policy must be an object")
    if network.get("scheme") != "https":
        raise ReconError("only HTTPS reconnaissance is allowed")
    raw_hosts = network.get("allowed_hosts")
    if not isinstance(raw_hosts, list) or not raw_hosts:
        raise ReconError("allowed_hosts must be a non-empty list")
    allowed_hosts = {_strict_text(item, "allowed_host").lower() for item in raw_hosts}
    if len(allowed_hosts) != len(raw_hosts):
        raise ReconError("allowed_hosts must be unique")
    max_source_bytes = _positive_int(network.get("max_source_bytes"), "max_source_bytes")
    max_total_bytes = _positive_int(network.get("max_total_bytes"), "max_total_bytes")
    timeout_seconds = _positive_int(network.get("timeout_seconds"), "timeout_seconds")
    if network.get("unrestricted_search") is not False or network.get("arbitrary_url_fetch") is not False:
        raise ReconError("reconnaissance network authority must remain finite")

    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ReconError("sources must be a non-empty list")
    source_ids: set[str] = set()
    total_bytes = 0
    results: list[dict[str, Any]] = []
    for index, raw_source in enumerate(sources):
        if not isinstance(raw_source, dict):
            raise ReconError(f"sources[{index}] must be an object")
        source_id = _strict_text(raw_source.get("source_id"), f"sources[{index}].source_id")
        if source_id in source_ids:
            raise ReconError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)
        url = _strict_text(raw_source.get("url"), f"{source_id}.url")
        media_type = _strict_text(raw_source.get("media_type"), f"{source_id}.media_type")
        if media_type not in {"html", "pdf"}:
            raise ReconError(f"unsupported media_type for {source_id}: {media_type}")
        body, final_url, content_type = _fetch(
            url,
            allowed_hosts=allowed_hosts,
            max_bytes=max_source_bytes,
            timeout_seconds=timeout_seconds,
        )
        total_bytes += len(body)
        if total_bytes > max_total_bytes:
            raise ReconError("total reconnaissance byte budget exceeded")

        if media_type == "pdf":
            pages = _pdf_pages(body)
        else:
            pages = [_html_text(body)]
        raw_anchors = raw_source.get("claims_under_review")
        if not isinstance(raw_anchors, list) or not raw_anchors:
            raise ReconError(f"{source_id}.claims_under_review must be a non-empty list")
        anchors = [
            _anchor_result(anchor=anchor, pages=pages, is_pdf=media_type == "pdf")
            for anchor in raw_anchors
            if isinstance(anchor, dict)
        ]
        if len(anchors) != len(raw_anchors):
            raise ReconError(f"{source_id} contains a non-object claim anchor")
        results.append(
            {
                "source_id": source_id,
                "source_class": _strict_text(raw_source.get("source_class"), f"{source_id}.source_class"),
                "authority": _strict_text(raw_source.get("authority"), f"{source_id}.authority"),
                "title": _strict_text(raw_source.get("title"), f"{source_id}.title"),
                "doi": raw_source.get("doi"),
                "requested_url": url,
                "final_url": final_url,
                "media_type": media_type,
                "http_content_type": content_type,
                "source_sha256": _sha256(body),
                "source_size_bytes": len(body),
                "pdf_page_count": len(pages) if media_type == "pdf" else None,
                "claims": anchors,
                "all_claim_anchors_matched": all(item["matched"] for item in anchors),
                "source_bytes_persisted": False,
                "scientific_status_changed": False,
                "row_level_measurement_authority": False,
            }
        )

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "reconnaissance_id": config.get("reconnaissance_id"),
        "config_path": config_path.as_posix(),
        "config_sha256": _sha256(config_path.read_bytes()),
        "source_count": len(results),
        "total_source_bytes_observed": total_bytes,
        "all_sources_fetched": True,
        "all_claim_anchors_matched": all(
            item["all_claim_anchors_matched"] for item in results
        ),
        "sources": results,
        "unrestricted_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "source_bytes_persisted": False,
        "paper_claims_promoted_to_row_level_authority": False,
        "scientific_status_changed": False,
    }
    unsigned = dict(report)
    report["report_sha256_without_self_field"] = _sha256(_canonical_bytes(unsigned))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.config.resolve(strict=True))
        output = args.output.resolve(strict=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_bytes(result))
    except (OSError, ReconError, ValueError) as exc:
        print(f"condition-source reconnaissance failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
