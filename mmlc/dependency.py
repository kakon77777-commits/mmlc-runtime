from __future__ import annotations

from collections import deque
from typing import Any

from .errors import DependencyCycleError, MissingReferenceError, TraversalSemanticError
from .layout import PHYSICAL_TRAVERSALS, physical_sequence, spatial_neighbour, traversal_neighbour
from .types import MatrixLedger, MatrixRef, TemporalRef, ValueRef


def referenced_transaction_fields(value: object) -> list[tuple[str, str]]:
    if isinstance(value, ValueRef):
        return [(value.tx_id, value.field)]
    if isinstance(value, dict):
        refs: list[tuple[str, str]] = []
        for child in value.values():
            refs.extend(referenced_transaction_fields(child))
        return refs
    if isinstance(value, (list, tuple)):
        refs = []
        for child in value:
            refs.extend(referenced_transaction_fields(child))
        return refs
    return []


def matrix_references(value: object) -> list[MatrixRef]:
    if isinstance(value, MatrixRef):
        return [value]
    if isinstance(value, dict):
        refs: list[MatrixRef] = []
        for child in value.values():
            refs.extend(matrix_references(child))
        return refs
    if isinstance(value, (list, tuple)):
        refs = []
        for child in value:
            refs.extend(matrix_references(child))
        return refs
    return []



def temporal_references(value: object) -> list[TemporalRef]:
    if isinstance(value, TemporalRef):
        return [value]
    if isinstance(value, dict):
        refs: list[TemporalRef] = []
        for child in value.values():
            refs.extend(temporal_references(child))
        return refs
    if isinstance(value, (list, tuple)):
        refs: list[TemporalRef] = []
        for child in value:
            refs.extend(temporal_references(child))
        return refs
    return []


def temporal_index(ledger: MatrixLedger) -> dict[tuple[str, int], str]:
    index: dict[tuple[str, int], str] = {}
    for tx_id, tx in ledger.transactions.items():
        series = tx.series_id or tx.tx_id
        key = (series, int(tx.time_index))
        if key in index:
            raise MissingReferenceError(f"Duplicate temporal key {key}: {index[key]}, {tx_id}")
        index[key] = tx_id
    return index


def resolve_temporal_target(ledger: MatrixLedger, current_tx_id: str, ref: TemporalRef, index: dict[tuple[str, int], str] | None = None) -> str | None:
    if ref.lag < 0:
        raise TraversalSemanticError("Temporal lag must be non-negative")
    tx = ledger.transactions[current_tx_id]
    target_time = int(tx.time_index) - int(ref.lag)
    lookup = index if index is not None else temporal_index(ledger)
    return lookup.get((ref.series_id, target_time))

def contains_matrix_reference(value: object) -> bool:
    return bool(matrix_references(value))


def referenced_transactions(value: object) -> list[str]:
    return [tx_id for tx_id, _ in referenced_transaction_fields(value)]


def active_physical_sequence(ledger: MatrixLedger, execution_traversal: str) -> list[str]:
    if execution_traversal not in PHYSICAL_TRAVERSALS:
        raise TraversalSemanticError(
            f"Matrix-relative previous/next references require a physical execution traversal; got {execution_traversal}"
        )
    return physical_sequence(ledger, execution_traversal)


def resolve_matrix_target(
    ledger: MatrixLedger,
    tx_id: str,
    ref: MatrixRef,
    execution_traversal: str,
    sequence: list[str] | None = None,
) -> str | None:
    if ref.relation in {"left", "right", "up", "down"}:
        return spatial_neighbour(ledger, tx_id, ref.relation)
    if ref.relation in {"previous", "next"}:
        seq = sequence if sequence is not None else active_physical_sequence(ledger, execution_traversal)
        return traversal_neighbour(seq, tx_id, ref.relation)
    raise TraversalSemanticError(f"Unsupported matrix relation: {ref.relation}")


def build_dependency_edges(
    ledger: MatrixLedger,
    execution_traversal: str = "dependency_topological",
) -> dict[str, dict[str, set[str]]]:
    edges: dict[str, dict[str, set[str]]] = {tx_id: {} for tx_id in ledger.transactions}
    tindex = temporal_index(ledger)
    has_relative = any(
        contains_matrix_reference(value)
        for tx in ledger.transactions.values()
        for value in (tx.base, tx.operand, tx.declared_result, tx.context)
    )
    sequence = active_physical_sequence(ledger, execution_traversal) if has_relative and any(
        ref.relation in {"previous", "next"}
        for tx in ledger.transactions.values()
        for value in (tx.base, tx.operand, tx.declared_result, tx.context)
        for ref in matrix_references(value)
    ) else None

    for tx_id, tx in ledger.transactions.items():
        for dep in tx.dependencies:
            edges[tx_id].setdefault(dep, set()).add("explicit")
        for value, location in (
            (tx.base, "base"),
            (tx.operand, "operand"),
            (tx.declared_result, "declared_result"),
            (tx.context, "context"),
        ):
            for dep, field in referenced_transaction_fields(value):
                edges[tx_id].setdefault(dep, set()).add(f"{location}:{field}")
            for ref in matrix_references(value):
                target = resolve_matrix_target(ledger, tx_id, ref, execution_traversal, sequence)
                if target is None:
                    if not ref.has_default:
                        raise MissingReferenceError(
                            f"Transaction {tx_id} has no {ref.relation} neighbour and no default"
                        )
                    continue
                edges[tx_id].setdefault(target, set()).add(
                    f"{location}:{ref.field}:matrix:{ref.relation}"
                )
            for ref in temporal_references(value):
                target = resolve_temporal_target(ledger, tx_id, ref, tindex)
                if target is None:
                    if not ref.has_default:
                        raise MissingReferenceError(
                            f"Transaction {tx_id} has no temporal target series={ref.series_id} lag={ref.lag}"
                        )
                    continue
                edges[tx_id].setdefault(target, set()).add(
                    f"{location}:{ref.field}:temporal:{ref.series_id}:lag={ref.lag}"
                )
        for dep in edges[tx_id]:
            if dep not in ledger.transactions:
                raise MissingReferenceError(f"Transaction {tx_id} references missing transaction {dep}")
    return edges


def build_dependencies(
    ledger: MatrixLedger,
    execution_traversal: str = "dependency_topological",
) -> dict[str, set[str]]:
    edges = build_dependency_edges(ledger, execution_traversal)
    return {tx_id: set(parents) for tx_id, parents in edges.items()}


def stable_topological_sort(
    ledger: MatrixLedger,
    deps: dict[str, set[str]],
    priority_order: list[str] | None = None,
) -> list[str]:
    rank_order = priority_order or ledger.display_order
    display_rank = {tx_id: i for i, tx_id in enumerate(rank_order)}
    in_degree = {tx_id: len(parents) for tx_id, parents in deps.items()}
    children: dict[str, set[str]] = {tx_id: set() for tx_id in deps}
    for child, parents in deps.items():
        for parent in parents:
            children[parent].add(child)
    ready = sorted((tx for tx, degree in in_degree.items() if degree == 0), key=lambda x: (display_rank.get(x, 10**9), x))
    result: list[str] = []
    while ready:
        current = ready.pop(0)
        result.append(current)
        for child in sorted(children[current], key=lambda x: (display_rank.get(x, 10**9), x)):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                ready.append(child)
                ready.sort(key=lambda x: (display_rank.get(x, 10**9), x))
    if len(result) != len(deps):
        cyclic = sorted(tx for tx, degree in in_degree.items() if degree > 0)
        raise DependencyCycleError(f"Dependency cycle detected: {cyclic}")
    return result


def reverse_graph(deps: dict[str, set[str]]) -> dict[str, set[str]]:
    children: dict[str, set[str]] = {tx_id: set() for tx_id in deps}
    for child, parents in deps.items():
        for parent in parents:
            children[parent].add(child)
    return children


def ancestors(start: str, deps: dict[str, set[str]]) -> list[str]:
    visited: set[str] = set()
    queue = deque(sorted(deps.get(start, set())))
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        queue.extend(sorted(deps.get(node, set())))
    return sorted(visited)


def descendants(start: str, deps: dict[str, set[str]]) -> list[str]:
    children = reverse_graph(deps)
    visited: set[str] = set()
    queue = deque(sorted(children.get(start, set())))
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        queue.extend(sorted(children.get(node, set())))
    return sorted(visited)


def find_path(root: str, target: str, deps: dict[str, set[str]]) -> list[str]:
    if root == target:
        return [root]
    children = reverse_graph(deps)
    queue: deque[tuple[str, list[str]]] = deque([(root, [root])])
    visited = {root}
    while queue:
        node, path = queue.popleft()
        for child in sorted(children.get(node, set())):
            if child in visited:
                continue
            next_path = [*path, child]
            if child == target:
                return next_path
            visited.add(child)
            queue.append((child, next_path))
    return []
