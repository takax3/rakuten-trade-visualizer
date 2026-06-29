from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.fixture
def test_db(monkeypatch, request) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name)
    db_path = Path(".pytest-db") / f"{safe_name}.db"
    if db_path.exists():
        db_path.unlink()
    monkeypatch.setenv("TRADE_VISUALIZER_DB_PATH", str(db_path))
    return db_path
