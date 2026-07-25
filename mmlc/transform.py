from __future__ import annotations

from copy import deepcopy

from .types import MatrixLedger, SourceObject, Transaction
from .values import substitute_value


def instantiate_ledger(
    ledger: MatrixLedger,
    bindings: dict[str, object],
    *,
    ledger_id_suffix: str | None = None,
) -> MatrixLedger:
    """Create a bound ledger without mutating the symbolic source ledger."""
    suffix = ledger_id_suffix or "bound"
    sources = {
        source_id: SourceObject(
            object_id=source.object_id,
            type_name=source.type_name,
            value=substitute_value(source.value, bindings),
            metadata=deepcopy(source.metadata),
        )
        for source_id, source in ledger.sources.items()
    }
    transactions = {
        tx_id: Transaction(
            tx_id=tx.tx_id,
            source_id=tx.source_id,
            base=substitute_value(tx.base, bindings),
            operator=tx.operator,
            operand=substitute_value(tx.operand, bindings),
            declared_result=substitute_value(tx.declared_result, bindings),
            context=substitute_value(deepcopy(tx.context), bindings),
            dependencies=list(tx.dependencies),
            region=tx.region,
        )
        for tx_id, tx in ledger.transactions.items()
    }
    return MatrixLedger(
        ledger_id=f"{ledger.ledger_id}::{suffix}",
        version=ledger.version,
        sources=sources,
        transactions=transactions,
        display_order=list(ledger.display_order),
        layout=deepcopy(ledger.layout),
        coordinates=dict(ledger.coordinates),
        traversals=deepcopy(ledger.traversals),
        audit_policy=ledger.audit_policy,
        boundary_events=substitute_value(deepcopy(ledger.boundary_events), bindings),
        evaluation_scenarios=[],
        metadata={**deepcopy(ledger.metadata), "bindings": deepcopy(bindings), "parent_ledger_id": ledger.ledger_id},
    )
