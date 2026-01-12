from __future__ import annotations

from neo4j import GraphDatabase, Driver
from core.config import settings

_driver: Driver | None = None


def init_driver() -> None:
    """Initialize a single global Neo4j driver (connection pool owner)."""
    global _driver
    if _driver is not None:
        return

    _driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        max_connection_pool_size=settings.NEO4J_MAX_POOL_SIZE,
        connection_timeout=settings.NEO4J_CONNECTION_TIMEOUT_SEC,
    )


def get_driver() -> Driver:
    if _driver is None:
        raise RuntimeError("Neo4j driver is not initialized. Call init_driver() on startup.")
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def get_db_name() -> str:
    return settings.NEO4J_DATABASE


# from neo4j import GraphDatabase
# from core.config import settings

# _driver = None


# def init_neo4j_driver():
#     global _driver
#     if _driver is None:
#         _driver = GraphDatabase.driver(
#             settings.NEO4J_URI,
#             auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
#             max_connection_pool_size=20,
#             connection_timeout=15
#         )


# def close_neo4j_driver():
#     global _driver
#     if _driver:
#         _driver.close()
#         _driver = None


# def get_driver():
#     if _driver is None:
#         raise RuntimeError("Neo4j driver is not initialized")
#     return _driver
