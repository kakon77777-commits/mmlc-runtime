"""Semantic feature-profile helpers.

A document migrated to MMLF 1.0 preserves the execution semantics of its source
version through metadata.migrated_from. Native 1.0 documents use the full 1.0
profile.
"""

from __future__ import annotations

from typing import Any

from .types import MatrixLedger


def version_tuple(value: Any) -> tuple[int, ...]:
    text = str(value).strip().lstrip("v")
    parts: list[int] = []
    for token in text.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts or [0])


def semantic_profile(ledger: MatrixLedger) -> str:
    document_metadata = dict(ledger.metadata.get("document_metadata", {}))
    if document_metadata.get("migration_profile") == "mmlf-stable-1.0":
        source = document_metadata.get("migrated_from")
        if source:
            return str(source)
    return str(ledger.version)


def supports_profile(profile: str, minimum: str) -> bool:
    current = version_tuple(profile)
    required = version_tuple(minimum)
    length = max(len(current), len(required))
    return current + (0,) * (length - len(current)) >= required + (0,) * (length - len(required))


def ledger_supports(ledger: MatrixLedger, minimum: str) -> bool:
    return supports_profile(semantic_profile(ledger), minimum)
