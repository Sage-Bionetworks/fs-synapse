from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from pathlib import PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryDirectory, mkdtemp
from typing import Any, Generator, Literal, overload

from fsspec import AbstractFileSystem
from synapseclient.api import get_children
from synapseclient.client import Synapse
from synapseclient.core.async_utils import wrap_async_generator_to_sync_generator
from synapseclient.core.exceptions import SynapseFileNotFoundError, SynapseHTTPError
from synapseclient.core.utils import iso_to_datetime
from synapseclient.models import File, Folder, Project, UserProfile
from synapseclient.operations import FileOptions
from synapseclient.operations import delete as syn_delete
from synapseclient.operations import get as syn_get
from synapseclient.operations import store as syn_store

from synapsefs.remote_file import RemoteFile
from synapsefs.utils import (
    normalize_mode,
    pad_empty_file,
    parse_mode,
    rename_to_target,
    strip_mode,
)

SynapseEntity = File | Folder | Project


@contextmanager
def synapse_errors(path: str) -> Generator[None, None, None]:
    """A context manager for mapping ``synapseclient`` errors to standard exceptions."""
    try:
        yield
    except SynapseFileNotFoundError:
        raise FileNotFoundError(path)
    except SynapseHTTPError as err:
        message = err.args[0]
        if "does not exist" in message:
            raise FileNotFoundError(path)
        elif "already exists" in message:
            raise FileExistsError(message)
        else:
            raise  # Raise original exception as is


class SynapseFS(AbstractFileSystem):  # type: ignore[misc]
    """A file system-like interface for Synapse using fsspec."""

    protocol = "syn"
    cachable = False

    SYNID_REGEX = re.compile(r"syn[0-9]+")

    SUPPORTED_TYPES: dict[str, type]
    SUPPORTED_TYPES = {
        "file": File,
        "folder": Folder,
        "project": Project,
    }

    DEFAULT_SYNAPSE_ARGS: dict[str, Any]
    DEFAULT_SYNAPSE_ARGS = {
        "silent": True,
    }

    def __init__(
        self,
        root: str | None = None,
        auth_token: str | None = None,
        synapse_args: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Construct a Synapse filesystem for fsspec.

        Args:
            root: Synapse ID for a project or folder.
                Defaults to None (rootless mode).
            auth_token: Synapse personal access token.
                Defaults to None.
            synapse_args: Dictionary of arguments to pass to
                the ``Synapse`` class. Defaults to None.
        """
        super().__init__(**kwargs)
        self.auth_token = auth_token
        self.synapse_args = synapse_args or self.DEFAULT_SYNAPSE_ARGS.copy()
        self._local = threading.local()
        self.root = self._resolve_root(root)

    @property
    def synapse(self) -> Synapse:
        """Construct a thread-local Synapse client.

        Returns:
            Synapse: Authenticated Synapse client
        """
        if not hasattr(self._local, "synapse"):
            # Override cache with temporary directory
            self.synapse_args["cache_root_dir"] = mkdtemp()
            synapse = Synapse(**self.synapse_args)
            synapse.login(authToken=self.auth_token)
            self._local.synapse = synapse
        # Clear the Synapse cache to avoid unwanted side effects. More info here:
        # https://github.com/Sage-Bionetworks-Workflows/py-dcqc/pull/3#discussion_r1068443214
        self._local.synapse.cache.purge(after_date=0)
        return self._local.synapse

    def is_synapse_id(self, text: str) -> bool:
        """Check whether the given text is a Synapse ID."""
        return self.SYNID_REGEX.fullmatch(text) is not None

    @classmethod
    def _strip_protocol(cls, path: str) -> str:
        """Strip the syn:// protocol prefix from a path."""
        if path.startswith("syn://"):
            path = path[len("syn://") :]
        return path.strip("/")

    def _resolve_root(self, root: str | None) -> str | None:
        """Resolve the given root path (if not None) to a Synapse entity ID.

        Args:
            root: Synapse ID for a project or folder.
                Defaults to None (rootless mode).

        Raises:
            ValueError: If the root is not or does not start with a Synapse ID.
            ValueError: If the root does not resolve to a project or folder.

        Returns:
            A single Synapse ID to act as the root.
        """
        if root is None or root == "":
            return None

        root_path = PurePosixPath(root)
        num_root_parts = len(root_path.parts)
        error_message = f"Root ({root}) must be `None` or start with a Synapse ID."

        if num_root_parts == 1:
            if not self.is_synapse_id(root):
                raise ValueError(error_message)
        else:  # num_root_parts > 1
            starting_entity, _, path = root.strip("/").partition("/")
            if not self.is_synapse_id(starting_entity):
                raise ValueError(error_message)
            root = self._path_to_synapse_id(path, starting_entity)

        # Ensure that the root is not a file
        with synapse_errors(root):
            root_entity = syn_get(
                root,
                file_options=FileOptions(download_file=False),
                synapse_client=self.synapse,
            )
        if not isinstance(root_entity, (Folder, Project)):
            message = f"Root ({root}) must resolve to a project or folder."
            raise ValueError(message)

        return root

    def _path_to_synapse_id(self, path: str, starting_entity: str | None = None) -> str:
        """Resolve a path to a Synapse ID starting from the root.

        The slash-delimited parts of the given path can consist
        of folder/file names or Synapse IDs.

        If the SynapseFS instance does not have a root, then the
        given path must start with a Synapse ID.

        Args:
            path: Path to a resource on the filesystem
            starting_entity: Synapse ID for where to
                start the traversal. Defaults to the root.

        Returns:
            Synapse ID for the resolved file or folder

        Raises:
            ValueError: If the path does not start with a
                Synapse ID while SynapseFS is rootless.
            FileNotFoundError: If the ``path`` does not
                resolve to existing entities.
        """
        original_path = path
        starting_entity = starting_entity or self.root

        if starting_entity is None:
            starting_entity, _, path = path.strip("/").partition("/")
            if not self.is_synapse_id(starting_entity):
                message = (
                    f"This SynapseFS is rootless, so the 1st part ({starting_entity}) "
                    f"of every path ({original_path}) must be a Synapse ID."
                )
                raise ValueError(message)

        # Starting with starting_entity, navigate the given path
        # by iterating each slash-delimited part
        current_entity = starting_entity
        for next_part in path.strip("/").split("/"):

            # Don't "move" if next_part refers to the root (which only happens once
            # at the beginning), the current directory, or an empty string
            if next_part in {"/", ".", ""}:
                continue

            # Move to the parent entity if next_part is the ".." symbol
            if next_part == "..":
                current_entity = self._get_parent_id(current_entity)
                continue

            # Otherwise, next_part should be the name or Synapse ID of a file/folder
            children_list = self._get_children(current_entity)
            # Build an "index" of children keyed on Synapse IDs or names
            # depending on whether next_part is a Synapse ID or not
            if self.is_synapse_id(next_part):
                children = {entity["id"]: entity for entity in children_list}
            else:
                children = {entity["name"]: entity for entity in children_list}
            # If next_part exists among the keys, return the associated Synapse ID
            if next_part in children:
                current_entity = children[next_part]["id"]
            else:
                raise FileNotFoundError(path)

        return current_entity

    def _synapse_id_to_entity(
        self,
        synapse_id: str,
        download_file: bool = False,
    ) -> SynapseEntity:
        """Retrieve and validate (meta)data for a Synapse entity

        Args:
            synapse_id: A Synapse ID
            download_file: Whether to download the associated file(s)

        Returns:
            The associated Synapse entity

        Raises:
            FileNotFoundError: If ``synapse_id`` does not exist.
            ValueError: If ``synapse_id`` does not correspond
                 to a supported entity type.
        """
        with synapse_errors(synapse_id):
            entity = syn_get(
                synapse_id,
                file_options=FileOptions(download_file=download_file),
                synapse_client=self.synapse,
            )
        valid_types = tuple(self.SUPPORTED_TYPES.values())
        if not isinstance(entity, valid_types):
            type_ = type(entity)
            message = f"{synapse_id} ({type_}) is not supported yet ({valid_types})."
            raise ValueError(message)
        return entity

    def _path_to_entity(self, path: str, download_file: bool = False) -> SynapseEntity:
        """Perform the validation and retrieval steps for a Synapse entity.

        Arguments:
            path: A path.
            download_file: Whether to download the associated file(s)

        Returns:
            A Synapse entity (File, Folder, or Project).
        """
        synapse_id = self._path_to_synapse_id(path)
        with synapse_errors(path):
            entity = self._synapse_id_to_entity(synapse_id, download_file)
        return entity

    def _path_to_parent_id(self, path: str) -> str:
        parent_path, _, basename = path.strip("/").rpartition("/")
        if parent_path == "":
            if self.root is not None:
                parent_id = self.root
            elif self.is_synapse_id(basename):
                parent_id = self._get_parent_id(basename)
            else:
                message = f"Path ({path}) must start with a Synapse ID when rootless."
                raise ValueError(message)
        else:
            parent_id = self._path_to_synapse_id(parent_path)
        return parent_id

    def _get_parent_id(self, entity_id: str) -> str:
        with synapse_errors(entity_id):
            entity = syn_get(
                entity_id,
                file_options=FileOptions(download_file=False),
                synapse_client=self.synapse,
            )
        if isinstance(entity, Project):
            message = f"Project ({entity.id}) has no parent."
            raise ValueError(message)
        parent_id = entity.parent_id
        with synapse_errors(parent_id):
            parent = syn_get(
                parent_id,
                file_options=FileOptions(download_file=False),
                synapse_client=self.synapse,
            )
        if parent.id is None:
            raise ValueError(f"Parent entity for {entity_id} has no ID.")
        return parent.id

    def _get_children(self, entity_id: str) -> list[dict[str, Any]]:
        """Retrieve a list of children for a Synapse entity

        Args:
            entity_id: The Synapse ID of a project or folder.

        Returns:
            List of children entities.
        """
        include_types = list(self.SUPPORTED_TYPES.keys())
        with synapse_errors(entity_id):
            children = wrap_async_generator_to_sync_generator(
                get_children,
                parent=entity_id,
                include_types=include_types,
                synapse_client=self.synapse,
            )
        return list(children)

    def info(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Get information about a resource on the filesystem.

        Arguments:
            path: A path to a resource on the filesystem.

        Returns:
            Dictionary with resource information.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
        """
        path = self._strip_protocol(path)
        entity = self._path_to_entity(path)

        name = entity.name
        is_dir = isinstance(entity, (Folder, Project))

        info: dict[str, Any] = {
            "name": name,
            "type": "directory" if is_dir else "file",
        }

        if not is_dir:
            info["size"] = entity.file_handle.content_size
        else:
            info["size"] = 0

        created_on = iso_to_datetime(entity.created_on)
        modified_on = iso_to_datetime(entity.modified_on)
        info["created"] = created_on.timestamp()
        info["modified"] = modified_on.timestamp()

        # Synapse-specific metadata (cheap — already on the entity object)
        info["synapse_id"] = entity.id
        info["synapse_parent_id"] = entity.parent_id
        info["synapse_etag"] = entity.etag
        info["synapse_concrete_type"] = type(entity).__name__

        info["synapse_creator_id"] = int(entity.created_by)
        info["synapse_modifier_id"] = int(entity.modified_by)

        # User profile lookups are expensive (extra API calls).
        # Only fetch when explicitly requested via detail=True kwarg.
        if kwargs.get("detail", False):
            creator = UserProfile.from_id(
                user_id=info["synapse_creator_id"],
                synapse_client=self.synapse,
            )
            info["synapse_creator_username"] = creator.username

            modifier = UserProfile.from_id(
                user_id=info["synapse_modifier_id"],
                synapse_client=self.synapse,
            )
            info["synapse_modifier_username"] = modifier.username
        else:
            info["synapse_creator_username"] = None
            info["synapse_modifier_username"] = None

        info["synapse_content_type"] = None
        info["synapse_content_md5"] = None
        info["synapse_version_label"] = None
        info["synapse_version_number"] = None

        if not is_dir:
            info["synapse_content_type"] = entity.file_handle.content_type
            info["synapse_content_md5"] = entity.file_handle.content_md5
            info["synapse_version_label"] = entity.version_label
            info["synapse_version_number"] = entity.version_number

        info["annotations"] = entity.annotations

        return info

    @overload
    def ls(self, path: str, detail: Literal[False] = ..., **kwargs: Any) -> list[str]:
        ...

    @overload
    def ls(
        self, path: str, detail: Literal[True] = ..., **kwargs: Any
    ) -> list[dict[str, Any]]:
        ...

    def ls(
        self, path: str, detail: bool = False, **kwargs: Any
    ) -> list[str] | list[dict[str, Any]]:
        """Get a list of the resources in a directory.

        Arguments:
            path: A path to a directory on the filesystem.
            detail: If True, return a list of info dicts. If False,
                return a list of full paths.

        Returns:
            List of paths (strings) or info dicts.

        Raises:
            NotADirectoryError: If ``path`` is not a directory.
            FileNotFoundError: If ``path`` does not exist.
        """
        path = self._strip_protocol(path)
        entity = self._path_to_entity(path)

        if not isinstance(entity, (Folder, Project)):
            synapse_id = entity.id
            type_ = type(entity)
            message = f"{synapse_id} ({type_}) is not a folder or project."
            raise NotADirectoryError(message)

        children = self._get_children(entity.id)

        if detail:
            result = []
            for child in children:
                child_path = f"{path}/{child['name']}" if path else child["name"]
                is_dir = child["type"] in (
                    "org.sagebionetworks.repo.model.Folder",
                    "org.sagebionetworks.repo.model.Project",
                )
                child_info: dict[str, Any] = {
                    "name": child_path,
                    "type": "directory" if is_dir else "file",
                }
                child_info["size"] = 0 if is_dir else None
                result.append(child_info)
            return result
        else:
            return [
                f"{path}/{child['name']}" if path else child["name"]
                for child in children
            ]

    def mkdir(
        self,
        path: str,
        create_parents: bool = True,
        exist_ok: bool = False,
        **kwargs: Any,
    ) -> None:
        """Make a directory.

        Arguments:
            path: Path to directory from root.
            create_parents: If True, create parent directories as needed.
            exist_ok: If True, do not raise an error if the directory
                already exists.

        Raises:
            FileExistsError: If the path already exists and exist_ok is False.
            FileNotFoundError: If the path is not found.
        """
        path = self._strip_protocol(path)

        if path == "":
            return

        posix_path = PurePosixPath(path)
        folder_name = str(posix_path.name)
        parent = self._path_to_parent_id(path)

        folder = Folder(
            name=folder_name,
            parent_id=parent,
            create_or_update=exist_ok or create_parents,
        )
        with synapse_errors(path):
            syn_store(folder, synapse_client=self.synapse)

    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        """Make directories recursively.

        Arguments:
            path: Path to directory from root.
            exist_ok: If True, do not raise an error if the directory
                already exists.
        """
        path = self._strip_protocol(path)

        if path == "":
            return

        parts = path.strip("/").split("/")

        # Determine the starting entity
        if self.root is not None:
            current_parent = self.root
            start_idx = 0
        elif self.is_synapse_id(parts[0]):
            current_parent = parts[0]
            start_idx = 1
        else:
            message = f"Path ({path}) must start with a Synapse ID when rootless."
            raise ValueError(message)

        for part in parts[start_idx:]:
            # Check if the child already exists
            children = self._get_children(current_parent)
            child_match = [c for c in children if c["name"] == part]
            if child_match:
                current_parent = child_match[0]["id"]
            else:
                folder = Folder(name=part, parent_id=current_parent)
                with synapse_errors(path):
                    folder = syn_store(folder, synapse_client=self.synapse)
                current_parent = folder.id

    def _open(self, path: str, mode: str = "rb", **kwargs: Any) -> RemoteFile:
        """Open a binary file-like object.

        Arguments:
            path: A path on the filesystem.
            mode: Mode to open file (defaults to 'rb').

        Returns:
            A file-like object.

        Raises:
            IsADirectoryError: If ``path`` exists and is a directory.
            FileExistsError: If the ``path`` exists and
                *exclusive mode* is specified (``x`` in the mode).
            FileNotFoundError: If ``path`` does not exist and
                ``mode`` does not imply creating the file.
        """
        path = self._strip_protocol(path)

        posix_path = PurePosixPath(path)
        file_name = str(posix_path.name)

        parsed = parse_mode(mode)
        reading = parsed.reading
        writing = parsed.writing
        appending = parsed.appending
        creating = parsed.creating
        exclusive = parsed.exclusive

        try:
            file_info = self.info(path)
            path_exists = True
            is_dir = file_info["type"] == "directory"
        except FileNotFoundError:
            path_exists = False
            is_dir = False

        if path_exists and is_dir:
            raise IsADirectoryError(path)

        if path_exists and exclusive:
            raise FileExistsError(path)

        if not path_exists:
            if creating:
                # Make sure the parent exists
                self._path_to_parent_id(path)
            else:
                raise FileNotFoundError(path)

        # Create temporary directory for housing files
        temp_dir = TemporaryDirectory()
        temp_path = temp_dir.name

        def on_close(remote_file: RemoteFile) -> None:
            """Called when the file closes, to upload data."""
            if creating or writing:
                pad_empty_file(remote_file)
            remote_file.raw.close()
            if creating or writing:
                parent = self._path_to_parent_id(path)
                new_file_path = rename_to_target(remote_file.raw.name, file_name)
                with synapse_errors(path):
                    file = File(path=str(new_file_path), parent_id=parent)
                    file = syn_store(file, synapse_client=self.synapse)
            temp_dir.cleanup()

        # Determine platform mode for the underlying file
        platform_mode = normalize_mode(mode)

        # The existing file should be downloaded first
        if path_exists and (reading or appending):
            entity = self._path_to_entity(path)
            with synapse_errors(path):
                entity = syn_get(
                    entity.id,
                    file_options=FileOptions(
                        download_file=True,
                        download_location=temp_path,
                    ),
                    synapse_client=self.synapse,
                )
            target_file = open(entity.path, platform_mode, -1)
        # Otherwise, any existing file will be ignored
        else:
            target_file = NamedTemporaryFile(
                platform_mode, -1, delete=False, dir=temp_path
            )

        # Set position of file descriptor based on the mode
        if appending:
            target_file.seek(0, os.SEEK_END)
        else:
            target_file.seek(0, os.SEEK_SET)

        return RemoteFile(target_file, strip_mode(mode), on_close)

    def rm_file(self, path: str) -> None:
        """Remove a file from the filesystem.

        Arguments:
            path: Path of the file to remove.

        Raises:
            IsADirectoryError: If the path is a directory.
            FileNotFoundError: If the path does not exist.
        """
        path = self._strip_protocol(path)
        entity = self._path_to_entity(path)

        if isinstance(entity, (Folder, Project)):
            synapse_id = entity.id
            type_ = type(entity)
            message = f"{synapse_id} ({type_}) is a folder or project."
            raise IsADirectoryError(message)

        syn_delete(entity, synapse_client=self.synapse)

    def rmdir(self, path: str) -> None:
        """Remove a directory from the filesystem.

        Arguments:
            path: Path of the directory to remove.

        Raises:
            OSError: If the directory is not empty.
            NotADirectoryError: If the path does not refer to a directory.
            FileNotFoundError: If no resource exists at the given path.
            PermissionError: If an attempt is made to remove the root.
        """
        path = self._strip_protocol(path)

        if path == "":
            message = "Cannot remove the root folder."
            raise PermissionError(message)

        entity = self._path_to_entity(path)

        if not isinstance(entity, (Folder, Project)):
            synapse_id = entity.id
            type_ = str(type(entity))
            message = f"{synapse_id} ({type_}) is not a folder or project."
            raise NotADirectoryError(message)

        children = self._get_children(entity.id)
        if len(children) > 0:
            type_name = "Folder" if isinstance(entity, Folder) else "Project"
            synapse_id = entity.id
            child_names = [c["name"] for c in children]
            message = f"{type_name} ({synapse_id}) is not empty ({child_names})."
            raise OSError(message)

        syn_delete(entity, synapse_client=self.synapse)

    def rm(
        self,
        path: str,
        recursive: bool = False,
        maxdepth: int | None = None,
    ) -> None:
        """Remove file(s) or directory.

        Arguments:
            path: Path to remove.
            recursive: If True, remove directories recursively.
            maxdepth: Maximum depth to recurse (unused, for API compat).
        """
        path = self._strip_protocol(path)
        entity = self._path_to_entity(path)

        if isinstance(entity, (Folder, Project)):
            if not recursive:
                # Check if empty
                children = self._get_children(entity.id)
                if len(children) > 0:
                    raise OSError(f"Directory not empty: {path}")
            syn_delete(entity, synapse_client=self.synapse)
        else:
            syn_delete(entity, synapse_client=self.synapse)

    def touch(self, path: str, truncate: bool = True, **kwargs: Any) -> None:
        """Create an empty file or update timestamp.

        Arguments:
            path: Path to the file.
            truncate: If True, truncate the file if it exists.
        """
        path = self._strip_protocol(path)

        try:
            self.info(path)
            exists = True
        except FileNotFoundError:
            exists = False

        if exists and not truncate:
            return

        # Write empty content (will become null byte due to Synapse restriction)
        self._open(path, "wb").close()
