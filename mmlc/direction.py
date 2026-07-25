from __future__ import annotations

from collections import defaultdict

from .layout import PHYSICAL_TRAVERSALS
from .persistence import semantic_hash
from .runtime import Runtime
from .types import DirectionComparison, MatrixLedger


def compare_directions(
    ledger: MatrixLedger,
    directions: list[str] | None = None,
    *,
    runtime: Runtime | None = None,
) -> DirectionComparison:
    engine = runtime or Runtime()
    chosen = directions or [
        "left_to_right",
        "right_to_left",
        "top_to_bottom",
        "bottom_to_top",
    ]
    unknown = [name for name in chosen if name not in PHYSICAL_TRAVERSALS]
    if unknown:
        raise ValueError(f"compare_directions requires physical traversals; unknown={unknown}")
    runs = {
        name: engine.execute(ledger, deterministic=True, execution_traversal=name)
        for name in chosen
    }
    semantic_groups: dict[str, list[str]] = defaultdict(list)
    result_groups: dict[str, list[str]] = defaultdict(list)
    for name, run in runs.items():
        semantic_groups[run.semantic_hash].append(name)
        result_signature = semantic_hash({
            tx_id: {
                "computed_result": result.computed_result,
                "audited_result": result.audited_result,
                "status": result.status,
            }
            for tx_id, result in sorted(run.transactions.items())
        })
        result_groups[result_signature].append(name)
    semantic_classes = sorted((sorted(group) for group in semantic_groups.values()), key=lambda x: x[0])
    result_classes = sorted((sorted(group) for group in result_groups.values()), key=lambda x: x[0])
    return DirectionComparison(
        ledger_id=ledger.ledger_id,
        directions=list(chosen),
        runs=runs,
        semantic_equivalence_classes=semantic_classes,
        result_equivalence_classes=result_classes,
        direction_sensitive=len(semantic_classes) > 1,
    )
