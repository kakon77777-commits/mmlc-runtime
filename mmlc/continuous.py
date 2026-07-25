from __future__ import annotations

import math
from copy import deepcopy
from statistics import NormalDist
from typing import Any, Iterable

from .semantics import supports_profile

from .errors import FDCSConfigurationError
from .persistence import semantic_hash

_NORMAL = NormalDist()
_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53)


def _finite(value: Any, *, name: str) -> float:
    try:
        number = float(value)
    except Exception as exc:
        raise FDCSConfigurationError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise FDCSConfigurationError(f"{name} must be finite")
    return number


def _halton(index: int, base: int) -> float:
    result = 0.0
    factor = 1.0 / base
    value = index
    while value > 0:
        result += factor * (value % base)
        value //= base
        factor /= base
    return result


def _clip_probability(value: float) -> float:
    return min(1.0 - 1.0e-12, max(1.0e-12, value))


def _cholesky(matrix: list[list[float]], tolerance: float = 1.0e-12) -> list[list[float]]:
    n = len(matrix)
    if n == 0 or any(len(row) != n for row in matrix):
        raise FDCSConfigurationError("correlation_matrix must be a non-empty square matrix")
    for i in range(n):
        if abs(matrix[i][i] - 1.0) > tolerance:
            raise FDCSConfigurationError("correlation_matrix diagonal entries must equal 1")
        for j in range(n):
            if abs(matrix[i][j] - matrix[j][i]) > tolerance:
                raise FDCSConfigurationError("correlation_matrix must be symmetric")
            if matrix[i][j] < -1.0 - tolerance or matrix[i][j] > 1.0 + tolerance:
                raise FDCSConfigurationError("correlation coefficients must lie in [-1, 1]")
    lower = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            subtotal = sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                diagonal = matrix[i][i] - subtotal
                if diagonal <= tolerance:
                    raise FDCSConfigurationError(
                        "correlation_matrix must be positive definite for deterministic Gaussian-copula sampling"
                    )
                lower[i][j] = math.sqrt(diagonal)
            else:
                lower[i][j] = (matrix[i][j] - subtotal) / lower[j][j]
    return lower


def _inverse_marginal(variable: dict[str, Any], probability: float, normal_score: float) -> float:
    kind = str(variable.get("distribution", "normal"))
    if kind == "normal":
        mean = _finite(variable.get("mean", 0.0), name=f"variable {variable['id']} mean")
        stddev = _finite(variable.get("stddev", 1.0), name=f"variable {variable['id']} stddev")
        if stddev <= 0:
            raise FDCSConfigurationError(f"variable {variable['id']} stddev must be > 0")
        return mean + stddev * normal_score
    if kind == "lognormal":
        mu = _finite(variable.get("mu", variable.get("mean_log", 0.0)), name=f"variable {variable['id']} mu")
        sigma = _finite(variable.get("sigma", variable.get("stddev_log", 1.0)), name=f"variable {variable['id']} sigma")
        if sigma <= 0:
            raise FDCSConfigurationError(f"variable {variable['id']} sigma must be > 0")
        return math.exp(mu + sigma * normal_score)
    if kind == "uniform":
        lower = _finite(variable.get("lower", 0.0), name=f"variable {variable['id']} lower")
        upper = _finite(variable.get("upper", 1.0), name=f"variable {variable['id']} upper")
        if upper <= lower:
            raise FDCSConfigurationError(f"variable {variable['id']} upper must exceed lower")
        return lower + probability * (upper - lower)
    if kind == "triangular":
        lower = _finite(variable.get("lower", 0.0), name=f"variable {variable['id']} lower")
        upper = _finite(variable.get("upper", 1.0), name=f"variable {variable['id']} upper")
        mode = _finite(variable.get("mode", (lower + upper) / 2.0), name=f"variable {variable['id']} mode")
        if not lower <= mode <= upper or upper <= lower:
            raise FDCSConfigurationError(f"variable {variable['id']} requires lower <= mode <= upper and lower < upper")
        split = (mode - lower) / (upper - lower)
        if probability < split:
            return lower + math.sqrt(probability * (upper - lower) * (mode - lower))
        return upper - math.sqrt((1.0 - probability) * (upper - lower) * (upper - mode))
    raise FDCSConfigurationError(f"Unsupported continuous distribution: {kind}")


def _validate_variables(variables: list[dict[str, Any]]) -> None:
    if not variables:
        raise FDCSConfigurationError("continuous ensemble requires at least one variable")
    if len(variables) > len(_PRIMES):
        raise FDCSConfigurationError(f"continuous ensemble supports at most {len(_PRIMES)} variables")
    ids: set[str] = set()
    targets: set[str] = set()
    for variable in variables:
        variable_id = str(variable.get("id", "")).strip()
        target = str(variable.get("target_tx_id", "")).strip()
        if not variable_id or not target:
            raise FDCSConfigurationError("continuous variable requires id and target_tx_id")
        if variable_id in ids:
            raise FDCSConfigurationError(f"Duplicate continuous variable id: {variable_id}")
        if target in targets:
            raise FDCSConfigurationError(
                f"Continuous variables must target distinct transactions; duplicate target: {target}"
            )
        ids.add(variable_id)
        targets.add(target)
        kind = str(variable.get("intervention_kind", "do_set"))
        if kind not in {"do_set", "soft_shift", "soft_scale"}:
            raise FDCSConfigurationError(
                f"Continuous variable {variable_id} intervention_kind must be do_set, soft_shift or soft_scale"
            )
        # Force distribution parameter validation once using a central quantile.
        _inverse_marginal(variable, 0.5, 0.0)


def generate_continuous_ensemble_specs(
    *,
    ledger_version: str,
    continuous_config: dict[str, Any] | None,
    transaction_ids: Iterable[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = deepcopy(dict(continuous_config or {}))
    if not bool(config.get("enabled", False)):
        return [], {"enabled": False, "status": "DISABLED", "ensembles": {}}
    if not supports_profile(str(ledger_version), "0.9"):
        raise FDCSConfigurationError("continuous_uncertainty requires MMLF v0.9 or later")
    raw_ensembles = config.get("ensembles", [])
    if not isinstance(raw_ensembles, list) or not raw_ensembles:
        raise FDCSConfigurationError("continuous_uncertainty.ensembles must be a non-empty array")
    tx_ids = set(transaction_ids)
    generated: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    ensemble_ids: set[str] = set()
    context_ids: set[str] = set()

    for raw in raw_ensembles:
        if not isinstance(raw, dict):
            raise FDCSConfigurationError("Each continuous ensemble must be an object")
        ensemble_id = str(raw.get("id", "")).strip()
        if not ensemble_id or ensemble_id in ensemble_ids:
            raise FDCSConfigurationError(f"Invalid or duplicate continuous ensemble id: {ensemble_id}")
        ensemble_ids.add(ensemble_id)
        variables = [deepcopy(dict(item)) for item in raw.get("variables", [])]
        _validate_variables(variables)
        for variable in variables:
            if str(variable["target_tx_id"]) not in tx_ids:
                raise FDCSConfigurationError(
                    f"Continuous variable {variable['id']} targets missing transaction: {variable['target_tx_id']}"
                )
        sample_count = int(raw.get("samples", config.get("samples", 128)))
        if sample_count < 4 or sample_count > int(config.get("max_samples", 4096)):
            raise FDCSConfigurationError("continuous ensemble samples must be between 4 and max_samples")
        dimension = len(variables)
        raw_corr = raw.get("correlation_matrix")
        if raw_corr is None:
            correlation = [[1.0 if i == j else 0.0 for j in range(dimension)] for i in range(dimension)]
        else:
            correlation = [[_finite(value, name="correlation coefficient") for value in row] for row in raw_corr]
        if len(correlation) != dimension:
            raise FDCSConfigurationError("correlation_matrix dimension must match variable count")
        lower = _cholesky(correlation)
        policy_id = str(raw.get("policy_id") or ensemble_id)
        scenario_prefix = str(raw.get("scenario_prefix") or ensemble_id)
        cost = _finite(raw.get("cost", 0.0), name=f"continuous ensemble {ensemble_id} cost")
        if cost < 0:
            raise FDCSConfigurationError(f"continuous ensemble {ensemble_id} cost must be non-negative")
        modulation = _finite(raw.get("modulation", 1.0), name=f"continuous ensemble {ensemble_id} modulation")
        if modulation < 0:
            raise FDCSConfigurationError(f"continuous ensemble {ensemble_id} modulation must be non-negative")

        samples: list[dict[str, float]] = []
        # Antithetic Halton points reduce first-moment drift while preserving deterministic replay.
        half = (sample_count + 1) // 2
        raw_points: list[list[float]] = []
        for index in range(1, half + 1):
            point = [_clip_probability(_halton(index, _PRIMES[d])) for d in range(dimension)]
            raw_points.append(point)
            if len(raw_points) < sample_count:
                raw_points.append([1.0 - value for value in point])
        raw_points = raw_points[:sample_count]

        for sample_index, uniforms in enumerate(raw_points):
            independent_z = [_NORMAL.inv_cdf(_clip_probability(value)) for value in uniforms]
            correlated_z = [
                sum(lower[i][j] * independent_z[j] for j in range(i + 1))
                for i in range(dimension)
            ]
            values: dict[str, float] = {}
            interventions: list[dict[str, Any]] = []
            for variable, z_score in zip(variables, correlated_z):
                probability = _clip_probability(_NORMAL.cdf(z_score))
                sampled = _inverse_marginal(variable, probability, z_score)
                variable_id = str(variable["id"])
                values[variable_id] = sampled
                kind = str(variable.get("intervention_kind", "do_set"))
                item: dict[str, Any] = {
                    "id": f"continuous-{ensemble_id}-{sample_index:04d}-{variable_id}",
                    "kind": kind,
                    "target_tx_id": str(variable["target_tx_id"]),
                    "reason": f"deterministic continuous approximation sample {sample_index}",
                    "metadata": {"ensemble_id": ensemble_id, "variable_id": variable_id},
                }
                if kind == "do_set":
                    item["value"] = sampled
                elif kind == "soft_shift":
                    item["shift"] = sampled
                else:
                    item["scale"] = sampled
                interventions.append(item)
            context_id = f"{ensemble_id}-sample-{sample_index:04d}"
            if context_id in context_ids:
                raise FDCSConfigurationError(f"Duplicate generated context id: {context_id}")
            context_ids.add(context_id)
            metadata = {
                "generated_by": "continuous_uncertainty",
                "continuous_ensemble_id": ensemble_id,
                "sample_index": sample_index,
                "sample_values": values,
                "sampling_method": "antithetic_halton_gaussian_copula",
            }
            generated.append({
                "id": context_id,
                "modulation": modulation,
                "interventions": interventions,
                "probability": 1.0 / sample_count,
                "policy_id": policy_id,
                "scenario_id": f"{scenario_prefix}-{sample_index:04d}",
                "cost": cost,
                "metadata": metadata,
            })
            samples.append(values)

        summaries[ensemble_id] = {
            "ensemble_id": ensemble_id,
            "policy_id": policy_id,
            "sample_count": sample_count,
            "variable_ids": [str(variable["id"]) for variable in variables],
            "variables": variables,
            "correlation_matrix": correlation,
            "sampling_method": "antithetic_halton_gaussian_copula",
            "equal_probability": 1.0 / sample_count,
            "samples": samples,
        }

    plan = {
        "enabled": True,
        "status": "PASS",
        "sampling_method": "antithetic_halton_gaussian_copula",
        "generated_context_count": len(generated),
        "ensembles": summaries,
        "scope_note": (
            "Continuous distributions are approximated by a deterministic finite weighted ensemble. "
            "The Gaussian copula encodes the declared dependence structure; it is not estimated from external data."
        ),
    }
    plan["analysis_hash"] = semantic_hash(plan)
    return generated, plan


def _sample_moments(samples: list[dict[str, float]], variable_ids: list[str]) -> dict[str, Any]:
    count = len(samples)
    means = {variable_id: sum(sample[variable_id] for sample in samples) / count for variable_id in variable_ids}
    covariance: list[list[float]] = []
    for left in variable_ids:
        row: list[float] = []
        for right in variable_ids:
            row.append(sum(
                (sample[left] - means[left]) * (sample[right] - means[right])
                for sample in samples
            ) / count)
        covariance.append(row)
    stddevs = {variable_id: math.sqrt(max(0.0, covariance[i][i])) for i, variable_id in enumerate(variable_ids)}
    correlation: list[list[float | None]] = []
    for i, left in enumerate(variable_ids):
        row = []
        for j, right in enumerate(variable_ids):
            denominator = stddevs[left] * stddevs[right]
            row.append(covariance[i][j] / denominator if denominator > 0 else None)
        correlation.append(row)
    return {
        "sample_count": count,
        "means": means,
        "standard_deviations": stddevs,
        "covariance_matrix": covariance,
        "correlation_matrix": correlation,
    }


def build_continuous_approximation_analysis(plan: dict[str, Any] | None) -> dict[str, Any]:
    source = deepcopy(dict(plan or {}))
    if not source.get("enabled"):
        return {"enabled": False, "status": "DISABLED", "ensembles": {}}
    ensembles: dict[str, Any] = {}
    for ensemble_id, item in sorted(source.get("ensembles", {}).items()):
        variable_ids = list(item["variable_ids"])
        empirical = _sample_moments(list(item["samples"]), variable_ids)
        target_marginals: dict[str, Any] = {}
        for variable in item["variables"]:
            kind = str(variable.get("distribution", "normal"))
            variable_id = str(variable["id"])
            target: dict[str, Any] = {"distribution": kind}
            if kind == "normal":
                target.update({"mean": float(variable.get("mean", 0.0)), "standard_deviation": float(variable.get("stddev", 1.0))})
            elif kind == "uniform":
                lower = float(variable.get("lower", 0.0)); upper = float(variable.get("upper", 1.0))
                target.update({"mean": (lower + upper) / 2.0, "standard_deviation": (upper - lower) / math.sqrt(12.0)})
            elif kind == "triangular":
                lower = float(variable.get("lower", 0.0)); upper = float(variable.get("upper", 1.0)); mode = float(variable.get("mode", (lower + upper) / 2.0))
                mean = (lower + upper + mode) / 3.0
                variance = (lower * lower + upper * upper + mode * mode - lower * upper - lower * mode - upper * mode) / 18.0
                target.update({"mean": mean, "standard_deviation": math.sqrt(max(0.0, variance))})
            elif kind == "lognormal":
                mu = float(variable.get("mu", variable.get("mean_log", 0.0))); sigma = float(variable.get("sigma", variable.get("stddev_log", 1.0)))
                mean = math.exp(mu + sigma * sigma / 2.0)
                variance = (math.exp(sigma * sigma) - 1.0) * math.exp(2.0 * mu + sigma * sigma)
                target.update({"mean": mean, "standard_deviation": math.sqrt(variance)})
            target_marginals[variable_id] = target
        payload = {
            "ensemble_id": ensemble_id,
            "policy_id": item["policy_id"],
            "sampling_method": item["sampling_method"],
            "sample_count": item["sample_count"],
            "target_marginals": target_marginals,
            "declared_correlation_matrix": item["correlation_matrix"],
            "empirical": empirical,
            "approximation_only": True,
        }
        payload["analysis_hash"] = semantic_hash(payload)
        ensembles[ensemble_id] = payload
    result = {
        "enabled": True,
        "status": "PASS",
        "sampling_method": source.get("sampling_method"),
        "generated_context_count": source.get("generated_context_count", 0),
        "ensembles": ensembles,
        "scope_note": source.get("scope_note"),
    }
    result["analysis_hash"] = semantic_hash(result)
    return result
