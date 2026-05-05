"""Unit tests for SynapseFS class."""

import fsspec
import pytest
from pytest_mock import MockerFixture
from synapseclient.core.exceptions import SynapseFileNotFoundError, SynapseHTTPError

from synapsefs.synapsefs import SynapseFS, synapse_errors


class TestIsSynapseId:
    """Tests for SynapseFS.is_synapse_id."""

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("syn123", id="standard"),
            pytest.param("syn0", id="zero"),
            pytest.param("syn999999999", id="large_number"),
        ],
    )
    def test_valid(self, rootless_fs: SynapseFS, text: str) -> None:
        """Verify that well-formed Synapse IDs are recognized."""
        assert rootless_fs.is_synapse_id(text)

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("syn", id="prefix_only"),
            pytest.param("SYN123", id="uppercase"),
            pytest.param("123syn", id="digits_before_prefix"),
            pytest.param("syn123abc", id="trailing_letters"),
            pytest.param("", id="empty_string"),
            pytest.param("synABC", id="letters_after_prefix"),
        ],
    )
    def test_invalid(self, rootless_fs: SynapseFS, text: str) -> None:
        """Verify that malformed strings are not recognized as Synapse IDs."""
        assert not rootless_fs.is_synapse_id(text)


class TestStripProtocol:
    """Tests for SynapseFS._strip_protocol."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            pytest.param("syn://foo", "foo", id="protocol"),
            pytest.param("syn://foo/", "foo", id="protocol_trailing_slash"),
            pytest.param("/foo/", "foo", id="leading_and_trailing_slashes"),
            pytest.param("foo", "foo", id="plain_path"),
            pytest.param("", "", id="empty_string"),
            pytest.param("syn://foo/bar/baz", "foo/bar/baz", id="nested_path"),
            pytest.param("syn://syn123456", "syn123456", id="synapse_id"),
        ],
    )
    def test_strip_protocol(self, path: str, expected: str) -> None:
        """Verify that _strip_protocol normalizes paths correctly."""
        assert SynapseFS._strip_protocol(path) == expected


class TestRootlessInit:
    """Tests for SynapseFS() without auth token."""

    def test_no_root_creates_rootless_synapse_fs(self) -> None:
        """Verify that omitting root creates a rootless SynapseFS with root=None."""
        fs = SynapseFS()
        assert isinstance(fs, SynapseFS)
        assert fs.root is None


class TestSynapseErrors:
    """Tests for the synapse_errors context manager."""

    def test_file_not_found_error(self) -> None:
        """Verify SynapseFileNotFoundError maps to FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            with synapse_errors("foo"):
                raise SynapseFileNotFoundError("bar")

    def test_does_not_exist_error(self) -> None:
        """Verify SynapseHTTPError 'does not exist' maps to FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            with synapse_errors("foo"):
                raise SynapseHTTPError("does not exist")

    def test_already_exists_error(self) -> None:
        """Verify SynapseHTTPError 'already exists' maps to FileExistsError."""
        with pytest.raises(FileExistsError):
            with synapse_errors("foo"):
                raise SynapseHTTPError("already exists")

    def test_unrecognized_http_error_re_raises(self) -> None:
        """Verify unrecognized SynapseHTTPError is re-raised as-is."""
        with pytest.raises(SynapseHTTPError):
            with synapse_errors("foo"):
                raise SynapseHTTPError("something else")


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

    def test_rootless_root_path_raises_value_error(self) -> None:
        """Verify that querying '/' on a rootless FS raises ValueError.

        _strip_protocol turns '/' into '', and with no root there is no
        Synapse ID to resolve, so _path_to_synapse_id should raise.
        """
        fs = SynapseFS()
        stripped = fs._strip_protocol("/")
        assert stripped == ""
        with pytest.raises(ValueError, match="must be a Synapse ID"):
            fs._path_to_synapse_id(stripped)


class TestFsspecRegistration:
    """Tests for fsspec protocol registration."""

    def test_fsspec_filesystem_creates_synapse_fs(self) -> None:
        """Verify that fsspec.filesystem('syn') returns a SynapseFS instance."""
        fs = fsspec.filesystem("syn")
        assert isinstance(fs, SynapseFS)


class TestMakedirs:
    """Tests for SynapseFS._makedirs (mocked, no Synapse calls)."""

    FILE_TYPE = "org.sagebionetworks.repo.model.FileEntity"
    FOLDER_TYPE = "org.sagebionetworks.repo.model.Folder"

    def test_file_in_path_raises_not_a_directory(self, mocker: MockerFixture) -> None:
        """Verify that a FileEntity in the path raises NotADirectoryError.

        Regression: the type literal in _makedirs previously read 'File' rather
        than 'FileEntity', so file-blockers fell through to a Synapse 400.
        """
        fs = SynapseFS()
        mocker.patch.object(
            fs,
            "_get_children",
            return_value=[
                {"id": "syn1", "name": "blocker.txt", "type": self.FILE_TYPE}
            ],
        )
        with pytest.raises(NotADirectoryError, match="blocker.txt"):
            fs._makedirs("syn999/blocker.txt/below")

    def test_existing_leaf_without_exist_ok_raises(self, mocker: MockerFixture) -> None:
        """Verify existing leaf folder raises FileExistsError without exist_ok."""
        fs = SynapseFS()
        mocker.patch.object(
            fs,
            "_get_children",
            return_value=[{"id": "syn2", "name": "leaf", "type": self.FOLDER_TYPE}],
        )
        with pytest.raises(FileExistsError):
            fs._makedirs("syn999/leaf")

    def test_existing_leaf_with_exist_ok_returns_id(
        self, mocker: MockerFixture
    ) -> None:
        """Verify existing leaf folder with exist_ok=True returns its ID."""
        fs = SynapseFS()
        mocker.patch.object(
            fs,
            "_get_children",
            return_value=[{"id": "syn2", "name": "leaf", "type": self.FOLDER_TYPE}],
        )
        assert fs._makedirs("syn999/leaf", exist_ok=True) == "syn2"

    def test_creates_missing_intermediates(self, mocker: MockerFixture) -> None:
        """Verify missing intermediates are created via syn_store."""
        fs = SynapseFS()
        fs._local.synapse = mocker.MagicMock()
        mocker.patch.object(fs, "_get_children", return_value=[])
        store_mock = mocker.patch(
            "synapsefs.synapsefs.syn_store",
            side_effect=[
                mocker.MagicMock(id="syn_a"),
                mocker.MagicMock(id="syn_b"),
            ],
        )
        result = fs._makedirs("syn999/a/b")
        assert result == "syn_b"
        assert store_mock.call_count == 2

    def test_rootless_non_id_path_raises_value_error(self) -> None:
        """Verify rootless path not starting with a Synapse ID raises ValueError."""
        fs = SynapseFS()
        with pytest.raises(ValueError, match="must start with a Synapse ID"):
            fs._makedirs("not_a_syn_id/foo")
        assert fs.root is None
