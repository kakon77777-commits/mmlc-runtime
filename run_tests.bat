@echo off
python -m pytest -q
if errorlevel 1 exit /b 1
python experiments\e0_arithmetic\run_e0.py
if errorlevel 1 exit /b 1
python experiments\e0_arithmetic\run_randomized_e0.py
if errorlevel 1 exit /b 1
python experiments\e1_symbolic_exchange\run_e1.py
if errorlevel 1 exit /b 1
python experiments\e2_root_cause\run_e2.py
if errorlevel 1 exit /b 1
python experiments\e3_matrix_directions\run_e3.py
if errorlevel 1 exit /b 1
python experiments\e4_cross_axis_constraints\run_e4.py
if errorlevel 1 exit /b 1
python experiments\e5_temporal_dynamics\run_e5.py
if errorlevel 1 exit /b 1
python experiments\e6_fdcs_interventions\run_e6.py
if errorlevel 1 exit /b 1
python experiments\e7_soft_cyclic_identifiability\run_e7.py
if errorlevel 1 exit /b 1
python experiments\e8_probability_policy_observation\run_e8.py
if errorlevel 1 exit /b 1
pause
python experiments\e9_continuous_information_decision\run_e9.py
