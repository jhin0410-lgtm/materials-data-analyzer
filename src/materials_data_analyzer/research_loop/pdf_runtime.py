"""Compatibility import for the shared safe PDF runtime policy."""
from ..pdf_runtime import (
    CURRENT_PYPDF_VERSION,
    metadata,
    read_pdf,
    require_current_pdf_parser,
)

__all__ = ["CURRENT_PYPDF_VERSION", "metadata", "read_pdf", "require_current_pdf_parser"]
