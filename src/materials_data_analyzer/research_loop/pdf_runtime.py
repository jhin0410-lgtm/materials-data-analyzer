"""Parser policy for current, potentially external PDF inputs.

Historical replay belongs to the separately installed baseline distribution;
there is deliberately no environment-variable override of this policy.
"""
from importlib import metadata

CURRENT_PYPDF_VERSION = "6.21.4"


def require_current_pdf_parser() -> None:
    installed = metadata.version("pypdf")
    if installed != CURRENT_PYPDF_VERSION:
        raise ValueError(
            f"external PDF processing requires pypdf=={CURRENT_PYPDF_VERSION}; "
            f"installed {installed}. Historical replay must use the isolated baseline."
        )
