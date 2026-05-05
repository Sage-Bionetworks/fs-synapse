from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import IO, NamedTuple

NULL_BYTE = b"\x00"


class ParsedMode(NamedTuple):
    """Parsed file mode flags."""

    reading: bool
    writing: bool
    appending: bool
    creating: bool
    exclusive: bool


def parse_mode(mode: str) -> ParsedMode:
    """Parse a file mode string into boolean flags.

    Args:
        mode: A file mode string (e.g. "rb", "w", "a+b").

    Returns:
        A ParsedMode with boolean flags for each mode category.
    """
    mode_str = mode.replace("b", "").replace("t", "")
    write_chars = {"w", "a", "+", "x"}
    create_chars = {"w", "a", "x"}
    mode_set = set(mode_str)
    return ParsedMode(
        reading="r" in mode_set or "+" in mode_set,
        writing=bool(mode_set & write_chars),
        appending="a" in mode_set,
        creating=bool(mode_set & create_chars),
        exclusive="x" in mode_set,
    )


def strip_mode(mode: str) -> str:
    """Strip 'b' and 't' modifiers from a mode string.

    Args:
        mode: A file mode string (e.g. "rb", "wt", "a+b").

    Returns:
        The mode string without encoding modifiers (e.g. "r", "w", "a+").
    """
    return mode.replace("b", "").replace("t", "")


def normalize_mode(mode: str) -> str:
    """Normalize a mode string to binary form (strip 'b'/'t', then append 'b').

    Args:
        mode: A file mode string (e.g. "rb", "wt", "a+").

    Returns:
        The normalized binary mode string (e.g. "rb", "wb", "a+b").
    """
    return strip_mode(mode) + "b"


def pad_empty_file(file: IO[bytes]) -> None:
    """Write a null byte if the file is empty.

    Synapse rejects truly empty files, so a null byte is used as a placeholder.

    Args:
        file: A writable binary file-like object.
    """
    file.seek(0, os.SEEK_END)
    if file.tell() == 0:
        file.write(NULL_BYTE)


def rename_to_target(source: str, target_name: str) -> Path:
    """Rename a file to the target name within the same directory.

    Args:
        source: Path to the source file.
        target_name: The desired filename.

    Returns:
        The new file path.
    """
    old_path = Path(source)
    new_path = old_path.parent / target_name
    shutil.move(old_path, new_path)
    return new_path
