"""Checks on the running Neo4j database.

Start it with:  docker compose up -d
Run with:       .venv\Scripts\python.exe -m pytest -m neo4j
"""

import re
from pathlib import Path

import pytest
from neo4j.exceptions import ServiceUnavailable

from src.graph.neo4j_db import connect

pytestmark = pytest.mark.neo4j

COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.yml"


@pytest.fixture(scope="module")
def driver():
    driver = connect()
    try:
        driver.verify_connectivity()
    except ServiceUnavailable:
        driver.close()
        pytest.skip("Neo4j is not running; start it with `docker compose up -d`")
    yield driver
    driver.close()


def test_server_runs_the_version_pinned_in_docker_compose(driver):
    pinned = re.search(r"image:\s*neo4j:(\S+)-community", COMPOSE_PATH.read_text(encoding="utf-8")).group(1)
    info = driver.execute_query("CALL dbms.components() YIELD versions, edition RETURN versions[0] AS v, edition AS e")
    record = info.records[0]
    assert (record["v"], record["e"]) == (pinned, "community")


def test_write_and_read_back_in_a_rolled_back_transaction(driver):
    """Nothing is left in the database: the transaction is rolled back."""
    with driver.session() as session:
        tx = session.begin_transaction()
        tx.run("CREATE (:SmokeTest {name: $name})-[:KNOWS]->(:SmokeTest {name: 'b'})", name="a")
        found = tx.run("MATCH (a:SmokeTest {name: 'a'})-[:KNOWS]->(b) RETURN b.name AS name").single()["name"]
        tx.rollback()
    assert found == "b"
    left = driver.execute_query("MATCH (n:SmokeTest) RETURN count(n) AS n").records[0]["n"]
    assert left == 0
