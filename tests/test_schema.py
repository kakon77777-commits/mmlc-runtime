from pathlib import Path

import pytest

from mmlc.errors import SchemaValidationError
from mmlc.parser import load_ledger


def test_missing_branches_fails(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("format: MMLF\nversion: '0.1'\nledger_id: bad\n", encoding="utf-8")
    with pytest.raises(SchemaValidationError):
        load_ledger(path)
