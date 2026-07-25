from __future__ import annotations

from collections import defaultdict
from typing import Any

from .errors import DependencyCycleError, MMLCError
from .types import FixedPointGroup, MatrixLedger


def execution_units(
    ledger: MatrixLedger,
    deps: dict[str, set[str]],
    priority_order: list[str],
) -> tuple[list[tuple[str, str]], dict[str, FixedPointGroup], dict[str, str]]:
    """Collapse declared fixed-point groups and topologically order the units."""
    groups = {group.group_id: group for group in ledger.fixed_point_groups}
    member_to_group: dict[str, str] = {}
    for group in ledger.fixed_point_groups:
        if not group.members:
            raise DependencyCycleError(f"Fixed-point group {group.group_id} has no members")
        for member in group.members:
            if member not in ledger.transactions:
                raise DependencyCycleError(f"Fixed-point group {group.group_id} references missing transaction {member}")
            if member in member_to_group:
                raise DependencyCycleError(f"Transaction {member} appears in multiple fixed-point groups")
            member_to_group[member] = group.group_id

    def unit_of(tx_id: str) -> str:
        return f"group:{member_to_group[tx_id]}" if tx_id in member_to_group else f"tx:{tx_id}"

    unit_members: dict[str, set[str]] = defaultdict(set)
    for tx_id in ledger.transactions:
        unit_members[unit_of(tx_id)].add(tx_id)
    unit_deps: dict[str, set[str]] = {unit: set() for unit in unit_members}
    for child, parents in deps.items():
        child_unit = unit_of(child)
        for parent in parents:
            parent_unit = unit_of(parent)
            if parent_unit != child_unit:
                unit_deps[child_unit].add(parent_unit)

    rank = {tx_id: i for i, tx_id in enumerate(priority_order)}
    unit_rank = {
        unit: min(rank.get(tx_id, 10**9) for tx_id in members)
        for unit, members in unit_members.items()
    }
    children: dict[str, set[str]] = {unit: set() for unit in unit_deps}
    indegree = {unit: len(parents) for unit, parents in unit_deps.items()}
    for child, parents in unit_deps.items():
        for parent in parents:
            children[parent].add(child)
    ready = sorted((unit for unit, degree in indegree.items() if degree == 0), key=lambda u: (unit_rank[u], u))
    ordered_units: list[str] = []
    while ready:
        unit = ready.pop(0)
        ordered_units.append(unit)
        for child in sorted(children[unit], key=lambda u: (unit_rank[u], u)):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=lambda u: (unit_rank[u], u))
    if len(ordered_units) != len(unit_deps):
        cyclic = sorted(unit for unit, degree in indegree.items() if degree > 0)
        raise DependencyCycleError(f"Undeclared or cross-group dependency cycle detected: {cyclic}")

    plan: list[tuple[str, str]] = []
    for unit in ordered_units:
        kind, identifier = unit.split(":", 1)
        plan.append((kind, identifier))
    return plan, groups, member_to_group


def convergence_delta(old: dict[str, Any], new: dict[str, Any]) -> float:
    deltas: list[float] = []
    for key in old:
        try:
            oval = float(old[key])
            nval = float(new[key])
            scale = 1.0 + abs(oval) + abs(nval)
            deltas.append(abs(nval - oval) / scale)
        except Exception as exc:
            raise MMLCError(f"Fixed-point values must be numeric: {key}: {exc}") from exc
    return max(deltas, default=0.0)
