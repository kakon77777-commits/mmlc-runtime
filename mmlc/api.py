"""Stable public API facade for MMLC Runtime 1.x."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .migration import MigrationReport, migrate_file
from .parser import load_ledger
from .persistence import write_run
from .report import fdcs_markdown_report, markdown_report
from .runtime import Runtime
from .stability import compatibility_manifest
from .types import RunResult
from .version import __version__


@dataclass(frozen=True)
class ValidationSummary:
    path: str
    ledger_id: str
    version: str
    transaction_count: int
    shape: tuple[int, int]
    fdcs_enabled: bool


def validate_file(path: str | Path) -> ValidationSummary:
    ledger = load_ledger(path)
    rows = len(ledger.layout)
    columns = max((len(row) for row in ledger.layout), default=0)
    return ValidationSummary(
        path=str(path),
        ledger_id=ledger.ledger_id,
        version=ledger.version,
        transaction_count=len(ledger.transactions),
        shape=(rows, columns),
        fdcs_enabled=bool(ledger.fdcs.get("enabled", False)),
    )


def execute_file(
    path: str | Path,
    *,
    deterministic: bool = True,
    execution_traversal: str | None = None,
) -> RunResult:
    ledger = load_ledger(path)
    return Runtime().execute(
        ledger,
        deterministic=deterministic,
        execution_traversal=execution_traversal,
    )


def simulate_fdcs_file(path: str | Path, *, deterministic: bool = True) -> RunResult:
    return execute_file(path, deterministic=deterministic)


def save_result(result: RunResult, output: str | Path, *, deterministic: bool = True) -> None:
    output_path = Path(output)
    write_run(output_path, result, markdown_report(result), deterministic=deterministic)
    if result.fdcs_projection.get("enabled"):
        (output_path / "fdcs_report.md").write_text(fdcs_markdown_report(result), encoding="utf-8")


def runtime_info() -> dict[str, Any]:
    return {
        "name": "mmlc-runtime",
        "display_name": "MMLC Runtime — Multidirectional Matrix Ledger Computation",
        "version": __version__,
        **compatibility_manifest(),
    }


__all__ = [
    "MigrationReport",
    "ValidationSummary",
    "execute_file",
    "migrate_file",
    "runtime_info",
    "save_result",
    "simulate_fdcs_file",
    "validate_file",
]
