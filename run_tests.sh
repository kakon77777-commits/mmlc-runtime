#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q
python experiments/e0_arithmetic/run_e0.py
python experiments/e0_arithmetic/run_randomized_e0.py
python experiments/e1_symbolic_exchange/run_e1.py
python experiments/e2_root_cause/run_e2.py
python experiments/e3_matrix_directions/run_e3.py
python experiments/e4_cross_axis_constraints/run_e4.py
python experiments/e5_temporal_dynamics/run_e5.py
python experiments/e6_fdcs_interventions/run_e6.py
python experiments/e7_soft_cyclic_identifiability/run_e7.py
python experiments/e8_probability_policy_observation/run_e8.py
python experiments/e9_continuous_information_decision/run_e9.py
