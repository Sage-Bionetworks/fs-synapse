# fs-synapse

<!--
[![ReadTheDocs](https://readthedocs.org/projects/fs-synapse/badge/?version=latest)](https://sage-bionetworks-workflows.github.io/fs-synapse/)
[![PyPI-Server](https://img.shields.io/pypi/v/fs-synapse.svg)](https://pypi.org/project/fs-synapse/)
[![codecov](https://codecov.io/gh/Sage-Bionetworks-Workflows/fs-synapse/branch/main/graph/badge.svg?token=OCC4MOUG5P)](https://codecov.io/gh/Sage-Bionetworks-Workflows/fs-synapse)
[![Project generated with PyScaffold](https://img.shields.io/badge/-PyScaffold-005CA0?logo=pyscaffold)](#pyscaffold)
-->

> A Synapse implementation of the [fsspec](https://filesystem-spec.readthedocs.io/) interface.

`fs-synapse` allows us to leverage the [fsspec API](https://filesystem-spec.readthedocs.io/en/latest/api.html) to interface with Synapse files, folders, and projects. By learning this API, you can write code that is agnostic to where your files are physically located. This is achieved by referring to Synapse entities using URLs. Commented examples are included below.

```
syn://syn50545516               # Synapse project

syn://syn50557597               # Folder in the above Synapse project
syn://syn50545516/syn50557597   # Same folder, but using a full path
syn://syn50545516/TestSubDir    # Same folder, but referenced by name

syn://syn50555279               # File in the above Synapse project
syn://syn50545516/syn50555279   # Same file, but using a full path
syn://syn50545516/test.txt      # Same file, but referenced by name

syn://syn50545516/ExploratoryTests/report.json      # Nested file
```

## Benefits

There are several benefits to using the `fs-synapse` API over `synapseclient`.

```python
from synapsefs import SynapseFS

fs = SynapseFS()

# Or using fsspec directly
import fsspec
fs = fsspec.filesystem("syn")
```

### Interact with Synapse using a Pythonic interface

```python
file_url = "syn://syn50555279"

with fs.open(file_url, "a") as fp:
    fp.write("Appending some text to a Synapse file")
```

### Access to several convenience functions

```python
folder_url = "syn://syn50696438"

fs.makedirs(f"{folder_url}/creating/nested/folders/with/one/operation")
```

### Refer to Synapse files and folders by name

You don't have to track as many Synapse IDs. You only need to care about the top-level projects or folders and refer to subfolders and files by name.

```python
project_url = "syn://syn50545516"

data_url = f"{project_url}/data/raw.csv"
output_url = f"{project_url}/outputs/processed.csv"

with fs.open(data_url, "r") as data_fp, fs.open(output_url, "a") as output_fp:
    results = number_cruncher(data)
    output.write(results)
```

### Write Synapse-agnostic code

Unfortunately, every time you use `synapseclient` for file and folder operations, you are hard-coding a dependency on Synapse into your project. Leveraging `fs-synapse` helps avoid this hard dependency and makes your code more portable to other file backends (_e.g._ S3). You can swap for any other file system by using their URL scheme (_e.g._ `s3://`). Here's [an index](https://filesystem-spec.readthedocs.io/en/latest/api.html#built-in-implementations) of available file systems that you can swap for.

### Rely on code covered by integration tests

So you don't have to write the Synapse integration tests yourself! These tests tend to be slow, so delegating that responsibilty to an externally managed package like `fs-synapse` keeps your test suite fast and focused on what you care about.

In your test code, you can use the [memory filesystem](https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.implementations.memory.MemoryFileSystem) for faster I/O instead of storing and retrieving files on Synapse.

```python
def test_some_feature_of_your_code():
    fs = fsspec.filesystem("memory")
    cruncher = NumberCruncher(fs=fs)
    cruncher.save("report.json")
    assert fs.exists("report.json")
```

## Migration from PyFilesystem2 to fsspec

This package previously used [PyFilesystem2](http://docs.pyfilesystem.org/) (`fs`) as its base. It now uses [fsspec](https://filesystem-spec.readthedocs.io/). The table below maps the old API to the new one.

### Initialization

| Old (PyFilesystem2) | New (fsspec) |
| --- | --- |
| `from fs import open_fs` | `import fsspec` |
| `fs = open_fs("syn://")` | `fs = fsspec.filesystem("syn")` |
| `fs = open_fs("syn://syn50545516")` | `fs = SynapseFS(root="syn50545516")` |

### File operations

| Old (PyFilesystem2) | New (fsspec) |
| --- | --- |
| `fs.open(path, "r")` | `fs.open(path, "r")` |
| `fs.readtext(path)` | `fs.cat_file(path).decode()` |
| `fs.readbytes(path)` | `fs.cat_file(path)` |
| `fs.writetext(path, text)` | `fs.pipe_file(path, text.encode())` |
| `fs.writebytes(path, data)` | `fs.pipe_file(path, data)` |
| `fs.create(path)` / `fs.touch(path)` | `fs.touch(path)` |
| `fs.download(name, file_obj)` | `fs.get(path, local_path)` |

### Directory operations

| Old (PyFilesystem2) | New (fsspec) |
| --- | --- |
| `fs.listdir(path)` | `fs.ls(path, detail=False)` (returns full paths) |
| `fs.makedir(path)` | `fs.mkdir(path)` |
| `fs.makedirs(path)` | `fs.makedirs(path)` |
| `fs.opendir(path)` | _(no equivalent; use full paths)_ |
| `fs.tree(path=path)` | `fs.ls(path, detail=True)` |

### Removal

| Old (PyFilesystem2) | New (fsspec) |
| --- | --- |
| `fs.remove(path)` | `fs.rm(path)` |
| `fs.removedir(path)` | `fs.rmdir(path)` |
| `fs.removetree(path)` | `fs.rm(path, recursive=True)` |

### Info and metadata

| Old (PyFilesystem2) | New (fsspec) |
| --- | --- |
| `info = fs.getinfo(path, namespaces=["details", "synapse"])` | `info = fs.info(path)` |
| `info.name` | `info["name"]` |
| `info.is_dir` | `info["type"] == "directory"` |
| `info.get("details", "size")` | `info["size"]` |
| `info.get("synapse", "id")` | `info["synapse_id"]` |
| `info.get("synapse", "content_type")` | `info["synapse_content_type"]` |
| `info.get("synapse", "etag")` | `info["synapse_etag"]` |
| `fs.getsize(path)` | `fs.info(path)["size"]` |
| `fs.gettype(path)` | `fs.info(path)["type"]` |
| `fs.exists(path)` | `fs.exists(path)` |

### Errors

| Old (PyFilesystem2) | New (fsspec) |
| --- | --- |
| `fs.errors.ResourceNotFound` | `FileNotFoundError` |
| `fs.errors.FileExists` / `DirectoryExists` | `FileExistsError` |
| `fs.errors.FileExpected` | `IsADirectoryError` |
| `fs.errors.DirectoryExpected` | `NotADirectoryError` |
| `fs.errors.CreateFailed` | `ValueError` |
| `fs.errors.ResourceInvalid` | `ValueError` |
| `fs.errors.RemoveRootError` | `PermissionError` |
| `fs.errors.DirectoryNotEmpty` | `OSError` |

## PyScaffold

This project has been set up using PyScaffold 4.3. For details and usage
information on PyScaffold see [PyScaffold](https://pyscaffold.org/).

```console
putup --name fs-synapse --markdown --github-actions --pre-commit --license Apache-2.0 fs-synapse
```
