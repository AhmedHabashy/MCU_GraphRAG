"""Unit tests for src/graph/neo4j_db.py (no database needed)."""

import pytest

from src.graph.neo4j_db import connect


def test_missing_settings_are_named_without_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("NEO4J_URI=bolt://localhost:7687\nNEO4J_PASSWORD=secret-value\n", encoding="utf-8")
    with pytest.raises(RuntimeError) as error:
        connect(env)
    assert "NEO4J_USER" in str(error.value) and "secret-value" not in str(error.value)
