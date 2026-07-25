from __future__ import annotations

from typing import Any

from .persistence import semantic_hash
from .types import CorrectionAuditEntry, MatrixLedger, MatrixRef, TemporalRef, ValueRef



def _contains_reference(value: Any) -> bool:
    if isinstance(value, (ValueRef, MatrixRef, TemporalRef)):
        return True
    if isinstance(value, dict):
        return any(_contains_reference(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_reference(v) for v in value)
    return False

def apply_corrections(ledger: MatrixLedger) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, Any]]:
    """Build an effective declared-result view without mutating source transactions.

    v0.5 deliberately limits corrections to ``declared_result``. Every entry is
    appended to a hash chain so the original assertion and every amendment remain
    visible in the audit output.
    """
    effective = {tx_id: tx.declared_result for tx_id, tx in ledger.transactions.items()}
    applied: dict[str, list[str]] = {tx_id: [] for tx_id in ledger.transactions}
    entries: list[CorrectionAuditEntry] = []
    previous_hash = "0" * 64
    for correction in ledger.corrections:
        if correction.target_tx_id not in ledger.transactions:
            raise KeyError(f"Correction targets missing transaction: {correction.target_tx_id}")
        if correction.field not in {"declared_result", "expected_result"}:
            raise ValueError(f"Unsupported correction field: {correction.field}")
        if _contains_reference(correction.value):
            raise ValueError(
                f"Correction values cannot introduce dependencies in v0.5: {correction.correction_id}"
            )
        before = effective[correction.target_tx_id]
        if correction.mode == "replace":
            after = correction.value
        elif correction.mode == "delta":
            if before is None:
                raise ValueError(f"Cannot apply delta correction to null value: {correction.correction_id}")
            after = before + correction.value
        else:
            raise ValueError(f"Unsupported correction mode: {correction.mode}")
        payload = {
            "correction_id": correction.correction_id,
            "target_tx_id": correction.target_tx_id,
            "field": correction.field,
            "mode": correction.mode,
            "value": correction.value,
            "reason": correction.reason,
            "metadata": correction.metadata,
            "before": before,
            "after": after,
            "previous_hash": previous_hash,
        }
        entry_hash = semantic_hash(payload)
        entries.append(CorrectionAuditEntry(
            correction_id=correction.correction_id,
            target_tx_id=correction.target_tx_id,
            field=correction.field,
            mode=correction.mode,
            before=before,
            after=after,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        ))
        effective[correction.target_tx_id] = after
        applied[correction.target_tx_id].append(correction.correction_id)
        previous_hash = entry_hash
    analysis = {
        "enabled": bool(ledger.corrections),
        "append_only": True,
        "original_values_preserved": True,
        "entry_count": len(entries),
        "entries": entries,
        "head_hash": previous_hash,
    }
    return effective, applied, analysis
