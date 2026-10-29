"""Process-owned paper runtime shared by server startup and Streamlit sessions."""
import atexit
import threading
from pathlib import Path
from .market import Hub
from .monitor import PaperMonitor
from .storage import Store

_lock = threading.RLock()
_hub = None
_monitors = {}


def hub():
    global _hub
    with _lock:
        if _hub is None:
            _hub = Hub()
        return _hub


def monitor(path):
    key = str(Path(path).expanduser().resolve())
    with _lock:
        current = _monitors.get(key)
        if current is None or not current.thread.is_alive():
            current = PaperMonitor(Store(key), hub())
            _monitors[key] = current
        return current


def start():
    from ..config import Settings
    return monitor(Settings.from_env().data_dir / 'crypto-v08.sqlite3')


def shutdown():
    global _hub
    with _lock:
        for current in _monitors.values():
            current.stop.set()
        for current in _monitors.values():
            current.thread.join(timeout=12)
        if _hub is not None:
            _hub.close()
        # Keep a worker which failed to stop registered; never replace it silently.
        for key in list(_monitors):
            if not _monitors[key].thread.is_alive():
                del _monitors[key]
        if not _monitors:
            _hub = None


atexit.register(shutdown)
