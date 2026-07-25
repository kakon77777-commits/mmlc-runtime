from __future__ import annotations

from typing import Any

from .types import MatrixLedger, TransactionResult


def build_temporal_analysis(ledger: MatrixLedger, dependency_channels: dict[str, dict[str, set[str]]], results: dict[str, TransactionResult] | None = None) -> dict[str, Any]:
    periods = sorted({int(tx.time_index) for tx in ledger.transactions.values()})
    series: dict[str, list[dict[str, Any]]] = {}
    delayed_edges: list[dict[str, Any]] = []
    for tx_id, tx in ledger.transactions.items():
        sid = tx.series_id or tx.tx_id
        series.setdefault(sid, []).append({"tx_id": tx_id, "time_index": int(tx.time_index)})
    for sid in series:
        series[sid].sort(key=lambda item: (item["time_index"], item["tx_id"]))
    for child, parents in dependency_channels.items():
        ctime = int(ledger.transactions[child].time_index)
        for parent, channels in parents.items():
            ptime = int(ledger.transactions[parent].time_index)
            lag = ctime - ptime
            if any(":temporal:" in channel for channel in channels):
                delayed_edges.append({
                    "parent": parent,
                    "child": child,
                    "parent_time": ptime,
                    "child_time": ctime,
                    "lag": lag,
                    "channels": sorted(channels),
                })
    snapshots: dict[str, dict[str, Any]] = {}
    if results is not None:
        for tx_id, result in results.items():
            period = str(int(ledger.transactions[tx_id].time_index))
            snapshots.setdefault(period, {})[tx_id] = {
                "series_id": ledger.transactions[tx_id].series_id or tx_id,
                "computed_result": result.computed_result,
                "audited_result": result.audited_result,
                "status": result.status,
            }
    return {
        "enabled": bool(delayed_edges or len(periods) > 1),
        "periods": periods,
        "series": series,
        "delayed_edges": delayed_edges,
        "causal_time_order_valid": all(edge["lag"] >= 0 for edge in delayed_edges),
        "state_snapshots": snapshots,
    }
