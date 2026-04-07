from __future__ import annotations

import io
import os
from collections.abc import Callable, Iterable
from typing import IO, BinaryIO


class RemoteFile(io.IOBase, BinaryIO):
    """Proxy around a local temporary file that represents a remote Synapse file.

    Delegates all I/O to the underlying file while enforcing the requested
    access mode. When closed, fires an optional callback (typically used to
    upload the file contents back to Synapse).
    """

    def __init__(
        self,
        f: IO[bytes],
        mode: str,
        on_close: Callable[[RemoteFile], None] | None = None,
    ):
        """Initialize a RemoteFile.

        Args:
            f: The underlying local file to delegate I/O operations to.
            mode: The requested access mode (e.g., "r", "w", "a", "r+").
                Controls what operations are permitted, independent of
                the underlying file's actual mode.
            on_close: Optional callback invoked once when the file is closed.
                Receives this RemoteFile instance as its argument.
        """
        self._f = f
        self.__mode = mode
        self._on_close = on_close

    def __enter__(self) -> RemoteFile:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:  # type: ignore
        self.close()

    @property
    def raw(self) -> IO[bytes]:
        """Return the underlying file object."""
        return self._f

    def close(self) -> None:
        """Close the file and fire the on_close callback if set.

        Idempotent: the callback is only invoked on the first call.
        """
        if not self.closed and self._on_close is not None:
            self._on_close(self)

    @property
    def closed(self) -> bool:
        """Whether the underlying file is closed."""
        return self._f.closed

    @property
    def mode(self) -> str:
        """The requested access mode for this file."""
        return self.__mode

    def fileno(self) -> int:
        """Return the file descriptor of the underlying file."""
        return self._f.fileno()

    def flush(self) -> None:
        """Flush the underlying file's write buffer."""
        self._f.flush()

    def readable(self) -> bool:
        """Whether this file was opened for reading."""
        return "r" in self.__mode or "+" in self.__mode

    def readline(self, limit: int | None = -1) -> bytes:
        """Read and return one line from the file."""
        limit = limit or -1
        return self._f.readline(limit)

    def readlines(self, hint: int = -1) -> list[bytes]:
        """Read and return a list of lines from the file."""
        return self._f.readlines(hint)

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        """Move the file position and return the new absolute position."""
        self._f.seek(offset, whence)
        return self._f.tell()

    def seekable(self) -> bool:
        """Whether this file supports random access."""
        return True

    def tell(self) -> int:
        """Return the current file position."""
        return self._f.tell()

    def writable(self) -> bool:
        """Whether this file was opened for writing."""
        return (
            "w" in self.__mode
            or "a" in self.__mode
            or "+" in self.__mode
            or "x" in self.__mode
        )

    def writelines(self, lines: Iterable[bytes]) -> None:  # type: ignore
        """Write a list of lines to the file."""
        return self._f.writelines(lines)

    def read(self, n: int = -1) -> bytes:
        """Read up to *n* bytes. Returns all remaining bytes if *n* is -1."""
        if not self.readable():
            raise IOError("not open for reading")
        return self._f.read(n)

    def write(self, b: bytes) -> int:
        """Write bytes to the file and return the number of bytes written."""
        if not self.writable():
            raise IOError("not open for writing")
        return self._f.write(b)

    def truncate(self, size: int | None = None) -> int:
        """Truncate the file to at most *size* bytes.

        If *size* is omitted, truncates at the current file position.
        """
        if not self.writable():
            raise IOError("not open for writing")
        if size is None:
            size = self._f.tell()
        self._f.truncate(size)
        return size
