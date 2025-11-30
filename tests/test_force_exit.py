import importlib
import os

m = importlib.import_module('s_mapper')


class DummyEvent:
    def accept(self):
        pass


def test_close_event_without_force(tmp_path, monkeypatch):
    # Ensure default behavior does not call os._exit
    called = {'exit': False}

    def fake_exit(code=0):
        called['exit'] = True

    monkeypatch.setenv('S_MAPPER_FORCE_EXIT_ON_CLOSE', '0')
    monkeypatch.setattr(os, '_exit', fake_exit)

    obj = type('O', (), {})()
    # Minimal attributes used by closeEvent
    obj.save_mappings_to_config = lambda: None
    obj.keyboard_thread = type('T', (), {'stop': lambda s: None, 'wait': lambda s, t=None: True})()
    obj.mouse_thread = type('T', (), {'stop': lambda s: None, 'wait': lambda s, t=None: True})()
    obj._active_title_timer = type('T', (), {'stop': lambda s: None})()
    obj._unhook_all_keyboard_hooks = lambda : None
    obj.tray_icon = type('T', (), {'hide': lambda s: None})()

    close = m.KeyMapperApp.closeEvent.__get__(obj, m.KeyMapperApp)
    close(DummyEvent())

    assert called['exit'] is False


def test_close_event_with_force(monkeypatch):
    # When env var is set to true, os._exit should be called
    called = {'exit': False}

    def fake_exit(code=0):
        called['exit'] = True

    monkeypatch.setenv('S_MAPPER_FORCE_EXIT_ON_CLOSE', '1')
    monkeypatch.setattr(os, '_exit', fake_exit)

    obj = type('O', (), {})()
    obj.save_mappings_to_config = lambda: None
    obj.keyboard_thread = type('T', (), {'stop': lambda s: None, 'wait': lambda s, t=None: True})()
    obj.mouse_thread = type('T', (), {'stop': lambda s: None, 'wait': lambda s, t=None: True})()
    obj._active_title_timer = type('T', (), {'stop': lambda s: None})()
    obj._unhook_all_keyboard_hooks = lambda : None
    obj.tray_icon = type('T', (), {'hide': lambda s: None})()

    close = m.KeyMapperApp.closeEvent.__get__(obj, m.KeyMapperApp)
    close(DummyEvent())

    assert called['exit'] is True
