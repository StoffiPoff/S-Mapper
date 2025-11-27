import importlib

m = importlib.import_module('s_mapper')


class DummyCheckbox:
    def __init__(self):
        self.checked = False
    def setChecked(self, val):
        self.checked = bool(val)


class DummyLabel:
    def __init__(self):
        self.text = ''
        self.style = ''
    def setText(self, t):
        self.text = t
    def setStyleSheet(self, s):
        self.style = s


def test_enable_keyboard_fails_shows_warning(monkeypatch):
    obj = type('O', (), {})()
    # Set up fields used by the method
    obj._kbd_available = True
    obj._is_admin = False
    obj.kbd_suppression_checkbox = DummyCheckbox()
    obj.kbd_status_label = DummyLabel()

    # Make refresh raise so enabling fails
    def failing_refresh():
        raise RuntimeError('permission denied')

    obj._refresh_keyboard_hooks = failing_refresh
    obj._unhook_all_keyboard_hooks = lambda : None

    calls = []
    def fake_warning(self, title, message):
        calls.append((title, message))

    monkeypatch.setattr(m.QMessageBox, 'warning', fake_warning)

    # Bind and call toggle method
    toggle = m.KeyMapperApp._on_kbd_suppression_toggled.__get__(obj, m.KeyMapperApp)
    toggle(True)

    # Should have attempted enabling and failed -> show warning, checkbox false
    assert len(calls) == 1
    assert 'Failed to enable low-level suppression' in calls[0][1]
    assert obj._kbd_enabled is False
    assert obj.kbd_suppression_checkbox.checked is False
    assert 'failed' in obj.kbd_status_label.text.lower()


def test_disable_unhooks_and_status(monkeypatch):
    obj = type('O', (), {})()
    obj._kbd_available = True
    obj._is_admin = True
    obj._kbd_enabled = True
    obj.kbd_suppression_checkbox = DummyCheckbox()
    obj.kbd_status_label = DummyLabel()

    unhooked = {'called': False}
    def unhook_all():
        unhooked['called'] = True

    obj._unhook_all_keyboard_hooks = unhook_all

    toggle = m.KeyMapperApp._on_kbd_suppression_toggled.__get__(obj, m.KeyMapperApp)
    toggle(False)

    assert unhooked['called'] is True
    assert obj._kbd_enabled is False
    assert 'disabled' in obj.kbd_status_label.text.lower()


def test_disable_while_not_admin(monkeypatch):
    # Ensure disabling works when we are not elevated - UI should still allow it
    obj = type('O', (), {})()
    obj._kbd_available = True
    obj._is_admin = False
    obj._kbd_enabled = True
    obj.kbd_suppression_checkbox = DummyCheckbox()
    obj.kbd_status_label = DummyLabel()

    unhooked = {'called': False}
    def unhook_all():
        unhooked['called'] = True

    obj._unhook_all_keyboard_hooks = unhook_all

    toggle = m.KeyMapperApp._on_kbd_suppression_toggled.__get__(obj, m.KeyMapperApp)
    toggle(False)

    assert unhooked['called'] is True
    assert obj._kbd_enabled is False
    assert 'disabled' in obj.kbd_status_label.text.lower()
