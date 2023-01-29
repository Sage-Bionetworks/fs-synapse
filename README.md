# fs-synapse

<!--
[![ReadTheDocs](https://readthedocs.org/projects/fs-synapse/badge/?version=latest)](https://sage-bionetworks-workflows.github.io/fs-synapse/)
[![PyPI-Server](https://img.shields.io/pypi/v/fs-synapse.svg)](https://pypi.org/project/fs-synapse/)
[![codecov](https://codecov.io/gh/Sage-Bionetworks-Workflows/fs-synapse/branch/main/graph/badge.svg?token=OCC4MOUG5P)](https://codecov.io/gh/Sage-Bionetworks-Workflows/fs-synapse)
[![Project generated with PyScaffold](https://img.shields.io/badge/-PyScaffold-005CA0?logo=pyscaffold)](#pyscaffold)
-->

> A Synapse implementation of the [PyFileSystem2](http://docs.pyfilesystem.org/) interface.

`fs-synapse` allows us to leverage the [PyFileSystem API](https://docs.pyfilesystem.org/en/latest/interface.html) to interface with Synapse files, folders, and projects. By learning this API, you can write code that is agnostic to where your files are physically located. This is achieved by referring to Synapse entities using URLs. Commented examples are included below, but more details can be found [here](https://docs.pyfilesystem.org/en/latest/openers.html).

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
from fs import open_fs

fs = open_fs("syn://")
```

### Interact with Synapse using a Pythonic interface

This [guide](https://docs.pyfilesystem.org/en/latest/guide.html) provides several code examples for various use cases.

```python
file_url = "syn://syn50555279"

with fs.open(file_url, "a") as fp:
    fp.write("Appending some text to a Synapse file")
```

### Access to several convenience functions

The full list of available functions are listed [here](https://docs.pyfilesystem.org/en/latest/interface.html).

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

Unfortunately, every time you use `synapseclient` for file and folder operations, you are hard-coding a dependency on Synapse into your project. Leveraging `fs-synapse` helps avoid this hard dependency and makes your code more portable to other file backends (_e.g._ S3). You can swap for any other file system by using their URL scheme (_e.g._ `s3://`). Here's [an index](https://www.pyfilesystem.org/page/index-of-filesystems/) of available file systems that you can swap for.

### Rely on code covered by integration tests

So you don't have to write the Synapse integration tests yourself! These tests tend to be slow, so delegating that responsibilty to an externally managed package like `fs-synapse` keeps your test suite fast and focused on what you care about.

In your test code, you can use `mem://` or `temp://` URLs for faster I/O instead of storing and retrieving files on Synapse ([MemoryFS](https://docs.pyfilesystem.org/en/latest/reference/memoryfs.html) and [TempFS](https://docs.pyfilesystem.org/en/latest/reference/tempfs.html)).

```python
def test_some_feature_of_your_code():
    output_url = "mem://report.json"
    cruncher = NumberCruncher()
    cruncher.save(output_url)
    assert cruncher.fs.exists(output_url)
```

# PyScaffold

This project has been set up using PyScaffold 4.3. For details and usage
information on PyScaffold see https://pyscaffold.org/.

```console
putup --name fs-synapse --markdown --github-actions --pre-commit --license Apache-2.0 fs-synapse
```
