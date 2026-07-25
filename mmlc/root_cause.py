from __future__ import annotations

from typing import Any

from .types import TransactionResult


def build_root_cause_analysis(
    results: dict[str, TransactionResult],
    deps: dict[str, set[str]],
) -> dict[str, Any]:
    """Propagate roots and one witness path in a single topological pass.

    ``results`` preserves Runtime execution order, which is already a stable
    topological ordering. Only unhealthy dependency edges propagate roots.
    This avoids the O(R * V * BFS) behaviour of the v0.2 prototype draft.
    """
    order = list(results)
    roots_by_tx: dict[str, set[str]] = {}
    paths_by_tx: dict[str, dict[str, list[str]]] = {}
    seed_roots: list[str] = []

    for tx_id in order:
        result = results[tx_id]
        inherited: set[str] = set()
        witness_paths: dict[str, list[str]] = {}
        for parent in result.unhealthy_dependencies:
            for root in roots_by_tx.get(parent, set()):
                inherited.add(root)
                parent_path = paths_by_tx.get(parent, {}).get(root, [root, parent] if root != parent else [root])
                witness_paths.setdefault(root, [*parent_path, tx_id])

        if result.status == "PASS":
            roots: set[str] = set()
            witness_paths = {}
        elif inherited:
            roots = inherited
        elif result.local_status in {"FAIL", "ERROR"}:
            roots = {tx_id}
            witness_paths = {tx_id: [tx_id]}
            seed_roots.append(tx_id)
        else:
            # Defensive fallback: an unhealthy transaction without a known
            # upstream root becomes its own explicit root rather than vanishing.
            roots = {tx_id}
            witness_paths = {tx_id: [tx_id]}
            seed_roots.append(tx_id)

        roots_by_tx[tx_id] = roots
        paths_by_tx[tx_id] = witness_paths
        result.root_causes = sorted(roots)

    seed_roots = sorted(set(seed_roots))
    per_transaction: dict[str, Any] = {}
    affected_by_root: dict[str, list[str]] = {root: [] for root in seed_roots}
    for tx_id in order:
        result = results[tx_id]
        for root in result.root_causes:
            affected_by_root.setdefault(root, []).append(tx_id)
        per_transaction[tx_id] = {
            "status": result.status,
            "local_status": result.local_status,
            "dependencies": sorted(deps.get(tx_id, set())),
            "unhealthy_dependencies": list(result.unhealthy_dependencies),
            "dependency_channels": dict(result.dependency_channels),
            "root_causes": list(result.root_causes),
            "paths": {root: paths_by_tx[tx_id][root] for root in result.root_causes},
        }

    return {
        "root_causes": seed_roots,
        "affected_by_root": affected_by_root,
        "per_transaction": per_transaction,
    }
