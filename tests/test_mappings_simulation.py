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


def test_refresh_keyboard_hooks_handles_macro_mappings():
    """_refresh_keyboard_hooks should index macro mappings by source_key and
    store the full mapping dict in the bucket (not None) so low-level hooks
    can hand the dict to the handler without causing NoneType errors.
    """
    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._kbd_available = True
    # Keep hooks disabled so the _update_hooks_for_active_title fast-exit
    obj._kbd_enabled = False
    obj.mappings = {'mywindow': {'Macro 1': {'type': 'macro', 'macro_id': 'Macro 1', 'source_key': 'q', 'window_title': 'mywindow', 'actions': ['text:hi']}}}

    # Call the refresh function and assert index contains mapping dict
    refresh = m.KeyMapperApp._refresh_keyboard_hooks.__get__(obj, m.KeyMapperApp)
    refresh()

    assert 'q' in obj._source_index
    bucket = obj._source_index['q']
    assert bucket and isinstance(bucket[0][1], dict)
    assert bucket[0][1].get('type') == 'macro'


def test_handle_mapping_action_enqueues_macro(monkeypatch):
    obj = type('O', (), {})()
    # fake macro present in macros_by_id
    macro = {'id': 'Macro 1', 'name': 'TestMacro', 'actions': ['text:hi']}
    obj.macros_by_id = {'Macro 1': macro}

    # record enqueue calls
    enqueued = []
    class DummyMacroThread:
        def enqueue_macro(self, m):
            enqueued.append(m)

    obj.macro_thread = DummyMacroThread()
    # ping_output_view should accept insertPlainText calls
    obj.ping_output_view = type('P', (), {'insertPlainText': lambda s: None})()

    from s_mapper.ui import KeyMapperApp
    handler = KeyMapperApp._handle_mapping_action.__get__(obj, KeyMapperApp)
    handler({'type': 'macro', 'macro_id': 'Macro 1'})

    assert len(enqueued) == 1
    assert enqueued[0]['name'] == 'TestMacro'


def test_macro_trigger_from_key_can_fire_multiple_times():
    # Simulate repeated key presses bound to a macro; ensure each press
    # results in the macro being enqueued.
    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._kbd_available = False
    obj._active_title_lock = __import__('threading').Lock()
    obj._cached_active_title = 'mywindow'

    # mapping is a macro mapping stored under the target window
    obj.mappings = {'mywindow': {'Macro 1': {'type': 'macro', 'macro_id': 'Macro 1', 'source_key': 'q', 'window_title': 'mywindow', 'actions': ['text:ok']}}}

    # provide macros_by_id so handler can look up macro
    obj.macros_by_id = {'Macro 1': {'id': 'Macro 1', 'name': 'RepeatMacro', 'actions': ['text:ok']}}

    # dummy enqueue recorder
    enqueued = []
    class DummyMacroThread:
        def enqueue_macro(self, m):
            enqueued.append(m)

    obj.macro_thread = DummyMacroThread()

    # Connect the handler so mapping_action_signal emits call into _handle_mapping_action
    class Emitter:
        def __init__(self, cb):
            self.cb = cb
        def emit(self, v):
            # emulate PyQt signal dispatch
            self.cb(v)

    # bind handler and replace the object's signal
    from s_mapper.ui import KeyMapperApp
    handler = KeyMapperApp._handle_mapping_action.__get__(obj, KeyMapperApp)
    obj.mapping_action_signal = Emitter(handler)

    # Simulate two key presses
    fake_key = __import__('types').SimpleNamespace(name='q')
    press = m.KeyMapperApp.on_press.__get__(obj, m.KeyMapperApp)
    press(fake_key)
    press(fake_key)

    assert len(enqueued) == 2


def test_low_level_hook_callback_enqueues_macro_multiple_times(monkeypatch):
    """Simulate the low-level keyboard callback path created by
    _update_hooks_for_active_title. We monkeypatch the `kbd.on_press_key`
    helper to capture the created callback and then invoke it twice with a
    fake event. The macro should be enqueued both times.
    """
    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._kbd_available = True
    obj._kbd_enabled = True
    obj._active_title_lock = __import__('threading').Lock()
    obj._cached_active_title = 'mywindow'

    # mapping is a macro mapping stored under the target window
    obj.mappings = {'mywindow': {'Macro 1': {'type': 'macro', 'macro_id': 'Macro 1', 'source_key': 'q', 'window_title': 'mywindow', 'actions': ['text:ok']}}}
    obj.macros_by_id = {'Macro 1': {'id': 'Macro 1', 'name': 'LLMacro', 'actions': ['text:ok']}}

    enqueued = []
    class DummyMacroThread:
        def enqueue_macro(self, m):
            enqueued.append(m)

    obj.macro_thread = DummyMacroThread()

    # mapping_action_signal should call the handler that enqueues macros
    from s_mapper.ui import KeyMapperApp
    handler = KeyMapperApp._handle_mapping_action.__get__(obj, KeyMapperApp)
    class Emitter:
        def __init__(self, cb):
            self.cb = cb
        def emit(self, v):
            self.cb(v)

    obj.mapping_action_signal = Emitter(handler)

    # prepare internal structures used by _refresh_keyboard_hooks
    obj._source_index = {}
    obj._keyboard_hooks = {}
    obj._kbd_ignore = {}

    captured = {}

    def fake_on_press_key(key, callback, suppress=False):
        # Return a lightweight handle and capture the callback
        captured['cb'] = callback
        return {'key': key}

    # Provide a dummy kbd module interface for functions used in the callback
    import importlib
    ui_mod = importlib.import_module('s_mapper.ui')
    monkeypatch.setattr(ui_mod, 'kbd', type('K', (), {'on_press_key': fake_on_press_key, 'is_pressed': lambda *_: False, 'send': lambda *_: None}))

    # Make sure the nested update function is available on the dummy object
    obj._update_hooks_for_active_title = KeyMapperApp._update_hooks_for_active_title.__get__(obj, KeyMapperApp)

    # Now call the method to build hooks — it should call our fake_on_press_key
    refresh = KeyMapperApp._refresh_keyboard_hooks.__get__(obj, KeyMapperApp)
    refresh()

    assert 'cb' in captured

    # Build a fake event object the callback expects
    event = type('E', (), {'event_type': 'down', 'name': 'q'})()

    # First invoke
    captured['cb'](event)
    # wait for the short ignore window to expire (slightly longer than 0.25s)
    import time as _time
    _time.sleep(0.3)
    # Second invoke should enqueue again after expiry
    captured['cb'](event)

    assert len(enqueued) == 2


def test_keyboard_hook_no_error_when_bucket_no_match(monkeypatch):
    """Ensure callback doesn't reference uninitialized locals when the
    bucket contains entries that don't match the active window title."""
    from s_mapper.ui import KeyMapperApp

    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._kbd_available = True
    obj._kbd_enabled = True
    obj._active_title_lock = __import__('threading').Lock()
    obj._cached_active_title = 'mywindow'

    # bucket contains an entry that will *not* match the active title
    obj._source_index = {'q': [('otherwindow', 'x')]}
    obj._keyboard_hooks = {}
    obj._kbd_ignore = {}

    captured = {}

    def fake_on_press_key(key, callback, suppress=False):
        captured['cb'] = callback
        return {'key': key}

    import importlib
    ui_mod = importlib.import_module('s_mapper.ui')
    monkeypatch.setattr(ui_mod, 'kbd', type('K', (), {'on_press_key': fake_on_press_key, 'is_pressed': lambda *_: False, 'send': lambda *_: None}))

    # bind the nested helper
    obj._update_hooks_for_active_title = KeyMapperApp._update_hooks_for_active_title.__get__(obj, KeyMapperApp)
    # call refresh which should not raise and should create a callback
    refresh = KeyMapperApp._refresh_keyboard_hooks.__get__(obj, KeyMapperApp)
    refresh()

    assert 'cb' in captured

    # build an event and call the callback; no exception should be raised
    event = type('E', (), {'event_type': 'down', 'name': 'q'})()
    captured['cb'](event)


def test_macro_running_flag_blocks_mappings():
    """Ensure that when a macro is running, mapping handlers ignore incoming
    triggers (prevents macro synthetic input from retriggering mappings).
    """
    from s_mapper.ui import KeyMapperApp

    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._kbd_available = False
    obj._kbd_enabled = False
    obj._active_title_lock = __import__('threading').Lock()
    obj._cached_active_title = 'mywindow'
    obj._macro_running = True

    obj.mappings = {'mywindow': {'Map 1': {'source_key': 'q', 'target_key': 'x', 'window_title': 'mywindow'}}}

    calls = []
    class DummyEmitter:
        def emit(self, *a, **k):
            calls.append((a, k))

    obj.mapping_action_signal = DummyEmitter()

    press = KeyMapperApp.on_press.__get__(obj, KeyMapperApp)
    fake_key = __import__('types').SimpleNamespace(name='q')
    press(fake_key)

    # Nothing should have been enqueued due to _macro_running True
    assert len(calls) == 0


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
    from s_mapper.ui import KeyMapperApp
    handler = KeyMapperApp._handle_mapping_action.__get__(obj, KeyMapperApp)
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
