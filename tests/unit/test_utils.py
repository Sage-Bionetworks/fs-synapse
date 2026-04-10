"""Unit tests for SynapseFS utils."""

import io
from pathlib import Path

import pytest

from synapsefs.synapsefs import SynapseFS
from synapsefs.utils import (
    NULL_BYTE,
    normalize_mode,
    pad_empty_file,
    parse_mode,
    rename_to_target,
    strip_mode,
)


class TestParseMode:
    """Tests for parse_mode."""

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [
            pytest.param(
                "r",
                (True, False, False, False, False),
                id="read_only",
            ),
            pytest.param(
                "rb",
                (True, False, False, False, False),
                id="read_binary",
            ),
            pytest.param(
                "w",
                (False, True, False, True, False),
                id="write",
            ),
            pytest.param(
                "wb",
                (False, True, False, True, False),
                id="write_binary",
            ),
            pytest.param(
                "a",
                (False, True, True, True, False),
                id="append",
            ),
            pytest.param(
                "x",
                (False, True, False, True, True),
                id="exclusive_create",
            ),
            pytest.param(
                "xb",
                (False, True, False, True, True),
                id="exclusive_create_binary",
            ),
            pytest.param(
                "r+",
                (True, True, False, False, False),
                id="read_write",
            ),
            pytest.param(
                "r+b",
                (True, True, False, False, False),
                id="read_write_binary",
            ),
            pytest.param(
                "a+",
                (True, True, True, True, False),
                id="append_read",
            ),
            pytest.param(
                "wt",
                (False, True, False, True, False),
                id="write_text_stripped",
            ),
        ],
    )
    def test_parse_mode(self, mode: str, expected: tuple) -> None:
        result = parse_mode(mode)
        assert result == expected


class TestStripMode:
    """Tests for strip_mode."""

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [
            pytest.param("rb", "r", id="read_binary"),
            pytest.param("wt", "w", id="write_text"),
            pytest.param("a+b", "a+", id="append_plus_binary"),
            pytest.param("r", "r", id="read_plain"),
        ],
    )
    def test_strip_mode(self, mode: str, expected: str) -> None:
        assert strip_mode(mode) == expected


class TestNormalizeMode:
    """Tests for normalize_mode."""

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [
            pytest.param("r", "rb", id="read"),
            pytest.param("rb", "rb", id="read_binary"),
            pytest.param("w", "wb", id="write"),
            pytest.param("wt", "wb", id="write_text"),
            pytest.param("a+", "a+b", id="append_plus"),
            pytest.param("r+b", "r+b", id="read_plus_binary"),
        ],
    )
    def test_normalize_mode(self, mode: str, expected: str) -> None:
        assert normalize_mode(mode) == expected


class TestPadEmptyFile:
    """Tests for pad_empty_file."""

    def test_pads_empty_file(self) -> None:
        f = io.BytesIO(b"")
        pad_empty_file(f)
        f.seek(0)
        assert f.read() == NULL_BYTE

    def test_does_not_pad_nonempty_file(self) -> None:
        content = b"hello"
        f = io.BytesIO(content)
        pad_empty_file(f)
        f.seek(0)
        assert f.read() == content


class TestRenameToTarget:
    """Tests for rename_to_target."""

    def test_renames_file(self, tmp_path: Path) -> None:
        source = tmp_path / "tmpfile123"
        source.write_bytes(b"data")
        result = rename_to_target(str(source), "final.txt")
        expected = tmp_path / "final.txt"
        assert result == expected
        assert expected.read_bytes() == b"data"
        assert not source.exists()


class TestPathToParentId:
    """Tests for SynapseFS._path_to_parent_id edge cases."""

    def test_rootless_bare_name_raises_value_error(self) -> None:
        """Verify that a bare name in rootless mode raises ValueError."""
        fs = SynapseFS()
        with pytest.raises(ValueError, match="must start with a Synapse ID"):
            fs._path_to_parent_id("not_a_synapse_id")


class TestPathToSynapseId:
    """Tests for SynapseFS._path_to_synapse_id edge cases."""

    def test_rootless_non_id_path_raises_value_error(self) -> None:
        """Verify that a path not starting with a Synapse ID raises ValueError."""
        fs = SynapseFS()
        with pytest.raises(ValueError):
            fs._path_to_synapse_id("SynapseFS Test Project/syn50555279")
