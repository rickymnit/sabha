"""Shared fixtures for sabha_core tests.

Integration fixtures start throwaway containers with testcontainers (CLAUDE.md: integration tests never touch the
developer's own services). Tests that use them must be marked `@pytest.mark.integration`; `make test-fast`
deselects them.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import MongoClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

MONGO_IMAGE = "mongo:7.0.43"  # keep in step with infra/docker-compose.dev.yml
REPLICA_SET = "rs0"


@pytest.fixture(scope="session")
def mongo_replica_set() -> Iterator[MongoClient[dict[str, Any]]]:
    """A single-node MongoDB 7 replica set in a container, shared by the whole test session."""
    container = (
        DockerContainer(MONGO_IMAGE)
        .with_command(f"--replSet {REPLICA_SET} --bind_ip_all --wiredTigerCacheSizeGB 0.25")
        .with_exposed_ports(27017)
        .waiting_for(LogMessageWaitStrategy("Waiting for connections"))
    )
    with container:
        initiate = f"rs.initiate({{_id: '{REPLICA_SET}', members: [{{_id: 0, host: 'localhost:27017'}}]}})"
        code, output = container.exec(["mongosh", "--quiet", "--eval", initiate])
        assert code == 0, output
        host, port = container.get_container_host_ip(), container.get_exposed_port(27017)
        # directConnection: the member advertises localhost:27017 inside the container, not the mapped port.
        client: MongoClient[dict[str, Any]] = MongoClient(
            f"mongodb://{host}:{port}/?directConnection=true", serverSelectionTimeoutMS=30_000
        )
        try:
            _wait_for_primary(client)
            yield client
        finally:
            client.close()


def _wait_for_primary(client: MongoClient[dict[str, Any]]) -> None:
    for _ in range(60):
        if client.admin.command("hello").get("isWritablePrimary"):
            return
        time.sleep(0.5)  # the single-node election takes a moment after rs.initiate
    raise RuntimeError("replica set never elected a primary")
