import importlib

m = importlib.import_module('s_mapper')


class DummyEvent:
    def __init__(self):
        self._type = None

    def type(self):
        # Simulate a WindowStateChange event
        return m.QEvent.Type.WindowStateChange


class DummyWindow:
    def __init__(self, tray_available=True, tray_visible=True):
        self._hidden = False
        self._minimized = True
        self._tray_available = tray_available
        # mimic a tray icon object
        class Tray:
            def __init__(self, visible=True):
                self._visible = visible

            def isVisible(self):
                return self._visible

            def showMessage(self, *a, **k):
                # succeed silently
                return True

        if tray_available:
            self.tray_icon = Tray(tray_visible)
        else:
            # When tray is unavailable, the attribute may be absent or non-functional
            self.tray_icon = None

    def isMinimized(self):
        return self._minimized

    def hide(self):
        self._hidden = True


def test_change_event_does_not_hide_when_tray_unavailable():
    obj = DummyWindow(tray_available=False)

    # Bind and call method
    change = m.KeyMapperApp.changeEvent.__get__(obj, m.KeyMapperApp)
    ev = DummyEvent()
    change(ev)

    # If tray is not available, app should not hide on minimize
    assert getattr(obj, '_hidden', False) is False


def test_change_event_hides_when_tray_available():
    obj = DummyWindow(tray_available=True, tray_visible=True)

    change = m.KeyMapperApp.changeEvent.__get__(obj, m.KeyMapperApp)
    ev = DummyEvent()
    change(ev)

    assert obj._hidden is True
