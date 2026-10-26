"""Helpers for files that hold secrets (keys, password hashes)."""
import os
from typing import Union


def private_dir(path: str) -> None:
    """Create `path` if needed and make it owner-only (0700)."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def write_private(path: str, data: Union[bytes, str]) -> None:
    """
    Atomically write `data` to `path` with owner-only permissions (0600).
    The file is created with that mode from the start, so it is never
    briefly readable by other users.
    """
    if isinstance(data, str):
        data = data.encode()
    tmp = f"{path}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def tighten(path: str, mode: int = 0o600) -> None:
    """Fix permissions of an existing file (e.g. one created by an older version)."""
    try:
        if os.path.exists(path):
            os.chmod(path, mode)
    except OSError:
        pass
