"""Cross-file content checks for NASA review evidence."""
from __future__ import annotations


import numpy as np
import pandas as pd

from ._nasa_review_evidence_validation import (
    _DUPLICATE_SKIP_REASON,
    _INVENTORY_COUNT_FIELDS,
    _ids,
)

def _aggregated_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working["battery_id"] = _ids(working, context="NASA source inventory")
    if "skip_reason" in working.columns:
        working = working[
            working["skip_reason"].fillna("") != _DUPLICATE_SKIP_REASON
        ].copy()
    count_columns = [
        column for column in _INVENTORY_COUNT_FIELDS if column in working.columns
    ]
    if not count_columns:
        return pd.DataFrame({"battery_id": sorted(set(working["battery_id"]))})
    for column in count_columns:
        working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0)
    return working.groupby("battery_id", sort=True)[count_columns].sum().reset_index()


def _same_column(left: pd.Series, right: pd.Series, *, context: str) -> None:
    left_num = pd.to_numeric(left, errors="coerce")
    right_num = pd.to_numeric(right, errors="coerce")
    numeric = (
        left_num[~left.isna()].notna().all()
        and right_num[~right.isna()].notna().all()
    )
    if numeric:
        if not left_num.isna().equals(right_num.isna()) or not np.isclose(
            left_num.fillna(0).to_numpy(dtype=float),
            right_num.fillna(0).to_numpy(dtype=float),
            rtol=1e-9,
            atol=1e-9,
        ).all():
            raise ValueError(f"NASA analysis/import content mismatch: {context}")
        return
    left_text = left.astype("string").str.strip().fillna("<missing>")
    right_text = right.astype("string").str.strip().fillna("<missing>")
    if not left_text.equals(right_text):
        raise ValueError(f"NASA analysis/import content mismatch: {context}")


def _bind_import_content(
    queue: pd.DataFrame,
    protocol: pd.DataFrame,
    inventory: pd.DataFrame,
) -> dict[str, set[str]]:
    queue = queue.copy()
    protocol = protocol.copy()
    queue["battery_id"] = _ids(queue, context="NASA protocol review queue")
    protocol["battery_id"] = _ids(protocol, context="NASA protocol summary")
    inventory = _aggregated_inventory(inventory)
    queue_ids = set(queue["battery_id"])
    protocol_ids = set(protocol["battery_id"])
    inventory_ids = set(inventory["battery_id"].astype(str))
    if queue_ids != protocol_ids:
        raise ValueError("review queue and protocol-summary battery identities differ")
    missing_inventory = sorted(queue_ids - inventory_ids)
    if missing_inventory:
        raise ValueError(
            "review queue batteries are missing from source inventory: "
            + ", ".join(missing_inventory)
        )
    queue = queue.set_index("battery_id").sort_index()
    protocol = protocol.set_index("battery_id").sort_index()
    inventory = inventory.set_index("battery_id").sort_index().loc[sorted(queue_ids)]
    protocol_columns = sorted(set(queue.columns) & set(protocol.columns))
    if not protocol_columns:
        raise ValueError("review queue and protocol summary share no auditable columns")
    for column in protocol_columns:
        _same_column(queue[column], protocol[column], context=f"protocol.{column}")
    for column in sorted(set(queue.columns) & set(inventory.columns)):
        _same_column(queue[column], inventory[column], context=f"inventory.{column}")
    return {
        "queue_battery_ids": queue_ids,
        "inventory_battery_ids": inventory_ids,
        "inventory_only_battery_ids": inventory_ids - queue_ids,
    }


