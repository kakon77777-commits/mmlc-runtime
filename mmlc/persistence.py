from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .values import serialize_value


def normalize(value: Any) -> Any:
    if is_dataclass(value):
        return normalize(asdict(value))
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    return serialize_value(value)


def canonical_json(value: Any) -> str:
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def write_run(output_dir: Path, result: Any, report: str, deterministic: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized = normalize(result)
    (output_dir / "run_result.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    timestamp = "1970-01-01T00:00:00+00:00" if deterministic else datetime.now(timezone.utc).isoformat()
    events = []
    for tx_id in result.execution_order:
        tx_result = result.transactions[tx_id]
        events.append({
            "event": "transaction_audited",
            "timestamp": timestamp,
            "tx_id": tx_id,
            "status": tx_result.status,
            "computed_result": normalize(tx_result.computed_result),
            "audited_result": normalize(tx_result.audited_result),
            "checks": normalize(tx_result.checks),
            "coordinate": normalize(tx_result.coordinate),
            "time_index": tx_result.time_index,
            "series_id": tx_result.series_id,
            "corrections_applied": list(tx_result.corrections_applied),
            "fixed_point_group": tx_result.fixed_point_group,
            "execution_traversal": result.execution_traversal,
        })
    with (output_dir / "events.jsonl").open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    (output_dir / "manifest.json").write_text(
        json.dumps({**normalize(result.manifest), "written_at": timestamp}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
