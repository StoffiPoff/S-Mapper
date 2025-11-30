#!/usr/bin/env python3
"""Convenience runner for S-Mapper during development.

This script executes the package entrypoint module so you can run the
application with a single command from the repository root:

    python run_app.py

It forwards execution to `s_mapper.app` (same behaviour as
`python -m s_mapper.app`) and avoids duplicating startup logic.
"""
import runpy
import os
import sys
from pathlib import Path

def ensure_repo_on_syspath():
    """Ensure the repository root (runner location) is on sys.path.

    Returns the repository root path (as str) that was inserted or already
    present. Returns None on error.

    The function is intentionally module-level so tests can import it and
    verify behaviour without executing the runner's main code path.
    """
    try:
        root = Path(__file__).resolve().parent
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        return root_str
    except Exception:
        return None


# PyInstaller static analysis hint -------------------------------------------------
# PyInstaller uses static analysis to discover imports. When the runner uses
# runpy.run_module('s_mapper.app') the analyzer may not detect the package's
# modules. Provide a harmless, guarded import so PyInstaller sees the module
# and includes the full package (no runtime effect because the block never
# executes).
if False:  # pragma: no cover - static import for PyInstaller analysis
    # The import is intentionally unreachable but ensures the analyzer picks
    # up the s_mapper package and submodules (including PyQt hooks).
    import s_mapper.app  # type: ignore

# Ensure repository path is discoverable first and then run the package
# entrypoint as if executed with -m so the module-level __main__ in
# s_mapper.app runs.
ensure_repo_on_syspath()
try:
    runpy.run_module('s_mapper.app', run_name='__main__')
except Exception as exc:  # pragma: no cover - hard to reproduce here
    # write traceback to the local app error logfile so users running the
    # packaged exe get a place to look for details
    import traceback
    try:
        log_dir = Path(__file__).resolve().parent
        # Use LOCALAPPDATA path if available, otherwise write next to runner
        appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser(r"~\AppData\Local")
        err_path = os.path.join(appdata, 'S-Mapper', 'error.log')
        os.makedirs(os.path.dirname(err_path), exist_ok=True)
        with open(err_path, 'a', encoding='utf8') as fh:
            fh.write(traceback.format_exc())
    except Exception:
        # last resort: print to stderr so console builds show the error
        print('Error during startup:')
        traceback.print_exc()
    # Re-raise so process still terminates with non-zero exit code.
    raise
