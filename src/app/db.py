"""The Neo4j driver every store shares. What is kept in the graph, and how it is searched, lives
with each feature: app.carehomes.store for care homes, app.domain for added entities."""

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import Settings


def make_driver(settings: Settings) -> AsyncDriver:
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
