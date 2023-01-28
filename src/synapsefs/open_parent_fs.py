from fs import open_fs
from fs.base import FS


# TODO: Switch to using parse_fs_url() and register.open()
#       https://github.com/PyFilesystem/pyfilesystem2/pull/561#issuecomment-1407436951
def open_parent_fs(url: str) -> tuple[FS, str]:
    # Split off prefix to avoid issues with `rpartition("/")`
    scheme, separator, resource = url.rpartition("://")
    if separator == "":
        prefix = "osfs://"
    else:
        prefix = scheme + separator

    # Retrieve the "top-most" parent folder for the FS root
    # to ensure that it exists for the FS to be constructed.
    # The remainder of the string can be used as the FS path
    fs_root, _, path = resource.partition("/")

    # Handle the case when the path starts with "/"
    if fs_root == "":
        fs_root = "/"

    # Handle the case when there is no "/" in the path
    if path == "":
        path = fs_root
        fs_root = ""

    fs_url = prefix + fs_root
    fs = open_fs(fs_url)
    return fs, path
