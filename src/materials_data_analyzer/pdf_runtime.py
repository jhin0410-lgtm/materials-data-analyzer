"""Single approved parser entry point for current and retained PDF sources."""
from importlib import metadata
from io import BytesIO

from pypdf import PdfReader

CURRENT_PYPDF_VERSION = "6.21.4"
MAX_PDF_BYTES = 32 * 1024 * 1024
MAX_PDF_PAGES = 1024


def require_current_pdf_parser() -> None:
    installed = metadata.version("pypdf")
    if installed != CURRENT_PYPDF_VERSION:
        raise ValueError(
            f"external PDF processing requires pypdf=={CURRENT_PYPDF_VERSION}; "
            f"installed {installed}. Reprocess retained originals with the approved parser."
        )


def read_pdf(body: bytes) -> PdfReader:
    """Guard before passing any current or historical bytes to the parser.

    A parser upgrade requires explicit review of the pin and source contracts.
    Callers preserve their established plain/layout and normalization semantics.
    This does not replace process isolation for untrusted documents.
    """
    require_current_pdf_parser()
    if not isinstance(body, bytes) or not body.startswith(b"%PDF-"):
        raise ValueError("source is not exact PDF bytes")
    if len(body) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds shared byte budget")
    reader = PdfReader(BytesIO(body), strict=False)
    if not 0 < len(reader.pages) <= MAX_PDF_PAGES:
        raise ValueError("PDF page count exceeds shared budget or is empty")
    return reader
