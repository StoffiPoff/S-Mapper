import sys
import os
import logging


from PyQt6.QtWidgets import (
    QApplication
)
try:
    import pygetwindow as gw
except Exception:
    # When running tests or in stripped environments the optional
    # pygetwindow package may not be present. Provide a small shim so
    # the rest of the module can import and tests can run without
    # importing the optional dependency.
    class _GWStub:
        @staticmethod
        def getActiveWindow():
            return None

        @staticmethod
        def getWindowsWithTitle(title):
            return []

    gw = _GWStub()

# reorganized submodules
from .utils import (
    get_log_filepath
)

# Optional low-level keyboard interception via the 'keyboard' package.
# We import lazily and safely since the user may not have it installed.
try:
    import keyboard as kbd  # type: ignore
    _KBD_AVAILABLE = True
except Exception:
    kbd = None
    _KBD_AVAILABLE = False


# _check_admin_windows moved to s_mapper.utils


# NOTE: This project targets Windows only. UNIX-specific elevation
# checks have been removed to simplify the runtime and avoid
# unnecessary platform branching.


# is_running_as_admin moved to s_mapper.utils

# resource_path moved to s_mapper.utils


# get_log_filepath and parse_ping_output moved to s_mapper.utils

# HelpWindow moved to s_mapper.widgets

# KeyboardListenerThread moved to s_mapper.threads


# ActiveWindowEventThread moved to s_mapper.threads

# MouseListenerThread moved to s_mapper.threads

# PingStatusLabel moved to s_mapper.widgets

from .ui import KeyMapperApp

# app.py is intentionally a thin entrypoint for the package. The
# heavy UI implementation lives in s_mapper.ui so tests and callers
# can continue to import KeyMapperApp from s_mapper.app (backwards
# compatibility).

__all__ = ["KeyMapperApp"]

if __name__ == "__main__":
    # Configure console logging for INFO and up
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Configure file logging for ERROR and up
    log_file_path = get_log_filepath()
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.ERROR)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logging.getLogger('').addHandler(file_handler)

    # Enable High-DPI scaling before creating the QApplication
    # This is the most reliable method across Qt versions
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    ex = KeyMapperApp()
    ex.show()
    sys.exit(app.exec())
