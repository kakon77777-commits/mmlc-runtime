from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any


@dataclass(frozen=True)
class SourceObject:
    object_id: str
    type_name: str
    value: Any
    metadata: dict[str, Any] = dc_field(default_factory=dict)


@dataclass(frozen=True)
class ValueRef:
    tx_id: str
    field: str = "result"


@dataclass(frozen=True)
class TemporalRef:
    """Reference another transaction by series identity and time lag."""

    series_id: str
    lag: int = 1
    field: str = "result"
    default: Any = None
    has_default: bool = False


@dataclass(frozen=True)
class MatrixRef:
    """A coordinate/traversal-relative reference resolved by Runtime v0.4.

    Relations ``left/right/up/down`` are spatial. ``previous/next`` are relative
    to the active physical execution traversal. ``default`` is used when the
    requested neighbour does not exist. If ``has_default`` is false, the missing
    neighbour is an explicit error.
    """

    relation: str
    field: str = "result"
    default: Any = None
    has_default: bool = False


@dataclass(frozen=True, order=True)
class Coordinate:
    row: int
    column: int


@dataclass
class Transaction:
    tx_id: str
    source_id: str | None
    base: Any
    operator: str
    operand: Any = None
    declared_result: Any = None
    context: dict[str, Any] = dc_field(default_factory=dict)
    dependencies: list[str] = dc_field(default_factory=list)
    region: str = "default"
    time_index: int = 0
    series_id: str | None = None


@dataclass(frozen=True)
class EvaluationScenario:
    scenario_id: str
    bindings: dict[str, Any]
    metadata: dict[str, Any] = dc_field(default_factory=dict)




@dataclass(frozen=True)
class MatrixConstraint:
    constraint_id: str
    kind: str
    axis: str
    members: tuple[str, ...]
    field: str = "result"
    target: Any = 0
    tolerance: float | None = None
    metadata: dict[str, Any] = dc_field(default_factory=dict)


@dataclass(frozen=True)
class ConstraintResult:
    constraint_id: str
    kind: str
    axis: str
    field: str
    members: tuple[str, ...]
    status: str
    observed: Any = None
    target: Any = None
    residual: Any = None
    detail: str = ""


@dataclass(frozen=True)
class RepairProposal:
    cells: tuple[str, ...]
    field: str
    deltas: dict[str, Any]
    corrected_values: dict[str, Any]
    preserves_constraints: tuple[str, ...]


@dataclass
class RepairReport:
    status: str
    method: str
    minimal_size: int | None
    proposals: list[RepairProposal]
    ambiguous: bool
    searched_supports: int
    exact: bool
    detail: str = ""




@dataclass(frozen=True)
class FixedPointGroup:
    group_id: str
    members: tuple[str, ...]
    method: str = "jacobi"
    tolerance: float = 1.0e-10
    max_iterations: int = 200
    initial_values: dict[str, Any] = dc_field(default_factory=dict)


@dataclass(frozen=True)
class CorrectionEntry:
    correction_id: str
    target_tx_id: str
    field: str
    mode: str
    value: Any
    reason: str = ""
    metadata: dict[str, Any] = dc_field(default_factory=dict)


@dataclass(frozen=True)
class CorrectionAuditEntry:
    correction_id: str
    target_tx_id: str
    field: str
    mode: str
    before: Any
    after: Any
    previous_hash: str
    entry_hash: str

@dataclass(frozen=True)
class AuditPolicy:
    local_required: bool = True
    signed_global_cancellation_allowed: bool = False
    numeric_tolerance: float = 1.0e-12
    required_checks: tuple[str, ...] = (
        "type",
        "domain",
        "value",
        "source",
        "dependency",
    )


@dataclass
class MatrixLedger:
    ledger_id: str
    version: str
    sources: dict[str, SourceObject]
    transactions: dict[str, Transaction]
    display_order: list[str]
    traversals: dict[str, Any]
    audit_policy: AuditPolicy
    layout: list[list[str | None]] = dc_field(default_factory=list)
    coordinates: dict[str, Coordinate] = dc_field(default_factory=dict)
    boundary_events: list[dict[str, Any]] = dc_field(default_factory=list)
    evaluation_scenarios: list[EvaluationScenario] = dc_field(default_factory=list)
    constraints: list[MatrixConstraint] = dc_field(default_factory=list)
    fixed_point_groups: list[FixedPointGroup] = dc_field(default_factory=list)
    corrections: list[CorrectionEntry] = dc_field(default_factory=list)
    fdcs: dict[str, Any] = dc_field(default_factory=dict)
    metadata: dict[str, Any] = dc_field(default_factory=dict)

    def __post_init__(self) -> None:
        # Backwards compatibility for programmatically constructed v0.1/v0.2
        # ledgers: their display order becomes a single-row matrix.
        if not self.layout:
            self.layout = [list(self.display_order)]
        if not self.coordinates:
            self.coordinates = {
                tx_id: Coordinate(r, c)
                for r, row in enumerate(self.layout)
                for c, tx_id in enumerate(row)
                if tx_id is not None
            }


@dataclass(frozen=True)
class CheckResult:
    status: str
    detail: str = ""
    residual: Any = None
    scaled_residual: float | None = None


@dataclass
class TransactionResult:
    tx_id: str
    operator: str
    operator_version: str
    computed_result: Any = None
    audited_result: Any = None
    status: str = "ERROR"
    local_status: str = "ERROR"
    checks: dict[str, CheckResult] = dc_field(default_factory=dict)
    dependencies: list[str] = dc_field(default_factory=list)
    unhealthy_dependencies: list[str] = dc_field(default_factory=list)
    dependency_channels: dict[str, list[str]] = dc_field(default_factory=dict)
    root_causes: list[str] = dc_field(default_factory=list)
    coordinate: Coordinate | None = None
    time_index: int = 0
    series_id: str | None = None
    original_declared_result: Any = None
    effective_declared_result: Any = None
    corrections_applied: list[str] = dc_field(default_factory=list)
    fixed_point_group: str | None = None
    fixed_point_iterations: int | None = None
    structural_result: Any = None
    intervened: bool = False
    intervention_ids: list[str] = dc_field(default_factory=list)
    intervention_kinds: list[str] = dc_field(default_factory=list)
    fdcs_context: str = "baseline"
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class RunResult:
    ledger_id: str
    runtime_version: str
    execution_order: list[str]
    execution_traversal: str
    transactions: dict[str, TransactionResult]
    local_failures: list[str]
    tainted_transactions: list[str]
    region_audits: dict[str, dict[str, Any]]
    global_audit: dict[str, Any]
    traversals: list[dict[str, Any]]
    root_cause_analysis: dict[str, Any]
    constraint_audits: dict[str, ConstraintResult]
    cross_axis_conflicts: list[dict[str, Any]]
    repair_analysis: RepairReport
    temporal_analysis: dict[str, Any]
    fixed_point_analysis: dict[str, Any]
    correction_analysis: dict[str, Any]
    fdcs_projection: dict[str, Any]
    semantic_hash: str
    execution_hash: str
    manifest: dict[str, Any]


@dataclass(frozen=True)
class ExchangeCellResult:
    tx_id: str
    symbolic_value: Any
    substituted_symbolic_value: Any
    direct_numeric_value: Any
    equivalent: bool
    detail: str = ""


@dataclass
class ExchangeScenarioResult:
    scenario_id: str
    bindings: dict[str, Any]
    status: str
    cells: dict[str, ExchangeCellResult]
    symbolic_hash: str
    numeric_hash: str


@dataclass
class ExchangeReport:
    ledger_id: str
    runtime_version: str
    status: str
    scenario_results: list[ExchangeScenarioResult]
    total_cells: int
    passed_cells: int
    failed_cells: int


@dataclass
class DirectionComparison:
    ledger_id: str
    directions: list[str]
    runs: dict[str, RunResult]
    semantic_equivalence_classes: list[list[str]]
    result_equivalence_classes: list[list[str]]
    direction_sensitive: bool
