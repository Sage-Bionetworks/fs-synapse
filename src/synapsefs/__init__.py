"""Top-level fs-synapse module."""

from importlib.metadata import PackageNotFoundError, version  # pragma: no cover

try:
    dist_name = __name__
    __version__ = version(dist_name)
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"
finally:
    del version, PackageNotFoundError

import logging

from synapsefs.open_parent_fs import open_parent_fs
from synapsefs.synapsefs import SynapseFS

# Set default logging handler to avoid "No handler found" warnings
logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.captureWarnings(True)

__all__ = ["SynapseFS", "open_parent_fs"]
