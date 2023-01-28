"""conftest.py for fs-synapse."""

from datetime import datetime
from getpass import getuser
from uuid import uuid4

import pytest

from synapsefs import SynapseFS

UUID = str(uuid4())
USER = getuser()
UTCTIME = datetime.now().isoformat(" ", "seconds").replace(":", ".")
RUNID = f"{USER} - {UTCTIME} - {UUID}"  # Valid characters: [A-Za-z0-9 .+'()_-]


def pytest_configure():
    pytest.RUNID = RUNID  # type: ignore


@pytest.fixture(scope="session")
def synapse_fs():
    yield SynapseFS()
