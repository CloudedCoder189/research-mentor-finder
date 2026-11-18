"""Serialize private account changes across workers sharing one token directory."""
import asyncio
import hashlib
import os
import time
from contextlib import asynccontextmanager

from pathlib import Path
import database


@asynccontextmanager
async def account_lock(user_id):
    folder = Path(database.DB_PATH).parent / ".account_locks"
    folder.mkdir(parents=True, exist_ok=True)
    # One compact, 128-bit name avoids MAX_PATH failures in deep Windows
    # checkouts. Include the database identity to isolate adjacent test stores.
    identity = str(Path(database.DB_PATH).resolve()) + "\0" + user_id
    path = folder / (hashlib.sha256(identity.encode()).hexdigest()[:32] + ".lock")
    handle = path.open("a+b")
    locked = False
    try:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 30
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except (BlockingIOError, PermissionError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Account changes are busy; try again.") from None
                await asyncio.sleep(0.05)
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
