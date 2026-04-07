"""conftest.py for fs-synapse."""

from __future__ import annotations

import os
from collections.abc import Generator
from uuid import uuid4

import pytest
from synapseclient.client import Synapse
from synapseclient.models import Folder
from synapseclient.operations import delete as syn_delete
from synapseclient.operations import store as syn_store

from synapsefs import SynapseFS

TEST_ROOT_PARENT = "syn50555278"


@pytest.fixture(scope="session")
def rootless_fs() -> Generator[SynapseFS, None, None]:
    """Return a rootless SynapseFS (no root, no explicit auth token)."""
    yield SynapseFS()


@pytest.fixture()
def fs(auth_token: str, test_folder: Folder) -> SynapseFS:
    """Return a SynapseFS rooted at the per-test folder."""
    return SynapseFS(test_folder.id, auth_token)


@pytest.fixture(scope="session")
def auth_token() -> str | None:
    """Return the Synapse auth token or skip."""
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if token is None:
        pytest.skip("'SYNAPSE_AUTH_TOKEN' not set in environment.")
    return token


@pytest.fixture(scope="session")
def synapse_client(auth_token: str) -> Synapse:
    """Return an authenticated Synapse client for the test session."""
    client = Synapse()
    client.login(authToken=auth_token)
    return client


@pytest.fixture(scope="session")
def integration_test_root(
    synapse_client: Synapse,
    request: pytest.FixtureRequest,
) -> Folder:
    """Create a session-level root folder under the test project and clean it up."""
    root = Folder(name=str(uuid4()), parent_id=TEST_ROOT_PARENT)
    root = syn_store(root, synapse_client=synapse_client)
    request.addfinalizer(lambda: syn_delete(root, synapse_client=synapse_client))
    return root


@pytest.fixture()
def test_folder(
    synapse_client: Synapse,
    integration_test_root: Folder,
    request: pytest.FixtureRequest,
) -> Folder:
    """Create a per-test subfolder and clean it up after the test."""
    folder = Folder(name=str(uuid4()), parent_id=integration_test_root.id)
    folder = syn_store(folder, synapse_client=synapse_client)
    request.addfinalizer(lambda: syn_delete(folder, synapse_client=synapse_client))
    return folder
