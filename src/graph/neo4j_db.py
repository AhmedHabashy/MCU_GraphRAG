"""Connection to the project's Neo4j database (started with `docker compose up -d`).

Needs NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD in .env (see .env.example).
"""

from dotenv import dotenv_values
from neo4j import GraphDatabase

from src.source_data_collection.tier_titles import PROJECT_ROOT

ENV_PATH = PROJECT_ROOT / ".env"
SETTINGS = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")


def connect(env_path=ENV_PATH):
    """A Neo4j driver for the configured database; the caller closes it."""
    values = dotenv_values(env_path)
    missing = [name for name in SETTINGS if not values.get(name)]
    if missing:
        raise RuntimeError(f"Missing from .env: {', '.join(missing)} (see .env.example)")
    return GraphDatabase.driver(values["NEO4J_URI"], auth=(values["NEO4J_USER"], values["NEO4J_PASSWORD"]))
