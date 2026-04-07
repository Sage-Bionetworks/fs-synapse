"""Unit tests for RemoteFile.

These tests do not require network access or a Synapse auth token.
"""

from tempfile import TemporaryFile
from unittest.mock import MagicMock

import pytest

from synapsefs.remote_file import RemoteFile


class TestClose:
    """Tests for close() and the on_close callback."""

    def test_fires_callback_on_close(self) -> None:
        """close() invokes on_close exactly once with the RemoteFile as the argument."""
        callback = MagicMock()
        with TemporaryFile() as f:
            rf = RemoteFile(f, "w", on_close=callback)
            rf.close()
            callback.assert_called_once_with(rf)

    def test_no_callback(self) -> None:
        """close() with on_close=None is a safe no-op."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "w", on_close=None)
            rf.close()

    def test_idempotent(self) -> None:
        """A second close() is a no-op once the underlying file is closed.

        The callback closes the underlying file (mimicking a real Synapse
        upload callback), so self.closed becomes True and the guard in
        close() prevents the callback from firing again.
        """

        def closing_callback(rf: RemoteFile) -> None:
            rf.raw.close()

        callback = MagicMock(side_effect=closing_callback)
        f = TemporaryFile()
        rf = RemoteFile(f, "w", on_close=callback)
        rf.close()
        rf.close()
        callback.assert_called_once()


class TestContextManager:
    """Tests for __enter__ / __exit__."""

    def test_returns_self(self) -> None:
        """__enter__ returns the RemoteFile instance."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "w")
            assert rf.__enter__() is rf

    def test_exit_calls_close(self) -> None:
        """Exiting the context manager fires the on_close callback."""
        callback = MagicMock()
        with TemporaryFile() as f:
            with RemoteFile(f, "w", on_close=callback) as rf:
                pass
            callback.assert_called_once_with(rf)


class TestProperties:
    """Tests for raw, closed, and mode properties."""

    def test_raw(self) -> None:
        """The raw property exposes the underlying file object."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "r")
            assert rf.raw is f

    def test_closed(self) -> None:
        """The closed property reflects the underlying file's state."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "r")
            assert not rf.closed
        # TemporaryFile closes f after exiting the with block
        assert rf.closed

    def test_mode_returns_requested_mode(self) -> None:
        """The mode property returns the requested mode, not the underlying file's."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "r")
            assert rf.mode == "r"

    def test_fileno(self) -> None:
        """fileno() delegates to the underlying file."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "r")
            assert rf.fileno() == f.fileno()

    def test_seekable(self) -> None:
        """RemoteFile is always seekable."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "r")
            assert rf.seekable() is True


class TestReadable:
    """Tests for readable() across modes."""

    @pytest.mark.parametrize("mode", ["r", "rb", "r+", "r+b"])
    def test_readable_modes(self, mode: str) -> None:
        """Modes containing 'r' or '+' are readable."""
        with TemporaryFile() as f:
            assert RemoteFile(f, mode).readable() is True

    @pytest.mark.parametrize("mode", ["w", "wb", "a", "ab", "x", "xb"])
    def test_not_readable_modes(self, mode: str) -> None:
        """Write-only, append-only, and exclusive-create modes are not readable."""
        with TemporaryFile() as f:
            assert RemoteFile(f, mode).readable() is False


class TestWritable:
    """Tests for writable() across modes."""

    @pytest.mark.parametrize("mode", ["w", "wb", "a", "ab", "x", "xb", "r+", "r+b"])
    def test_writable_modes(self, mode: str) -> None:
        """Modes containing 'w', 'a', 'x', or '+' are writable."""
        with TemporaryFile() as f:
            assert RemoteFile(f, mode).writable() is True

    @pytest.mark.parametrize("mode", ["r", "rb"])
    def test_not_writable_modes(self, mode: str) -> None:
        """Read-only modes are not writable."""
        with TemporaryFile() as f:
            assert RemoteFile(f, mode).writable() is False


class TestRead:
    """Tests for read(), readline(), and readlines()."""

    def test_read(self) -> None:
        """read() returns all remaining bytes by default."""
        with TemporaryFile() as f:
            f.write(b"hello")
            f.seek(0)
            rf = RemoteFile(f, "r")
            assert rf.read() == b"hello"

    def test_read_n_bytes(self) -> None:
        """read(n) returns at most n bytes."""
        with TemporaryFile() as f:
            f.write(b"hello")
            f.seek(0)
            rf = RemoteFile(f, "r")
            assert rf.read(3) == b"hel"

    def test_read_raises_when_not_readable(self) -> None:
        """read() raises IOError on a write-only file."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "w")
            with pytest.raises(IOError, match="not open for reading"):
                rf.read()

    def test_readline(self) -> None:
        """readline() reads one line at a time."""
        with TemporaryFile() as f:
            f.write(b"line1\nline2\n")
            f.seek(0)
            rf = RemoteFile(f, "r")
            assert rf.readline() == b"line1\n"
            assert rf.readline() == b"line2\n"

    def test_readline_with_limit(self) -> None:
        """readline(limit) reads at most limit bytes."""
        with TemporaryFile() as f:
            f.write(b"hello world\n")
            f.seek(0)
            rf = RemoteFile(f, "r")
            assert rf.readline(5) == b"hello"

    def test_readlines(self) -> None:
        """readlines() returns all lines as a list."""
        with TemporaryFile() as f:
            f.write(b"a\nb\nc\n")
            f.seek(0)
            rf = RemoteFile(f, "r")
            assert rf.readlines() == [b"a\n", b"b\n", b"c\n"]


class TestWrite:
    """Tests for write() and writelines()."""

    def test_write(self) -> None:
        """write() writes bytes and returns the number of bytes written."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "w")
            n = rf.write(b"hello")
            assert n == 5
            f.seek(0)
            assert f.read() == b"hello"

    def test_write_raises_when_not_writable(self) -> None:
        """write() raises IOError on a read-only file."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "r")
            with pytest.raises(IOError, match="not open for writing"):
                rf.write(b"data")

    def test_writelines(self) -> None:
        """writelines() writes an iterable of byte strings."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "w")
            rf.writelines([b"a\n", b"b\n"])
            f.seek(0)
            assert f.read() == b"a\nb\n"


class TestSeekAndTell:
    """Tests for seek(), tell(), and flush()."""

    def test_seek_and_tell(self) -> None:
        """seek() moves the position and tell() reports it."""
        with TemporaryFile() as f:
            f.write(b"abcdef")
            rf = RemoteFile(f, "r")
            pos = rf.seek(3)
            assert pos == 3
            assert rf.tell() == 3

    def test_seek_from_end(self) -> None:
        """seek() with SEEK_END offsets from the end of the file."""
        with TemporaryFile() as f:
            f.write(b"abcdef")
            rf = RemoteFile(f, "r")
            pos = rf.seek(-2, 2)  # SEEK_END
            assert pos == 4

    def test_seek_from_current(self) -> None:
        """seek() with SEEK_CUR offsets from the current position."""
        with TemporaryFile() as f:
            f.write(b"abcdef")
            rf = RemoteFile(f, "r")
            rf.seek(2)
            pos = rf.seek(1, 1)  # SEEK_CUR
            assert pos == 3

    def test_flush(self) -> None:
        """flush() delegates to the underlying file without error."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "w")
            rf.write(b"data")
            rf.flush()


class TestTruncate:
    """Tests for truncate()."""

    def test_truncate_with_size(self) -> None:
        """truncate(size) truncates to the given number of bytes."""
        with TemporaryFile() as f:
            f.write(b"hello world")
            rf = RemoteFile(f, "w")
            result = rf.truncate(5)
            assert result == 5
            f.seek(0)
            assert f.read() == b"hello"

    def test_truncate_at_current_position(self) -> None:
        """truncate() without an argument truncates at the current position."""
        with TemporaryFile() as f:
            f.write(b"hello world")
            rf = RemoteFile(f, "w")
            rf.seek(5)
            result = rf.truncate()
            assert result == 5
            f.seek(0)
            assert f.read() == b"hello"

    def test_truncate_raises_when_not_writable(self) -> None:
        """truncate() raises IOError on a read-only file."""
        with TemporaryFile() as f:
            rf = RemoteFile(f, "r")
            with pytest.raises(IOError, match="not open for writing"):
                rf.truncate()
