@echo off
setlocal
python -m pytest -q || exit /b 1
python experiments\release_v1\run_release_v1.py || exit /b 1
python scripts\verify_release.py || exit /b 1
endlocal
