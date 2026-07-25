from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .dependency import ancestors, descendants
from .layout import PHYSICAL_TRAVERSALS, path_metrics, physical_sequence
from .types import MatrixLedger


def traverse(
    ledger: MatrixLedger,
    name: str,
    execution_order: list[str],
    deps: dict[str, set[str]],
    start: str | None = None,
    region: str | None = None,
    role: str = "display",
    deterministic: bool = False,
) -> dict[str, Any]:
    if name in PHYSICAL_TRAVERSALS:
        visited = physical_sequence(ledger, name, region=region)
    elif name == "dependency_topological":
        visited = list(execution_order)
        if region is not None:
            visited = [tx_id for tx_id in visited if ledger.transactions[tx_id].region == region]
    elif name == "reverse_dependency":
        if start is None:
            raise ValueError("reverse_dependency requires start")
        visited = [start, *ancestors(start, deps)]
    elif name == "breadth_first_from_error":
        if start is None:
            raise ValueError("breadth_first_from_error requires start")
        visited = [start, *descendants(start, deps)]
    else:
        raise ValueError(f"Unknown traversal: {name}")
    timestamp = "1970-01-01T00:00:00+00:00" if deterministic else datetime.now(timezone.utc).isoformat()
    return {
        "traversal": name,
        "role": role,
        "start": start,
        "region": region,
        "visited": visited,
        "coordinates": {
            tx_id: {"row": ledger.coordinates[tx_id].row, "column": ledger.coordinates[tx_id].column}
            for tx_id in visited
            if tx_id in ledger.coordinates
        },
        "metrics": path_metrics(ledger, visited),
        "timestamp": timestamp,
    }
