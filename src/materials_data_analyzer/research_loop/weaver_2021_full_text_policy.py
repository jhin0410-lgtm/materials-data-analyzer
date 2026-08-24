"""Current-mission facade for the reviewed Weaver full-text policy implementation.

The source/acquisition policy is unchanged. This facade rebinds only the separately versioned
Weaver authority extension to the current immutable autonomous-production mission bytes after
upstream provenance/recovery hardening changed the base mission SHA.
"""
from __future__ import annotations

from . import weaver_2021_full_text_policy_impl as _impl

CURRENT_BASE_MISSION_SHA256 = "7de1c78d1411805623a4687a6d1956517edc009abe5790a0870e89ab6ccb4e88"
CURRENT_AUTHORITY_EXTENSION_SHA256 = "ea9665470bccefa3c0d84c11dc888ed63fd544cdceb6d5dd8d61ba50ef252e30"

_impl.BASE_MISSION_SHA256 = CURRENT_BASE_MISSION_SHA256
_impl.AUTHORITY_EXTENSION_SHA256 = CURRENT_AUTHORITY_EXTENSION_SHA256

ACTION_CLASS = _impl.ACTION_CLASS
ALLOWED_HOSTS = _impl.ALLOWED_HOSTS
AUTHORITY_EXTENSION_ID = _impl.AUTHORITY_EXTENSION_ID
AUTHORITY_EXTENSION_PATH = _impl.AUTHORITY_EXTENSION_PATH
AUTHORITY_EXTENSION_SHA256 = CURRENT_AUTHORITY_EXTENSION_SHA256
BASE_MISSION_ID = _impl.BASE_MISSION_ID
BASE_MISSION_SHA256 = CURRENT_BASE_MISSION_SHA256
CLAIMS = _impl.CLAIMS
MAX_REQUESTS = _impl.MAX_REQUESTS
MAX_SOURCE_BYTES = _impl.MAX_SOURCE_BYTES
MAX_TOTAL_BYTES = _impl.MAX_TOTAL_BYTES
POLICY_ID = _impl.POLICY_ID
POLICY_PATH = _impl.POLICY_PATH
POLICY_SHA256 = _impl.POLICY_SHA256
SOURCE_DOI = _impl.SOURCE_DOI
SOURCE_ID = _impl.SOURCE_ID
SOURCE_PMCID = _impl.SOURCE_PMCID
SOURCE_PMID = _impl.SOURCE_PMID
SOURCE_TITLE = _impl.SOURCE_TITLE
SOURCE_URL = _impl.SOURCE_URL
TIMEOUT_SECONDS = _impl.TIMEOUT_SECONDS
Weaver2021FullTextPolicyError = _impl.Weaver2021FullTextPolicyError
authenticate_weaver_2021_full_text_policy = _impl.authenticate_weaver_2021_full_text_policy

__all__ = [
    "ACTION_CLASS",
    "ALLOWED_HOSTS",
    "AUTHORITY_EXTENSION_ID",
    "AUTHORITY_EXTENSION_PATH",
    "AUTHORITY_EXTENSION_SHA256",
    "BASE_MISSION_ID",
    "BASE_MISSION_SHA256",
    "CLAIMS",
    "MAX_REQUESTS",
    "MAX_SOURCE_BYTES",
    "MAX_TOTAL_BYTES",
    "POLICY_ID",
    "POLICY_PATH",
    "POLICY_SHA256",
    "SOURCE_DOI",
    "SOURCE_ID",
    "SOURCE_PMCID",
    "SOURCE_PMID",
    "SOURCE_TITLE",
    "SOURCE_URL",
    "TIMEOUT_SECONDS",
    "Weaver2021FullTextPolicyError",
    "authenticate_weaver_2021_full_text_policy",
]
