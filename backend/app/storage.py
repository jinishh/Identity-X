"""Write-once object store.

Submission build: files on disk, made read-only after write, overwrite refused in code.
Production: S3-compatible storage (SeaweedFS) with versioning + Object Lock (COMPLIANCE).
"""

from pathlib import Path


class WormViolation(Exception):
    pass


def put(directory: Path, key: str, data: bytes) -> None:
    path = directory / key
    if path.exists():
        raise WormViolation(f"object {key} already exists and is write-once")
    path.write_bytes(data)
    path.chmod(0o444)


def get(directory: Path, key: str) -> bytes:
    return (directory / key).read_bytes()


def exists(directory: Path, key: str) -> bool:
    return (directory / key).exists()


def is_locked(directory: Path, key: str) -> bool:
    path = directory / key
    return path.exists() and not (path.stat().st_mode & 0o222)
