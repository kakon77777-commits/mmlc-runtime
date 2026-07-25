from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .api import runtime_info, validate_file
from .benchmark import run_release_benchmarks
from .direction import compare_directions
from .errors import MMLCError
from .exchange import verify_symbolic_numeric_exchange
from .migration import migrate_file
from .parser import load_ledger
from .persistence import normalize, write_run
from .report import (
    direction_markdown_report,
    exchange_markdown_report,
    fdcs_markdown_report,
    markdown_report,
    representation_markdown_report,
)
from .representation import compare_representations
from .runtime import Runtime
from .version import __version__

EXIT_OK = 0
EXIT_USAGE_OR_VALIDATION = 2
EXIT_AUDIT_FAILURE = 3
EXIT_INTERNAL_ERROR = 4


def _print_json(value: object, *, stream: object | None = None) -> None:
    target = sys.stdout if stream is None else stream
    print(json.dumps(normalize(value), ensure_ascii=False, indent=2), file=target)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmlc",
        description=f"MMLC Runtime v{__version__}",
    )
    parser.add_argument("--version", action="version", version=f"mmlc-runtime {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="Print runtime/API/schema compatibility information")

    validate_p = sub.add_parser("validate", help="Validate MMLF YAML/JSON")
    validate_p.add_argument("ledger", type=Path)

    migrate_p = sub.add_parser("migrate", help="Migrate MMLF v0.1-v0.9 to stable v1.0")
    migrate_p.add_argument("ledger", type=Path)
    migrate_p.add_argument("--output", type=Path, required=True)
    migrate_p.add_argument("--no-execution-verify", action="store_true")

    benchmark_p = sub.add_parser("benchmark", help="Run small deterministic release benchmarks")
    benchmark_p.add_argument("--output", type=Path)
    benchmark_p.add_argument("--sizes", nargs="+", type=int, default=[64, 256, 1024])
    benchmark_p.add_argument("--repeats", type=int, default=3)

    run_p = sub.add_parser("run", help="Execute and audit a ledger")
    run_p.add_argument("ledger", type=Path)
    run_p.add_argument("--output", type=Path, required=True)
    run_p.add_argument("--deterministic", action="store_true")
    run_p.add_argument("--execution-traversal", type=str)
    run_p.add_argument("--fail-on-audit", action="store_true")

    exchange_p = sub.add_parser("verify-exchange", help="Verify symbolic-numeric commutation")
    exchange_p.add_argument("ledger", type=Path)
    exchange_p.add_argument("--output", type=Path, required=True)

    representation_p = sub.add_parser(
        "compare-representations",
        help="Compare MMLC constraints with a flat-table reference and factor graph",
    )
    representation_p.add_argument("ledger", type=Path)
    representation_p.add_argument("--output", type=Path, required=True)

    fdcs_p = sub.add_parser(
        "simulate-fdcs",
        help="Execute FDCS branches, uncertainty, policy, information-value and observation analysis",
    )
    fdcs_p.add_argument("ledger", type=Path)
    fdcs_p.add_argument("--output", type=Path, required=True)
    fdcs_p.add_argument("--deterministic", action="store_true")
    fdcs_p.add_argument("--fail-on-audit", action="store_true")

    direction_p = sub.add_parser("compare-directions", help="Execute one ledger under multiple traversals")
    direction_p.add_argument("ledger", type=Path)
    direction_p.add_argument("--output", type=Path, required=True)
    direction_p.add_argument(
        "--directions",
        nargs="+",
        default=["left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"],
    )
    return parser


def _run_command(args: argparse.Namespace) -> int:
    if args.command == "info":
        _print_json(runtime_info())
        return EXIT_OK

    if args.command == "validate":
        _print_json(asdict(validate_file(args.ledger)))
        return EXIT_OK

    if args.command == "migrate":
        report = migrate_file(
            args.ledger,
            args.output,
            verify_execution=not args.no_execution_verify,
        )
        _print_json(asdict(report))
        return EXIT_OK

    if args.command == "benchmark":
        result = run_release_benchmarks(sizes=args.sizes, repeats=args.repeats)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(normalize(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _print_json(result)
        return EXIT_OK

    ledger = load_ledger(args.ledger)
    if args.command == "verify-exchange":
        report = verify_symbolic_numeric_exchange(ledger)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "exchange_result.json").write_text(
            json.dumps(normalize(report), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.output / "exchange_report.md").write_text(exchange_markdown_report(report), encoding="utf-8")
        _print_json({
            "ledger_id": report.ledger_id,
            "status": report.status,
            "passed_cells": report.passed_cells,
            "total_cells": report.total_cells,
            "output": str(args.output),
        })
        return EXIT_OK if report.status == "PASS" else EXIT_AUDIT_FAILURE

    if args.command == "compare-representations":
        result = Runtime().execute(ledger, deterministic=True)
        comparison = compare_representations(ledger, result)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "representation_comparison.json").write_text(
            json.dumps(normalize(comparison), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.output / "representation_report.md").write_text(
            representation_markdown_report(ledger.ledger_id, comparison), encoding="utf-8"
        )
        _print_json({
            "ledger_id": ledger.ledger_id,
            "equivalent": comparison["equivalent"],
            "factor_graph_edges": comparison["factor_graph_edges"],
            "output": str(args.output),
        })
        return EXIT_OK if comparison["equivalent"] else EXIT_AUDIT_FAILURE

    if args.command == "simulate-fdcs":
        result = Runtime().execute(ledger, deterministic=args.deterministic)
        args.output.mkdir(parents=True, exist_ok=True)
        write_run(args.output, result, markdown_report(result), deterministic=args.deterministic)
        (args.output / "fdcs_analysis.json").write_text(
            json.dumps(normalize(result.fdcs_projection), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.output / "fdcs_report.md").write_text(fdcs_markdown_report(result), encoding="utf-8")
        _print_json({
            "ledger_id": result.ledger_id,
            "global_status": result.global_audit.get("status", "UNKNOWN"),
            "fdcs_status": result.fdcs_projection.get("status", "DISABLED"),
            "contexts": result.fdcs_projection.get("branch_order", []),
            "all_contexts_executed": result.fdcs_projection.get("all_contexts_executed", True),
            "output": str(args.output),
        })
        failed = result.global_audit.get("status") != "PASS"
        return EXIT_AUDIT_FAILURE if args.fail_on_audit and failed else EXIT_OK

    if args.command == "compare-directions":
        comparison = compare_directions(ledger, args.directions)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "direction_comparison.json").write_text(
            json.dumps(normalize(comparison), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.output / "direction_report.md").write_text(direction_markdown_report(comparison), encoding="utf-8")
        _print_json({
            "ledger_id": comparison.ledger_id,
            "direction_sensitive": comparison.direction_sensitive,
            "semantic_equivalence_classes": comparison.semantic_equivalence_classes,
            "output": str(args.output),
        })
        return EXIT_OK

    result = Runtime().execute(
        ledger,
        deterministic=args.deterministic,
        execution_traversal=args.execution_traversal,
    )
    write_run(args.output, result, markdown_report(result), deterministic=args.deterministic)
    _print_json({
        "ledger_id": result.ledger_id,
        "execution_traversal": result.execution_traversal,
        "global_status": result.global_audit["status"],
        "local_failures": result.local_failures,
        "tainted_transactions": result.tainted_transactions,
        "root_causes": result.root_cause_analysis["root_causes"],
        "constraint_failures": result.global_audit.get("constraint_failures", []),
        "repair_status": result.repair_analysis.status,
        "temporal_edges": len(result.temporal_analysis.get("delayed_edges", [])),
        "fixed_point_all_converged": result.fixed_point_analysis.get("all_converged", True),
        "correction_entries": result.correction_analysis.get("entry_count", 0),
        "fdcs_status": result.fdcs_projection.get("status", "DISABLED"),
        "semantic_hash": result.semantic_hash,
        "execution_hash": result.execution_hash,
        "output": str(args.output),
    })
    failed = result.global_audit.get("status") != "PASS"
    return EXIT_AUDIT_FAILURE if args.fail_on_audit and failed else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run_command(args)
    except (MMLCError, ValueError, KeyError) as exc:
        _print_json({
            "status": "ERROR",
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }, stream=sys.stderr)
        return EXIT_USAGE_OR_VALIDATION
    except Exception as exc:  # Keep unexpected failures machine-readable.
        _print_json({
            "status": "ERROR",
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }, stream=sys.stderr)
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
