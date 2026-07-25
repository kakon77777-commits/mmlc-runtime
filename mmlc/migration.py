"""Deterministic MMLF migration into the stable 1.0 document profile."""

from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

from .errors import MMLCError
from .parser import load_ledger, load_raw_document, validate_raw
from .persistence import normalize, semantic_hash
from .runtime import Runtime
from .version import __version__


@dataclass(frozen=True)
class MigrationReport:
    source_path: str
    output_path: str
    source_version: str
    target_version: str
    ledger_id: str
    validated: bool
    execution_verified: bool
    execution_equivalent: bool | None
    source_outcome: str | None
    target_outcome: str | None
    source_snapshot_hash: str | None
    target_snapshot_hash: str | None
    migration_hash: str


def _strip_unstable(value: Any) -> Any:
    """Remove version/hash/runtime fields before compatibility comparison."""
    if isinstance(value, dict):
        source = dict(value)
        # Compare legacy and canonical intervention declarations by meaning, not
        # by surface syntax introduced during migration.
        if "target" in source and "target_tx_id" not in source:
            source["target_tx_id"] = source.pop("target")
        if "value" in source and "target_tx_id" in source and "kind" not in source:
            source["kind"] = "do_set"
        if str(source.get("id", "")).startswith("migrated-intervention-"):
            source.pop("id", None)
        result: dict[str, Any] = {}
        for key, item in source.items():
            if key in {
                "runtime_version",
                "ledger_version",
                "semantic_hash",
                "execution_hash",
                "analysis_hash",
                "branch_hash",
                "head_hash",
                "entry_hash",
                "previous_hash",
                "migration_hash",
            } or key.endswith("_hash"):
                continue
            result[str(key)] = _strip_unstable(item)
        return result
    if isinstance(value, list):
        return [_strip_unstable(item) for item in value]
    return value


def stable_execution_snapshot(result: Any) -> dict[str, Any]:
    data = normalize(result)
    return _strip_unstable({
        "ledger_id": data["ledger_id"],
        "execution_order": data["execution_order"],
        "execution_traversal": data["execution_traversal"],
        "transactions": data["transactions"],
        "global_audit": data["global_audit"],
        "constraint_audits": data["constraint_audits"],
        "cross_axis_conflicts": data["cross_axis_conflicts"],
        "repair_analysis": data["repair_analysis"],
        "temporal_analysis": data["temporal_analysis"],
        "fixed_point_analysis": data["fixed_point_analysis"],
        "correction_analysis": data["correction_analysis"],
        "fdcs_projection": data["fdcs_projection"],
    })


def migrate_document(data: dict[str, Any], *, target_version: str = "1.0") -> dict[str, Any]:
    if target_version != "1.0":
        raise ValueError(f"Unsupported migration target: {target_version}")
    validate_raw(data)
    migrated = copy.deepcopy(data)
    source_version = str(migrated.get("version", "0.1"))
    migrated["format"] = "MMLF"
    migrated["version"] = "1.0"

    # Canonicalise legacy intervention shorthand before validating against the
    # stable schema. The semantic profile remains the source version, so this
    # syntax normalisation does not activate features that were previously
    # declaration-only.
    fdcs = migrated.get("fdcs")
    if isinstance(fdcs, dict):
        intervention_lists: list[list[dict[str, Any]]] = []
        if isinstance(fdcs.get("interventions"), list):
            intervention_lists.append(fdcs["interventions"])
        for context in fdcs.get("contexts", []) if isinstance(fdcs.get("contexts"), list) else []:
            if isinstance(context, dict) and isinstance(context.get("interventions"), list):
                intervention_lists.append(context["interventions"])
        for items in intervention_lists:
            for position, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                item.setdefault("id", f"migrated-intervention-{position + 1}")
                item.setdefault("kind", "do_set")
                if "target_tx_id" not in item and "target" in item:
                    item["target_tx_id"] = item.pop("target")

    metadata = dict(migrated.get("metadata", {}))
    metadata.setdefault("migrated_from", source_version)
    metadata["migrated_by"] = f"mmlc-runtime {__version__}"
    metadata["migration_profile"] = "mmlf-stable-1.0"
    migrated["metadata"] = metadata
    validate_raw(migrated)
    return migrated


def _write_document(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("Migration output must end in .yaml, .yml, or .json")
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def _execute_outcome(path: Path) -> tuple[str, str | None]:
    try:
        result = Runtime().execute(load_ledger(path), deterministic=True)
    except Exception as exc:  # Compatibility includes preserving explicit failures.
        return f"ERROR:{exc.__class__.__name__}", None
    snapshot_hash = semantic_hash(stable_execution_snapshot(result))
    return f"RESULT:{result.global_audit.get('status', 'UNKNOWN')}", snapshot_hash


def migrate_file(
    source: str | Path,
    output: str | Path,
    *,
    target_version: str = "1.0",
    verify_execution: bool = True,
) -> MigrationReport:
    source_path = Path(source)
    output_path = Path(output)
    raw = load_raw_document(source_path)
    source_version = str(raw.get("version", "0.1"))
    ledger_id = str(raw.get("ledger_id", ""))
    migrated = migrate_document(raw, target_version=target_version)
    _write_document(output_path, migrated)
    load_ledger(output_path)  # Installed-schema validation and parser construction.

    source_outcome: str | None = None
    target_outcome: str | None = None
    source_hash: str | None = None
    target_hash: str | None = None
    equivalent: bool | None = None
    if verify_execution:
        source_outcome, source_hash = _execute_outcome(source_path)
        target_outcome, target_hash = _execute_outcome(output_path)
        equivalent = source_outcome == target_outcome and source_hash == target_hash
        if not equivalent:
            raise MMLCError(
                "Migration execution mismatch: "
                f"source={source_outcome}/{source_hash}, target={target_outcome}/{target_hash}"
            )

    migration_hash = semantic_hash({
        "source_version": source_version,
        "target_version": target_version,
        "ledger_id": ledger_id,
        "document": migrated,
        "source_outcome": source_outcome,
        "target_outcome": target_outcome,
        "source_snapshot_hash": source_hash,
        "target_snapshot_hash": target_hash,
    })
    return MigrationReport(
        source_path=str(source_path),
        output_path=str(output_path),
        source_version=source_version,
        target_version=target_version,
        ledger_id=ledger_id,
        validated=True,
        execution_verified=verify_execution,
        execution_equivalent=equivalent,
        source_outcome=source_outcome,
        target_outcome=target_outcome,
        source_snapshot_hash=source_hash,
        target_snapshot_hash=target_hash,
        migration_hash=migration_hash,
    )


def migration_report_dict(report: MigrationReport) -> dict[str, Any]:
    return asdict(report)
