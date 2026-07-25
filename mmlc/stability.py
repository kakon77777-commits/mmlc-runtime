"""Public compatibility declarations for MMLC Runtime 1.x."""

from __future__ import annotations

RUNTIME_API_VERSION = "1"
MMLF_STABLE_VERSION = "1.0"
SUPPORTED_MMLF_VERSIONS = (
    "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1.0",
)
STABLE_CLI_COMMANDS = (
    "validate",
    "run",
    "verify-exchange",
    "compare-representations",
    "simulate-fdcs",
    "compare-directions",
    "migrate",
    "benchmark",
    "info",
)
STABLE_PUBLIC_SYMBOLS = (
    "Runtime",
    "load_ledger",
    "validate_file",
    "execute_file",
    "simulate_fdcs_file",
    "migrate_file",
    "runtime_info",
    "verify_symbolic_numeric_exchange",
    "compare_directions",
    "compare_representations",
)


def compatibility_manifest() -> dict[str, object]:
    return {
        "runtime_api_version": RUNTIME_API_VERSION,
        "mmlf_stable_version": MMLF_STABLE_VERSION,
        "supported_mmlf_versions": list(SUPPORTED_MMLF_VERSIONS),
        "stable_cli_commands": list(STABLE_CLI_COMMANDS),
        "stable_public_symbols": list(STABLE_PUBLIC_SYMBOLS),
        "semantic_versioning": {
            "patch": "bug fixes with no intended public API or MMLF semantic change",
            "minor": "backward-compatible additions inside Runtime 1.x",
            "major": "public API removal or MMLF semantic incompatibility",
        },
    }
