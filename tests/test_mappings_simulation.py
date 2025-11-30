import importlib
import threading
from types import SimpleNamespace

m = importlib.import_module('s_mapper')


class DummySignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, cb):
        self._callbacks.append(cb)

    def emit(self, *args, **kwargs):
        for cb in list(self._callbacks):
            try:
                cb(*args, **kwargs)
            except Exception:
                raise


def make_obj_for_keypress():
    obj = type('O', (), {})()
    # minimal attributes used by on_press
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._kbd_available = False
    obj._kbd_enabled = False
    obj._active_title_lock = threading.Lock()
    obj._cached_active_title = 'mywindow'
    obj.mappings = {'mywindow': {'Mapping 1': {'source_key': 'q', 'target_key': 'x', 'window_title': 'mywindow'}}}
    # replace signal with simple object that records the emitted value
    calls = []
    class DummyEmitter:
        def emit(self, *args, **kwargs):
            calls.append((args, kwargs))

    obj.mapping_action_signal = DummyEmitter()
    return obj, calls


def test_keyboard_mapping_triggers_action():
    obj, calls = make_obj_for_keypress()

    # create a fake key object that has a .name attribute
    fake_key = SimpleNamespace(name='q')

    # bind and call on_press
    press = m.KeyMapperApp.on_press.__get__(obj, m.KeyMapperApp)
    press(fake_key)

    assert len(calls) == 1
    assert calls[0][0][0] == 'x'


def test_mouse_mapping_triggers_action():
    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._active_title_lock = threading.Lock()
    obj._cached_active_title = 'mywindow'
    obj.click_interval = 0.6
    obj.last_click_time = {}
    obj.click_counts = {}
    obj.mappings = {'mywindow': {'Mapping 1': {'mouse_button': 'left', 'press_count': 1, 'keyboard_button': 'z', 'window_title': 'mywindow'}}}

    # minimal emitter and recorder
    calls = []
    class DummyEmitter:
        def emit(self, *args, **kwargs):
            calls.append((args, kwargs))

    obj.mapping_action_signal = DummyEmitter()

    # fake mouse Button with .name
    fake_button = SimpleNamespace(name='left')

    click = m.KeyMapperApp.on_click.__get__(obj, m.KeyMapperApp)
    click(0, 0, fake_button, True)

    assert len(calls) == 1
    assert calls[0][0][0] == 'z'


def test_handle_mapping_action_injects_keys(monkeypatch):
    obj = type('O', (), {})()

    # Dummy keyboard controller that records operations
    events = []

    class DummyPressed:
        def __init__(self, events, *args):
            self.events = events

        def __enter__(self):
            self.events.append(('pressed_mods_enter',))

        def __exit__(self, exc_type, exc, tb):
            self.events.append(('pressed_mods_exit',))

    class DummyController:
        def pressed(self, *mods):
            return DummyPressed(events, mods)

        def press(self, k):
            events.append(('press', k))

        def release(self, k):
            events.append(('release', k))

    obj.keyboard_controller = DummyController()

    # call handler for a simple key
    handler = m.KeyMapperApp._handle_mapping_action.__get__(obj, m.KeyMapperApp)
    handler('a')
    assert ('press', 'a') in events and ('release', 'a') in events

    # now test modifiers (ctrl + alt + d)
    events.clear()
    handler('ctrl + alt + d')

    # Modifier pressed context should be entered and exited
    assert ('pressed_mods_enter',) in events
    assert ('pressed_mods_exit',) in events
    # The main key press/release should be recorded (Key.* may be used; ensure we see press/release)
    assert any(e[0] == 'press' for e in events)
    assert any(e[0] == 'release' for e in events)


def test_on_clipboard_change_starts_ping_thread(monkeypatch):
    obj = type('O', (), {})()

    # Minimal attributes
    obj._cached_active_title = 'myapp'
    obj._active_title_lock = threading.Lock()
    obj.ip_monitor_window_entry = SimpleNamespace(text=lambda: 'myapp')
    # toggle button check
    obj.ip_monitor_toggle_button = SimpleNamespace(isChecked=lambda: True, setText=lambda t: None)
    obj.ping_status_indicator = SimpleNamespace(setStyleSheet=lambda s: setattr(obj, '_indicator_style', s))

    # ping status label
    obj.ping_status_label = SimpleNamespace(show_message=lambda *a, **k: setattr(obj, '_last_show', a))
    # required methods referenced by clipboard handler
    obj.update_label_position = lambda *a, **k: None
    obj.handle_ping_result = lambda color, output: setattr(obj, '_last_ping', (color, output))

    # clipboard | mouse thread | ping thread store
    obj.clipboard = SimpleNamespace(text=lambda: '127.0.0.1')
    obj.mouse_thread = SimpleNamespace(mouse_moved=DummySignal())
    obj._ping_threads = set()

    # Replace PingThread with a dummy class that emits ping_result immediately
    started = {'called': False}

    class DummyPingThread:
        def __init__(self, ip):
            self.ip = ip
            self.ping_result = DummySignal()
            self.finished = DummySignal()

        def start(self):
            started['called'] = True
            # Simulate successful ping
            self.ping_result.emit('green', 'Dummy OK')
            # signal finished
            self.finished.emit()

    monkeypatch.setattr(m, 'PingThread', DummyPingThread)

    # Bind and call the method
    call = m.KeyMapperApp.on_clipboard_change.__get__(obj, m.KeyMapperApp)
    call()

    assert started['called'] is True


def test_on_clipboard_change_ignores_non_ip(monkeypatch):
    obj = type('O', (), {})()
    obj._cached_active_title = 'myapp'
    obj._active_title_lock = threading.Lock()
    obj.ip_monitor_window_entry = SimpleNamespace(text=lambda: 'myapp')
    obj.ip_monitor_toggle_button = SimpleNamespace(isChecked=lambda: True)
    obj.clipboard = SimpleNamespace(text=lambda: 'not.an.ip')

    called = {'ping': False}

    class DummyPingThread:
        def __init__(self, ip):
            called['ping'] = True

    monkeypatch.setattr(m, 'PingThread', DummyPingThread)

    call = m.KeyMapperApp.on_clipboard_change.__get__(obj, m.KeyMapperApp)
    call()

    assert called['ping'] is False
