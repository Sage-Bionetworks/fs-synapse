"""
Integration tests for SynapseFS.
Requires SYNAPSE_AUTH_TOKEN environment variable.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import fsspec
import pytest
from synapseclient.models import Folder

from synapsefs import SynapseFS

pytestmark = pytest.mark.integration


class TestInit:
    """Tests for SynapseFS.__init__."""

    def test_rootless_mode(self, auth_token: str) -> None:
        """Verify that omitting root creates a rootless SynapseFS with root=None."""
        fs = SynapseFS(auth_token=auth_token)
        assert fs.root is None

    def test_rootless_mode_with_empty_string(self, auth_token: str) -> None:
        """Verify that passing an empty string for root creates rootless mode."""
        fs = SynapseFS("", auth_token=auth_token)
        assert fs.root is None

    def test_rooted_with_project_id(self, auth_token: str) -> None:
        """Verify that a project Synapse ID can be used as root."""
        fs = SynapseFS("syn50545516", auth_token=auth_token)
        assert fs.root == "syn50545516"

    def test_rooted_with_folder_id(self, auth_token: str, test_folder: Folder) -> None:
        """Verify that a folder Synapse ID can be used as root."""
        fs = SynapseFS(test_folder.id, auth_token=auth_token)
        assert fs.root == test_folder.id

    def test_rooted_with_path_resolves_to_folder(
        self, fs: SynapseFS, auth_token: str, test_folder: Folder
    ) -> None:
        """Verify that a compound path (synID/name) resolves to the subfolder."""
        fs.mkdir("subdir")
        new_fs = SynapseFS(f"{test_folder.id}/subdir", auth_token=auth_token)
        assert new_fs.root is not None

    def test_error_when_root_is_a_file(self, fs: SynapseFS, auth_token: str) -> None:
        """Verify that using a file's Synapse ID as root raises ValueError."""
        fs.touch("file.txt")
        synapse_id = fs._path_to_synapse_id("file.txt")
        with pytest.raises(ValueError):
            SynapseFS(synapse_id, auth_token=auth_token)

    def test_error_when_root_does_not_start_with_synapse_id(
        self, auth_token: str
    ) -> None:
        """Verify that a plain name (not a Synapse ID) as root raises ValueError."""
        with pytest.raises(ValueError):
            SynapseFS("NotASynapseID", auth_token=auth_token)

    def test_error_when_root_path_does_not_start_with_synapse_id(
        self, auth_token: str
    ) -> None:
        """Verify that a path not starting with a Synapse ID raises ValueError."""
        with pytest.raises(ValueError):
            SynapseFS("SomeName/syn12345", auth_token=auth_token)


class TestInfo:
    """Tests for SynapseFS.info."""

    def test_info_for_file(self, fs: SynapseFS) -> None:
        """Verify that info returns correct name, type, and size for a file."""
        fs.pipe_file("hello.txt", b"hello")
        info = fs.info("hello.txt")
        assert info["name"] == "hello.txt"
        assert info["type"] == "file"
        assert info["size"] == 5
        assert info["synapse_entity_type"] == "File"

    def test_info_for_directory(self, fs: SynapseFS) -> None:
        """Verify that info returns type 'directory' and size 0 for a folder."""
        fs.mkdir("test_dir")
        info = fs.info("test_dir")
        assert info["name"] == "test_dir"
        assert info["type"] == "directory"
        assert info["size"] == 0
        assert info["synapse_entity_type"] == "Folder"

    def test_info_for_root(self, fs: SynapseFS) -> None:
        """Verify that info on '/' returns the root directory metadata."""
        info = fs.info("/")
        assert info["type"] == "directory"
        assert info["synapse_id"] is not None

    def test_info_contains_synapse_metadata(self, fs: SynapseFS) -> None:
        """Verify that info includes all expected Synapse-specific metadata keys."""
        fs.pipe_file("meta.txt", b"data")
        info = fs.info("meta.txt")
        assert "synapse_id" in info
        assert "synapse_parent_id" in info
        assert "synapse_etag" in info
        assert "synapse_creator_id" in info
        assert "synapse_modifier_id" in info
        assert "created" in info
        assert "modified" in info
        # Username keys present but None without detail=True
        assert info["synapse_creator_username"] is None
        assert info["synapse_modifier_username"] is None

    def test_info_with_detail_fetches_usernames(self, fs: SynapseFS) -> None:
        """Verify that info with detail=True populates creator/modifier usernames."""
        fs.pipe_file("detail.txt", b"data")
        info = fs.info("detail.txt", detail=True)
        assert info["synapse_creator_username"] is not None
        assert info["synapse_modifier_username"] is not None

    def test_info_file_specific_metadata(self, fs: SynapseFS) -> None:
        """
        Verify that file-specific fields (content_type, md5, version) are populated.
        """
        fs.pipe_file("typed.txt", b"content")
        info = fs.info("typed.txt")
        assert info["synapse_content_type"] is not None
        assert info["synapse_content_md5"] is not None
        assert info["synapse_version_number"] is not None

    def test_info_directory_has_null_file_metadata(self, fs: SynapseFS) -> None:
        """
        Verify that file-specific metadata fields are None for directories.
        """
        fs.mkdir("test_dir")
        info = fs.info("test_dir")
        assert info["synapse_content_type"] is None
        assert info["synapse_content_md5"] is None
        assert info["synapse_version_label"] is None
        assert info["synapse_version_number"] is None

    def test_info_includes_annotations(self, fs: SynapseFS) -> None:
        """Verify that info includes an 'annotations' key for a file."""
        fs.touch("annotated.txt")
        info = fs.info("annotated.txt")
        assert "annotations" in info

    def test_info_nonexistent_raises_file_not_found(self, fs: SynapseFS) -> None:
        """Verify that info raises FileNotFoundError for a nonexistent path."""
        with pytest.raises(FileNotFoundError):
            fs.info("doesnotexist")

    def test_info_empty_file_has_size_one(self, fs: SynapseFS) -> None:
        """Verify that an empty file reports size=1 due to the null-byte workaround."""
        fs.pipe_file("empty", b"")
        info = fs.info("empty")
        assert info["size"] == 1

    def test_info_is_json_serializable(self, fs: SynapseFS) -> None:
        """Verify that info() output can be serialized to JSON."""
        fs.pipe_file("serial.txt", b"data")
        info = fs.info("serial.txt")
        try:
            json.dumps(info)
        except (TypeError, ValueError):
            pytest.fail("info() should be JSON serializable")

    def test_info_timestamps_are_numeric_or_none(self, fs: SynapseFS) -> None:
        """Verify that created/modified are None, int, or float."""
        fs.pipe_file("timed.txt", b"data")
        info = fs.info("timed.txt")
        assert isinstance(info.get("created"), (type(None), int, float))
        assert isinstance(info.get("modified"), (type(None), int, float))


class TestLs:
    """Tests for SynapseFS.ls."""

    def test_ls_returns_names(self, fs: SynapseFS) -> None:
        """Verify that ls with detail=False returns a list of path strings."""
        fs.touch("a.txt")
        fs.touch("b.txt")
        entries = fs.ls("/", detail=False)
        base_names = [e.split("/")[-1] for e in entries]
        assert "a.txt" in base_names
        assert "b.txt" in base_names

    def test_ls_with_detail(self, fs: SynapseFS) -> None:
        """Verify that ls with detail=True returns dicts with name, type, and size."""
        fs.touch("c.txt")
        fs.mkdir("subdir")
        entries = fs.ls("/", detail=True)
        assert isinstance(entries, list)
        assert len(entries) >= 2
        for entry in entries:
            assert "name" in entry
            assert "type" in entry
            assert "size" in entry

    def test_ls_subdirectory(self, fs: SynapseFS) -> None:
        """Verify that ls lists children of a subdirectory."""
        fs.mkdir("parent")
        fs.touch("parent/child.txt")
        entries = fs.ls("parent", detail=False)
        base_names = [e.split("/")[-1] for e in entries]
        assert "child.txt" in base_names

    def test_ls_empty_directory(self, fs: SynapseFS) -> None:
        """Verify that ls returns an empty list for a directory with no children."""
        fs.mkdir("test_dir")
        entries = fs.ls("test_dir", detail=False)
        assert entries == []

    def test_ls_on_file_raises_not_a_directory(self, fs: SynapseFS) -> None:
        """Verify that ls on a file path raises NotADirectoryError."""
        fs.touch("not_a_dir.txt")
        with pytest.raises(NotADirectoryError):
            fs.ls("not_a_dir.txt")

    def test_ls_nonexistent_raises_file_not_found(self, fs: SynapseFS) -> None:
        """Verify that ls raises FileNotFoundError for a nonexistent path."""
        with pytest.raises(FileNotFoundError):
            fs.ls("nonexistent")

    def test_ls_detail_shows_types(self, fs: SynapseFS) -> None:
        """Verify that detail entries distinguish files from directories by type."""
        fs.makedirs("type_dir/sub_dir")
        fs.touch("type_dir/file.txt")
        entries = fs.ls("type_dir", detail=True)
        types = {e["name"].split("/")[-1]: e["type"] for e in entries}
        assert types["file.txt"] == "file"
        assert types["sub_dir"] == "directory"


class TestMkdir:
    """Tests for SynapseFS.mkdir."""

    def test_mkdir_creates_directory(self, fs: SynapseFS) -> None:
        """
        Verify that mkdir creates a new directory that exists and has type 'directory'.
        """
        fs.mkdir("newdir")
        assert fs.exists("newdir")
        info = fs.info("newdir")
        assert info["type"] == "directory"

    def test_mkdir_in_existing_parent(self, fs: SynapseFS) -> None:
        """Verify that mkdir creates a subdirectory when the parent already exists."""
        fs.mkdir("a")
        fs.mkdir("a/b")
        assert fs.exists("a/b")

    def test_mkdir_root_is_noop(self, fs: SynapseFS) -> None:
        """Verify that mkdir on root or empty string is a no-op and does not raise."""
        fs.mkdir("/")
        fs.mkdir("")

    def test_mkdir_existing_directory_with_create_parents(self, fs: SynapseFS) -> None:
        """
        Verify that mkdir on an existing directory does not raise when
          create_parents=True.
        """
        fs.mkdir("exist_dir")
        fs.mkdir("exist_dir", create_parents=True)


class TestMakedirs:
    """Tests for SynapseFS.makedirs."""

    def test_makedirs_creates_nested_directories(self, fs: SynapseFS) -> None:
        """Verify that makedirs creates all intermediate directories recursively."""
        fs.makedirs("x/y/z")
        assert fs.exists("x")
        assert fs.exists("x/y")
        assert fs.exists("x/y/z")

    def test_makedirs_existing_intermediate_dirs(self, fs: SynapseFS) -> None:
        """Verify that makedirs skips already-existing intermediate directories."""
        fs.mkdir("existing")
        fs.makedirs("existing/new/deep")
        assert fs.exists("existing/new/deep")

    def test_makedirs_root_is_noop(self, fs: SynapseFS) -> None:
        """
        Verify that makedirs on root or empty string is a no-op and does not raise.
        """
        fs.makedirs("/")
        fs.makedirs("")

    def test_makedirs_single_level(self, fs: SynapseFS) -> None:
        """Verify that makedirs works for a single directory level."""
        fs.makedirs("single")
        assert fs.exists("single")

    def test_makedirs_rootless_requires_synapse_id(self, auth_token: str) -> None:
        """
        Verify that makedirs in rootless mode raises ValueError without a Synapse ID.
        """
        rootless_fs = SynapseFS(auth_token=auth_token)
        with pytest.raises(ValueError):
            rootless_fs.makedirs("not_a_synapse_id/subdir")


class TestOpen:
    """Tests for SynapseFS.open (via _open)."""

    def test_open_write_and_read(self, fs: SynapseFS) -> None:
        """Verify that data written via open('wb') can be read back via open('rb')."""
        with fs.open("rw.txt", "wb") as f:
            f.write(b"hello world")
        with fs.open("rw.txt", "rb") as f:
            data = f.read()
        assert data == b"hello world"

    def test_open_exclusive_mode_raises_on_existing(self, fs: SynapseFS) -> None:
        """
        Verify that exclusive mode ('x') raises FileExistsError for existing files.
        """
        fs.touch("exists.txt")
        with pytest.raises(FileExistsError):
            fs.open("exists.txt", "xb")

    def test_open_exclusive_mode_creates_new_file(self, fs: SynapseFS) -> None:
        """Verify that exclusive mode ('x') creates and writes a new file."""
        with fs.open("exclusive.txt", "xb") as f:
            f.write(b"exclusive")
        with fs.open("exclusive.txt", "rb") as f:
            data = f.read()
        assert data == b"exclusive"

    def test_open_read_nonexistent_raises_file_not_found(self, fs: SynapseFS) -> None:
        """
        Verify that opening a nonexistent file for reading raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            fs.open("nonexistent.txt", "rb")

    def test_open_directory_raises_is_a_directory(self, fs: SynapseFS) -> None:
        """Verify that opening a directory raises IsADirectoryError."""
        fs.mkdir("a_dir")
        with pytest.raises(IsADirectoryError):
            fs.open("a_dir", "rb")

    def test_open_write_overwrites_existing(self, fs: SynapseFS) -> None:
        """Verify that opening an existing file with 'wb' replaces its contents."""
        fs.pipe_file("overwrite.txt", b"old data")
        with fs.open("overwrite.txt", "wb") as f:
            f.write(b"new data")
        with fs.open("overwrite.txt", "rb") as f:
            data = f.read()
        assert data == b"new data"

    def test_open_append_mode(self, fs: SynapseFS) -> None:
        """Verify that append mode adds data to the end of an existing file."""
        fs.pipe_file("append.txt", b"first")
        with fs.open("append.txt", "ab") as f:
            f.write(b"second")
        with fs.open("append.txt", "rb") as f:
            data = f.read()
        assert data == b"firstsecond"

    def test_open_empty_file_writes_null_byte(self, fs: SynapseFS) -> None:
        """
        Verify that closing an empty file results in size=1 (null-byte workaround).
        """
        with fs.open("empty.txt", "wb"):
            pass  # Write nothing
        info = fs.info("empty.txt")
        assert info["size"] == 1


class TestRmFile:
    """Tests for SynapseFS.rm_file."""

    def test_rm_file_removes_file(self, fs: SynapseFS) -> None:
        """Verify that rm_file deletes an existing file."""
        fs.touch("to_remove.txt")
        assert fs.exists("to_remove.txt")
        fs.rm_file("to_remove.txt")
        assert not fs.exists("to_remove.txt")

    def test_rm_file_on_directory_raises_is_a_directory(self, fs: SynapseFS) -> None:
        """Verify that rm_file raises IsADirectoryError when given a directory."""
        fs.mkdir("test_dir")
        with pytest.raises(IsADirectoryError):
            fs.rm_file("test_dir")

    def test_rm_file_nonexistent_raises_file_not_found(self, fs: SynapseFS) -> None:
        """Verify that rm_file raises FileNotFoundError for a nonexistent path."""
        with pytest.raises(FileNotFoundError):
            fs.rm_file("ghost.txt")


class TestRmdir:
    """Tests for SynapseFS.rmdir."""

    def test_rmdir_removes_empty_directory(self, fs: SynapseFS) -> None:
        """Verify that rmdir deletes an empty directory."""
        fs.mkdir("empty_dir")
        assert fs.exists("empty_dir")
        fs.rmdir("empty_dir")
        assert not fs.exists("empty_dir")

    def test_rmdir_non_empty_raises_os_error(self, fs: SynapseFS) -> None:
        """Verify that rmdir raises OSError when the directory is not empty."""
        fs.mkdir("notempty")
        fs.touch("notempty/file.txt")
        with pytest.raises(OSError):
            fs.rmdir("notempty")

    def test_rmdir_on_file_raises_not_a_directory(self, fs: SynapseFS) -> None:
        """Verify that rmdir raises NotADirectoryError when given a file."""
        fs.touch("a_file.txt")
        with pytest.raises(NotADirectoryError):
            fs.rmdir("a_file.txt")

    def test_rmdir_nonexistent_raises_file_not_found(self, fs: SynapseFS) -> None:
        """Verify that rmdir raises FileNotFoundError for a nonexistent path."""
        with pytest.raises(FileNotFoundError):
            fs.rmdir("no_such_dir")

    def test_rmdir_root_raises_permission_error(self, fs: SynapseFS) -> None:
        """Verify that rmdir raises PermissionError when attempting to remove root."""
        with pytest.raises(PermissionError):
            fs.rmdir("/")
        with pytest.raises(PermissionError):
            fs.rmdir("")


class TestRm:
    """Tests for SynapseFS.rm."""

    def test_rm_removes_file(self, fs: SynapseFS) -> None:
        """Verify that rm deletes a single file."""
        fs.touch("rm_file.txt")
        fs.rm("rm_file.txt")
        assert not fs.exists("rm_file.txt")

    def test_rm_empty_directory_without_recursive(self, fs: SynapseFS) -> None:
        """
        Verify that rm deletes an empty directory without requiring recursive=True.
        """
        fs.mkdir("empty_dir")
        fs.rm("empty_dir")
        assert not fs.exists("empty_dir")

    def test_rm_non_empty_directory_without_recursive_raises(
        self, fs: SynapseFS
    ) -> None:
        """Verify that rm raises OSError on a non-empty directory without recursive."""
        fs.mkdir("notempty")
        fs.touch("notempty/file.txt")
        with pytest.raises(OSError):
            fs.rm("notempty", recursive=False)

    def test_rm_recursive_removes_directory_tree(self, fs: SynapseFS) -> None:
        """Verify that rm with recursive=True deletes an entire directory tree."""
        fs.makedirs("tree/branch")
        fs.touch("tree/branch/leaf.txt")
        fs.rm("tree", recursive=True)
        assert not fs.exists("tree")

    def test_rm_nonexistent_raises_file_not_found(self, fs: SynapseFS) -> None:
        """Verify that rm raises FileNotFoundError for a nonexistent path."""
        with pytest.raises(FileNotFoundError):
            fs.rm("nonexistent")


class TestTouch:
    """Tests for SynapseFS.touch."""

    def test_touch_creates_new_file(self, fs: SynapseFS) -> None:
        """Verify that touch creates a file that did not previously exist."""
        assert not fs.exists("new.txt")
        fs.touch("new.txt")
        assert fs.exists("new.txt")

    def test_touch_new_file_has_size_one(self, fs: SynapseFS) -> None:
        """Verify that a touched file has size=1 due to the null-byte workaround."""
        fs.touch("sized.txt")
        info = fs.info("sized.txt")
        assert info["size"] == 1

    def test_touch_truncate_existing_file(self, fs: SynapseFS) -> None:
        """Verify that touch with truncate=True resets file size to 1 (null byte)."""
        fs.pipe_file("trunc.txt", b"some data")
        assert fs.info("trunc.txt")["size"] == 9
        fs.touch("trunc.txt", truncate=True)
        assert fs.info("trunc.txt")["size"] == 1

    def test_touch_no_truncate_preserves_content(self, fs: SynapseFS) -> None:
        """Verify that touch with truncate=False preserves the existing file size."""
        fs.pipe_file("keep.txt", b"keep me")
        fs.touch("keep.txt", truncate=False)
        info = fs.info("keep.txt")
        assert info["size"] == 7

    def test_touch_creates_file_type(self, fs: SynapseFS) -> None:
        """Verify that a touched file has type 'file' in its info."""
        fs.touch("typed.txt")
        info = fs.info("typed.txt")
        assert info["type"] == "file"


class TestFsspecRegistration:
    """Tests for fsspec protocol registration."""

    def test_fsspec_filesystem_creates_synapse_fs(self) -> None:
        """Verify that fsspec.filesystem('syn') returns a SynapseFS instance."""
        fs = fsspec.filesystem("syn")
        assert isinstance(fs, SynapseFS)
        assert fs.root is None


class TestRootlessPathTraversal:
    """Tests for rootless SynapseFS path traversal."""

    def test_path_with_multiple_synapse_ids(self, rootless_fs: SynapseFS) -> None:
        """Verify that a path with multiple Synapse IDs can be traversed."""
        info = rootless_fs.info("syn50545516/syn50557597")
        assert info["name"] == "syn50545516/syn50557597"
        assert info["type"] == "directory"

    def test_open_file_by_synapse_id(self, rootless_fs: SynapseFS) -> None:
        """Verify that a rootless SynapseFS can open a file directly by Synapse ID."""
        with rootless_fs.open("syn50555279", "r") as in_file:
            contents = in_file.read()
        assert contents == "foobar\n"


class TestGet:
    """Tests for SynapseFS.get (staging files to local disk)."""

    def test_get_downloads_file_to_local_path(self, fs: SynapseFS) -> None:
        """Verify that get() downloads a Synapse file to a local path."""
        fs.pipe_file("download_me.txt", b"hello from synapse")
        with TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "download_me.txt"
            assert not target.exists()
            fs.get("download_me.txt", str(target))
            assert target.exists()
            assert target.read_bytes() == b"hello from synapse"


class TestDoublePeriodPaths:
    """Tests for '..' (double-period) path resolution."""

    def test_double_period_resolves_to_same_path(self, fs: SynapseFS) -> None:
        """Verify that foo/bar/../bar/baz resolves to the same ID as foo/bar/baz."""
        fs.makedirs("foo/bar/baz")
        id_direct = fs._path_to_synapse_id("foo/bar/baz")
        id_via_dot_dot = fs._path_to_synapse_id("foo/bar/../bar/baz")
        assert id_direct == id_via_dot_dot

    def test_double_period_after_file_resolves_to_parent(self, fs: SynapseFS) -> None:
        """Verify that foo/test.txt/.. resolves to the same entity as foo."""
        fs.mkdir("foo")
        fs.touch("foo/test.txt")
        info_parent = fs.info("foo")
        info_via_dot_dot = fs.info("foo/test.txt/..")
        assert info_parent["synapse_id"] == info_via_dot_dot["synapse_id"]

    def test_init_with_double_period_after_folder(self, auth_token: str) -> None:
        """Verify that SynapseFS('syn50557597/..') roots at the parent project."""
        fs = SynapseFS("syn50557597/..", auth_token=auth_token)
        info = fs.info(".")
        assert info["synapse_id"] == "syn50545516"

    def test_init_with_double_period_after_file(self, auth_token: str) -> None:
        """Verify that SynapseFS('syn50555279/..') roots at the parent project."""
        fs = SynapseFS("syn50555279/..", auth_token=auth_token)
        info = fs.info(".")
        assert info["synapse_id"] == "syn50545516"


class TestInvalidEntityType:
    """Tests for unsupported Synapse entity types."""

    def test_table_entity_raises_value_error(self, fs: SynapseFS) -> None:
        """Verify that a Table entity raises ValueError (unsupported type)."""
        with pytest.raises(ValueError):
            fs._synapse_id_to_entity("syn50557522")


class TestGetParentId:
    """Tests for SynapseFS._get_parent_id."""

    def test_project_has_no_parent(self, rootless_fs: SynapseFS) -> None:
        """Verify that _get_parent_id raises ValueError for a project."""
        with pytest.raises(ValueError):
            rootless_fs._get_parent_id("syn50545516")


class TestPathToParentId:
    """Tests for SynapseFS._path_to_parent_id."""

    def test_returns_parent_for_synapse_id(self, rootless_fs: SynapseFS) -> None:
        """Verify that _path_to_parent_id returns the parent ID for a Synapse ID."""
        actual = rootless_fs._path_to_parent_id("syn50555279")
        assert actual == "syn50545516"
