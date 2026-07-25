#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q
python experiments/release_v1/run_release_v1.py
python scripts/verify_release.py
