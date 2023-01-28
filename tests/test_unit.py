from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile

import pytest
from fs import errors, open_fs
from synapseclient.core.exceptions import SynapseFileNotFoundError, SynapseHTTPError

from synapsefs.remote_file import RemoteFile
from synapsefs.synapsefs import SynapseFS, synapse_errors


def test_for_an_error_with_a_path_that_does_not_start_with_a_synapse_id(synapse_fs):
    with pytest.raises(ValueError):
        synapse_fs._path_to_synapse_id("SynapseFS Test Project/syn50555279")


def test_that_a_path_with_multiple_synapse_ids_can_be_traversed(synapse_fs):
    info = synapse_fs.getinfo("syn50545516/syn50557597")
    assert info.name == "TestSubDir"
    assert info.is_dir


def test_that_retrieving_the_parent_id_for_a_synapse_id_path_works(synapse_fs):
    actual = synapse_fs._path_to_parent_id("syn50555279")
    assert actual == "syn50545516"


def test_for_an_error_when_retrieving_the_parent_for_a_non_synapse_id_path(synapse_fs):
    with pytest.raises(ValueError):
        synapse_fs._path_to_parent_id("test.txt")


def test_for_an_error_when_retrieving_the_parent_entity_for_a_project(synapse_fs):
    with pytest.raises(ValueError):
        synapse_fs._get_parent_id("syn50545516")


def test_that_providing_an_empty_syn_url_to_open_fs_will_create_a_rootless_synapsefs():
    fs = open_fs("syn://")
    assert isinstance(fs, SynapseFS)
    assert fs.root is None


def test_for_fs_errors_when_using_synapse_errors_context_manager():
    with pytest.raises(errors.FSError):
        with synapse_errors("foo"):
            raise SynapseFileNotFoundError("bar")
    with pytest.raises(errors.FSError):
        with synapse_errors("foo"):
            raise SynapseHTTPError("does not exist")
    with pytest.raises(errors.FSError):
        with synapse_errors("foo"):
            raise SynapseHTTPError("already exists")
    with pytest.raises(SynapseHTTPError):
        with synapse_errors("foo"):
            raise SynapseHTTPError("something else")


def test_that_a_remote_file_without_a_close_on_callable_can_be_closed():
    with TemporaryFile() as temp_file:
        remote_file = RemoteFile(temp_file, "foo", "w", on_close=None)
        remote_file.close()


def test_that_staging_a_local_file_creates_a_copy():
    path = Path(__file__)
    local_fs = open_fs(f"osfs://{path.parent}")
    with TemporaryDirectory() as tmp_dir_name:
        tmp_dir_path = Path(tmp_dir_name)
        target_path = tmp_dir_path / "test.txt"
        assert not target_path.exists()
        target_file = target_path.open("wb")
        local_fs.download(path.name, target_file)
        target_file.close()
        assert target_path.exists()
