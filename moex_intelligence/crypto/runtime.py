"""Single-process owner for local Paper protection.

The advisory OS lock is deliberately tied to the SQLite path: two independent
Streamlit/launcher processes must never both run protective workers on a ledger.
This is a LOCAL PAPER safety boundary, not an exchange order guarantee.
"""
import atexit
import errno
import fcntl  # macOS and Linux, the supported local runtime platforms
import os
import threading
from pathlib import Path

from .market import Hub
from .monitor import PaperMonitor
from .storage import Store

_lock = threading.RLock()
_hub = None
_monitors = {}
_owners = {}


def hub():
    global _hub
    with _lock:
        if _hub is None:
            _hub = Hub()
        return _hub


def _claim(key):
    """Keep the descriptor open while protection is owned; never steal a lock."""
    path = Path(key + '.monitor.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EAGAIN, errno.EACCES):
            raise RuntimeError('Другой экземпляр CandlePath уже управляет Paper-базой. Закройте его перед запуском второго.') from exc
        raise
    return fd


def _release(key):
    fd = _owners.pop(key, None)
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def monitor(path):
    key = str(Path(path).expanduser().resolve())
    with _lock:
        current = _monitors.get(key)
        if current is not None and current.thread.is_alive():
            return current
        if current is not None:
            _monitors.pop(key)
            _release(key)
        fd = _claim(key)
        _owners[key] = fd
        try:
            current = PaperMonitor(Store(key), hub())
        except BaseException:
            _release(key)
            raise
        _monitors[key] = current
        return current


def start():
    from ..config import Settings
    return monitor(Settings.from_env().data_dir / 'crypto-v08.sqlite3')


def shutdown():
    """Never release process ownership while a protective worker is still alive."""
    global _hub
    with _lock:
        for current in _monitors.values():
            current.stop.set()
        for current in _monitors.values():
            if current.thread is not threading.current_thread():
                current.thread.join(timeout=12)
        for key, current in list(_monitors.items()):
            if not current.thread.is_alive():
                del _monitors[key]
                _release(key)
        if not _monitors:
            if _hub is not None:
                _hub.close()
            _hub = None


atexit.register(shutdown)
