"""Linux file primitives for durable local JSON state."""

from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile


@contextmanager
def exclusive_state_lock(path: str | Path) -> Iterator[None]:
    """Serialize one local read-modify-write operation for ``path``."""

    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_name(f"{state_path.name}.lock")
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: str | Path, content: str) -> None:
    """Durably replace ``path`` without exposing a partial target file."""

    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{state_path.name}.",
        suffix=".tmp",
        dir=state_path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, state_path)
        directory_descriptor = os.open(state_path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
