import os
import sys
import re


def _check_admin_windows() -> bool:
    """Return True if the current process is running elevated (Windows).

    This uses ctypes.windll.shell32.IsUserAnAdmin which returns a non-zero
    value when running elevated. Wrap in try/except to avoid import-time
    errors in environments where ctypes/win32 APIs are restricted.
    """
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_running_as_admin() -> bool:
    """Return True when the current process is running elevated (Windows).

    Prefer a top-level override if present so tests and callers can patch
    the behaviour on the `s_mapper` module. Fall back to the local
    implementation otherwise.
    """
    try:
        import sys as _sys
        m = _sys.modules.get('s_mapper')
        if m and hasattr(m, '_check_admin_windows'):
            return bool(getattr(m, '_check_admin_windows')())
    except Exception:
        pass

    return _check_admin_windows()


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller.

    This helper searches a few directories up from the module location
    so tests and development runs find assets in repo / package layouts.
    """
    base_path = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))

    candidate = os.path.join(base_path, relative_path)
    if os.path.exists(candidate):
        return candidate

    p = base_path
    for _ in range(4):
        p = os.path.dirname(p)
        candidate = os.path.join(p, relative_path)
        if os.path.exists(candidate):
            return candidate

    return os.path.join(base_path, relative_path)


def get_log_filepath():
    """Returns the platform-specific, user-writable path for the error.log file."""
    app_data_path = os.environ.get('LOCALAPPDATA') or os.path.expanduser(r"~\AppData\Local")
    try:
        log_dir = os.path.join(app_data_path, 'S-Mapper')
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, 'error.log')
    except Exception:
        return 'error.log'


def parse_ping_output(output: str):
    """Parse ping command output and return (lost_pct, color).

    lost_pct: int or None - percentage of lost packets if determined
    color: 'green' or 'red'
    """
    out = (output or '').lower()

    lost_pct = None
    m = re.search(r"(\d+)%.*loss", out)
    if m:
        try:
            lost_pct = int(m.group(1))
        except Exception:
            lost_pct = None
    else:
        m2 = re.search(r"lost\s*=\s*(\d+)", out)
        if m2:
            try:
                lost = int(m2.group(1))
                lost_pct = 100 if lost > 0 else 0
            except Exception:
                lost_pct = None
        elif re.search(r"received\s*=\s*0|\b0\s+received\b", out):
            lost_pct = 100

    color = 'red' if (lost_pct is not None and lost_pct >= 100) else 'green'
    return lost_pct, color
