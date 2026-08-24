from __future__ import annotations

from pathlib import Path

TARGET = Path("src/materials_data_analyzer/research_loop/public_data_acquisition.py")

text = TARGET.read_text(encoding="utf-8")

replacements = [
    (
        "import socket\nfrom collections.abc import Callable, Mapping, Sequence\n",
        "import socket\nfrom http.client import HTTPException\nfrom collections.abc import Callable, Mapping, Sequence\n",
    ),
    (
        '_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")\n',
        '_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")\n'
        "_TRANSIENT_HTTP_STATUS_CODES = frozenset(\n"
        "    {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}\n"
        ")\n",
    ),
    (
        "            if status < 200 or status >= 300:\n"
        "                raise PublicAcquisitionTransportError(\n"
        "                    f\"HTTP acquisition returned non-success status {status}\"\n"
        "                )\n",
        "            if status < 200 or status >= 300:\n"
        "                error_cls = (\n"
        "                    PublicAcquisitionTransportError\n"
        "                    if status in _TRANSIENT_HTTP_STATUS_CODES\n"
        "                    else PublicAcquisitionError\n"
        "                )\n"
        "                raise error_cls(\n"
        "                    f\"HTTP acquisition returned non-success status {status}\"\n"
        "                )\n",
    ),
    (
        "    except PublicAcquisitionError:\n"
        "        raise\n"
        "    except (HTTPError, URLError, TimeoutError, socket.timeout, OSError) as exc:\n"
        "        raise PublicAcquisitionTransportError(\n"
        "            f\"HTTP acquisition failed: {exc}\"\n"
        "        ) from exc\n",
        "    except PublicAcquisitionError:\n"
        "        raise\n"
        "    except HTTPError as exc:\n"
        "        error_cls = (\n"
        "            PublicAcquisitionTransportError\n"
        "            if exc.code in _TRANSIENT_HTTP_STATUS_CODES\n"
        "            else PublicAcquisitionError\n"
        "        )\n"
        "        raise error_cls(\n"
        "            f\"HTTP acquisition failed: {exc.code}: {exc.reason}\"\n"
        "        ) from exc\n"
        "    except (HTTPException, URLError, TimeoutError, socket.timeout, OSError) as exc:\n"
        "        raise PublicAcquisitionTransportError(\n"
        "            f\"HTTP acquisition failed: {exc}\"\n"
        "        ) from exc\n",
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one old fragment, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)

TARGET.write_text(text, encoding="utf-8")
