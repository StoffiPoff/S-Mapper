"""s_mapper package compatibility shim

This package exposes the same public symbols that used to exist in the
single-file `s_mapper.py` module so existing code/tests can continue to
`import s_mapper` or `from s_mapper import KeyMapperApp` unchanged.

During the refactor the original large script was moved to
`s_mapper.app` and kept intact. Gradually other submodules will be split
out from `app.py` over time.
"""

from importlib import import_module as _import
import sys as _sys

# IMPORTANT: avoid importing s_mapper.app at package import-time. Running
# the package with `python -m s_mapper.app` triggers import machinery that
# first imports the package `s_mapper` and then executes `s_mapper.app`.
# If __init__ imports s_mapper.app eagerly it ends up preloading the module
# in sys.modules and runpy will warn about the module being present during
# execution. Use lazy loading to prevent that.

def _ensure_app():
    """Attempt to import s_mapper.app on demand and return it or None."""
    try:
        return _import("s_mapper.app")
    except Exception:
        return None


def __getattr__(name: str):
    """Provide lazy attribute access for names that live in s_mapper.app.

    This keeps old callers/tests that expect `from s_mapper import KeyMapperApp`
    working while avoiding eager import of the app module.
    """
    # Prefer explicit globals defined in this shim first
    if name in globals():
        return globals()[name]

    app = _ensure_app()
    if app and hasattr(app, name):
        val = getattr(app, name)
        # cache for faster future access
        globals()[name] = val
        return val

    raise AttributeError(f"module {__name__} has no attribute {name!r}")


def __dir__():
    names = set(globals().keys())
    app = _ensure_app()
    if app:
        names.update(n for n in dir(app) if not n.startswith("_"))
    return sorted(names)

# Also expose some common helpers which now live in utils so tests can
# still import them from `s_mapper` directly (backwards compat).
try:
    from .utils import parse_ping_output  # re-export at package level
    globals()['parse_ping_output'] = parse_ping_output
except Exception:
    pass

# Also re-export a handful of common helpers and Qt symbols at the package
# level so tests (and older callers) can monkeypatch them on `s_mapper`.
try:
    from .utils import _check_admin_windows, resource_path, is_running_as_admin
    globals().update({
        '_check_admin_windows': _check_admin_windows,
        'resource_path': resource_path,
        'is_running_as_admin': is_running_as_admin,
    })
except Exception:
    pass

try:
    from .threads import PingThread
    globals()['PingThread'] = PingThread
except Exception:
    pass

try:
    # Some tests expect Qt classes to be available as top-level symbols; re-export
    # the ones commonly referenced so monkeypatching works.
    from PyQt6.QtWidgets import QMessageBox
    from PyQt6.QtCore import QEvent
    globals()['QMessageBox'] = QMessageBox
    globals()['QEvent'] = QEvent
except Exception:
    # If Qt isn't importable in an environment, don't fail package import.
    pass


# Lightweight proxy used when tests monkeypatch module-level symbols
# on the top-level package. The proxy resolves the current object from
# the top-level module at call/attribute time so changes in the test
# module are reflected in the app module at runtime.
class _ProxyCallable:
    def __init__(self, target_name):
        self._target_name = target_name

    def __call__(self, *args, **kwargs):
        target = getattr(_sys.modules['s_mapper'], self._target_name)
        return target(*args, **kwargs)

    def __getattr__(self, name):
        target = getattr(_sys.modules['s_mapper'], self._target_name)
        return getattr(target, name)


# Provide proxies inside the app module for names that tests commonly
# patch so monkeypatching the top-level package affects runtime code.
# Ensure common names that tests monkeypatch on the top-level package are
# proxied into the main submodules as well. Tests often replace symbols on
# the s_mapper package and expect the runtime code in s_mapper.app, s_mapper.ui
# and other submodules to pick up the patched values.
for _patch_name in ('QMessageBox', 'PingThread', '_check_admin_windows'):
    # Do NOT import s_mapper.app here – that would pre-load the app module and
    # reintroduce the runpy warning when executing `python -m s_mapper.app`.
    for _mod_name in ('s_mapper.ui', 's_mapper.threads', 's_mapper.widgets'):
        try:
            _mod = _import(_mod_name)
            setattr(_mod, _patch_name, _ProxyCallable(_patch_name))
        except Exception:
            # Not all submodules exist or may be importable in some environments;
            # ignore failures so package import remains robust.
            pass

__all__ = [
    name for name in globals().keys() if not name.startswith('_')
]
