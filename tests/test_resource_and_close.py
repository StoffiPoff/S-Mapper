import importlib
import os

m = importlib.import_module('s_mapper')


def test_resource_path_resolves_to_module_dir():
    # The app bundles icons inside the 'assets' folder; make sure our helper
    # resolves an assets path correctly during development.
    rel = os.path.join('assets', 'Square44x44Logo.png')
    res = m.resource_path(rel)
    expected = os.path.join(os.path.dirname(m.__file__), rel)
    assert os.path.isabs(res)
    assert os.path.normcase(res) == os.path.normcase(expected)
    # the icon exists in the repo as a basic sanity check
    assert os.path.exists(res)


class DummyThread:
    def __init__(self):
        self.stopped = False
        self.waited_with = None

    def stop(self):
        self.stopped = True

    def wait(self, timeout=None):
        # emulate behavior of QThread.wait: return True/False optionally
        self.waited_with = timeout
        return True


class DummyTimer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class DummyTray:
    def __init__(self):
        self.hidden = False

    def hide(self):
        self.hidden = True


class DummyEvent:
    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


def test_close_event_waits_on_threads(monkeypatch):
    # Build a fake object with the attributes closeEvent expects
    obj = type('O', (), {})()
    obj.save_mappings_to_config = lambda: None
    obj.save_macros_to_config = lambda: None
    obj.keyboard_thread = DummyThread()
    obj.mouse_thread = DummyThread()
    obj.macro_thread = DummyThread()
    obj._macro_recorder = DummyThread()
    obj._active_title_timer = DummyTimer()
    obj._unhook_all_keyboard_hooks = lambda : None
    obj.tray_icon = DummyTray()

    # Bind the class method to the instance and call it with a dummy event
    close = m.KeyMapperApp.closeEvent.__get__(obj, m.KeyMapperApp)
    ev = DummyEvent()
    close(ev)

    # Ensure we called stop() on threads and that wait was invoked
    assert obj.keyboard_thread.stopped is True
    assert obj.keyboard_thread.waited_with is not None
    assert obj.mouse_thread.stopped is True
    assert obj.mouse_thread.waited_with is not None
    assert obj.macro_thread.waited_with is not None
    assert obj._macro_recorder.waited_with is not None
    assert obj._active_title_timer.stopped is True
    assert obj.tray_icon.hidden is True
    assert ev.accepted is True
