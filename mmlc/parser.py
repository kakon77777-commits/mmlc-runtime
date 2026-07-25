from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from .errors import DuplicateIdError, SchemaValidationError
from .layout import build_layout
from .constraints import constraint_members_from_scope
from .types import (
    AuditPolicy, CorrectionEntry, EvaluationScenario, FixedPointGroup,
    MatrixConstraint, MatrixLedger, SourceObject, Transaction,
)
from .values import parse_value


def _load_raw(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    elif path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        raise SchemaValidationError(f"Unsupported ledger format: {path.suffix}")
    if not isinstance(data, dict):
        raise SchemaValidationError("Ledger root must be an object")
    return data


def _schema_name(version: object) -> str:
    version_text = str(version)
    supported = {
        "1.0": "mmlf-v1.0.schema.json",
        "0.9": "mmlf-v0.9.schema.json",
        "0.8": "mmlf-v0.8.schema.json",
        "0.7": "mmlf-v0.7.schema.json",
        "0.6": "mmlf-v0.6.schema.json",
        "0.5": "mmlf-v0.5.schema.json",
        "0.4": "mmlf-v0.4.schema.json",
        "0.3": "mmlf-v0.3.schema.json",
        "0.2": "mmlf-v0.2.schema.json",
        "0.1": "mmlf-v0.1.schema.json",
    }
    for prefix, name in supported.items():
        if version_text == prefix or version_text.startswith(prefix + "."):
            return name
    raise SchemaValidationError(f"Unsupported MMLF version: {version_text}")


def schema_text(version: object) -> str:
    resource = files("mmlc.schemas").joinpath(_schema_name(version))
    return resource.read_text(encoding="utf-8")


def validate_raw(data: dict[str, Any]) -> None:
    schema = json.loads(schema_text(data.get("version", "0.1")))
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path)
        raise SchemaValidationError(f"Schema error at {location or '<root>'}: {exc.message}") from exc


def load_ledger(path: str | Path) -> MatrixLedger:
    source_path = Path(path)
    data = _load_raw(source_path)
    validate_raw(data)

    source_ids = [str(obj["id"]) for obj in data.get("objects", [])]
    tx_ids = [str(branch["id"]) for branch in data["branches"]]
    scenario_ids = [str(item["id"]) for item in data.get("evaluation_scenarios", [])]
    if len(set(source_ids)) != len(source_ids):
        raise DuplicateIdError("Duplicate source object ID")
    if len(set(tx_ids)) != len(tx_ids):
        raise DuplicateIdError("Duplicate transaction ID")
    if len(set(scenario_ids)) != len(scenario_ids):
        raise DuplicateIdError("Duplicate evaluation scenario ID")

    sources = {
        str(obj["id"]): SourceObject(
            object_id=str(obj["id"]),
            type_name=str(obj["type"]),
            value=parse_value(obj["value"]),
            metadata=dict(obj.get("metadata", {})),
        )
        for obj in data.get("objects", [])
    }
    transactions: dict[str, Transaction] = {}
    for branch in data["branches"]:
        tx_id = str(branch["id"])
        transactions[tx_id] = Transaction(
            tx_id=tx_id,
            source_id=branch.get("source_id"),
            base=parse_value(branch.get("base")),
            operator=str(branch["operator"]),
            operand=parse_value(branch.get("operand")),
            declared_result=parse_value(branch.get("expected_result")),
            context=parse_value(dict(branch.get("context", {}))),
            dependencies=[str(x) for x in branch.get("dependencies", [])],
            region=str(branch.get("region", "default")),
            time_index=int(branch.get("time_index", 0)),
            series_id=str(branch.get("series_id", tx_id)),
        )

    scenarios = [
        EvaluationScenario(
            scenario_id=str(item["id"]),
            bindings={str(k): parse_value(v) for k, v in dict(item["bindings"]).items()},
            metadata=dict(item.get("metadata", {})),
        )
        for item in data.get("evaluation_scenarios", [])
    ]

    policy_raw = data.get("audit_policy", {})
    policy = AuditPolicy(
        local_required=bool(policy_raw.get("local_required", True)),
        signed_global_cancellation_allowed=bool(policy_raw.get("signed_global_cancellation_allowed", False)),
        numeric_tolerance=float(policy_raw.get("numeric_tolerance", 1e-12)),
        required_checks=tuple(policy_raw.get("required_checks", AuditPolicy().required_checks)),
    )
    traversals = dict(data.get("traversals", {}))
    try:
        layout, coordinates, display_order = build_layout(tx_ids, data.get("layout"))
    except Exception as exc:
        if isinstance(exc, SchemaValidationError):
            raise
        raise SchemaValidationError(str(exc)) from exc

    constraints: list[MatrixConstraint] = []
    constraint_ids: set[str] = set()
    for item in data.get("constraints", []):
        constraint_id = str(item["id"])
        if constraint_id in constraint_ids:
            raise DuplicateIdError("Duplicate constraint ID")
        constraint_ids.add(constraint_id)
        try:
            axis, members = constraint_members_from_scope(
                layout,
                transactions,
                dict(item["scope"]),
            )
        except Exception as exc:
            raise SchemaValidationError(f"Constraint {constraint_id}: {exc}") from exc
        constraints.append(MatrixConstraint(
            constraint_id=constraint_id,
            kind=str(item["kind"]),
            axis=axis,
            members=members,
            field=str(item.get("field", "result")),
            target=parse_value(item.get("target", 0)),
            tolerance=float(item["tolerance"]) if "tolerance" in item else None,
            metadata=dict(item.get("metadata", {})),
        ))

    fixed_point_groups: list[FixedPointGroup] = []
    group_ids: set[str] = set()
    for item in data.get("fixed_point_groups", []):
        group_id = str(item["id"])
        if group_id in group_ids:
            raise DuplicateIdError("Duplicate fixed-point group ID")
        group_ids.add(group_id)
        fixed_point_groups.append(FixedPointGroup(
            group_id=group_id,
            members=tuple(str(x) for x in item["members"]),
            method=str(item.get("method", "jacobi")),
            tolerance=float(item.get("tolerance", 1e-10)),
            max_iterations=int(item.get("max_iterations", 200)),
            initial_values={str(k): parse_value(v) for k, v in dict(item.get("initial_values", {})).items()},
        ))

    corrections: list[CorrectionEntry] = []
    correction_ids: set[str] = set()
    for item in data.get("corrections", []):
        correction_id = str(item["id"])
        if correction_id in correction_ids:
            raise DuplicateIdError("Duplicate correction ID")
        correction_ids.add(correction_id)
        corrections.append(CorrectionEntry(
            correction_id=correction_id,
            target_tx_id=str(item["target_tx_id"]),
            field=str(item.get("field", "declared_result")),
            mode=str(item.get("mode", "replace")),
            value=parse_value(item["value"]),
            reason=str(item.get("reason", "")),
            metadata=dict(item.get("metadata", {})),
        ))

    return MatrixLedger(
        ledger_id=str(data["ledger_id"]),
        version=str(data["version"]),
        sources=sources,
        transactions=transactions,
        display_order=display_order,
        layout=layout,
        coordinates=coordinates,
        traversals=traversals,
        audit_policy=policy,
        boundary_events=list(data.get("boundary_events", [])),
        evaluation_scenarios=scenarios,
        constraints=constraints,
        fixed_point_groups=fixed_point_groups,
        corrections=corrections,
        fdcs=parse_value(dict(data.get("fdcs", {}))),
        metadata={
            "source_file": str(source_path),
            "format": data["format"],
            "document_metadata": dict(data.get("metadata", {})),
        },
    )


def load_raw_document(path: str | Path) -> dict[str, Any]:
    """Load a raw MMLF document without constructing runtime objects."""
    return _load_raw(Path(path))
