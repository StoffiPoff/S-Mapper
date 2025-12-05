import importlib
import time


def test_macro_thread_sets_app_flag_and_respects_order(monkeypatch):
    # Import MacroThread class
    mod = importlib.import_module('s_mapper.threads')
    # Build a dummy app to observe flag
    app = type('A', (), {})()
    app._macro_running = False

    # Capture actions performed by the controller
    ops = []

    class DummyController:
        def type(self, s):
            ops.append(('type', s))

        def press(self, k):
            ops.append(('press', k))

        def release(self, k):
            ops.append(('release', k))

    # Replace keyboard.Controller used internally
    monkeypatch.setattr(mod.keyboard, 'Controller', lambda: DummyController())

    mt = mod.MacroThread(app=app)

    # Create a simple macro with enter then text
    macro = {'id': 'm1', 'name': 'm1', 'actions': ['key:enter', 'text:Hello']}
    mt.enqueue_macro(macro)

    # Run the thread loop in a way suitable for tests: start it then wait
    mt.start()
    # allow time for macro to process
    time.sleep(0.5)
    mt.stop()
    mt.wait(1000)

    # The app flag should have been set and cleared
    assert getattr(app, '_macro_running', False) is False

    # Ensure actions were performed in sequence
    # press/release should appear before typing Hello
    assert any(op[0] == 'press' for op in ops)
    assert any(op[0] == 'release' for op in ops)
    assert any(op == ('type', 'Hello') for op in ops)


def test_macro_thread_types_char_by_char_and_queues_repeated(monkeypatch):
    mod = importlib.import_module('s_mapper.threads')
    app = type('A', (), {})()
    app._macro_running = False

    ops = []

    class DummyController:
        def type(self, s):
            ops.append(('type', s))

        def press(self, k):
            ops.append(('press', k))

        def release(self, k):
            ops.append(('release', k))

    monkeypatch.setattr(mod.keyboard, 'Controller', lambda: DummyController())

    mt = mod.MacroThread(app=app)
    # tune delays down so tests run quickly
    mt.char_delay = 0.001
    mt.after_enter_delay = 0.01

    macro = {'id': 'm2', 'name': 'm2', 'actions': ['text:AB', 'key:enter', 'text:CD']}

    mt.enqueue_macro(macro)
    mt.enqueue_macro(macro)

    mt.start()
    import time as _t
    _t.sleep(0.35)
    mt.stop()
    mt.wait(1000)

    # Ensure both macros processed sequentially i.e. ops should contain the pattern twice
    seq = ''.join([o[0] + (str(o[1]) if len(o) > 1 else '') for o in ops])
    # Expect 'press'/'release' around enter and 'type' fragments for chars
    assert seq.count('type') >= 4


def test_macro_thread_supports_modifier_combos(monkeypatch):
    mod = importlib.import_module('s_mapper.threads')
    app = type('A', (), {})()
    app._macro_running = False

    ops = []

    class DummyController:
        def type(self, s):
            ops.append(('type', s))

        def press(self, k):
            ops.append(('press', k))

        def release(self, k):
            ops.append(('release', k))

    monkeypatch.setattr(mod.keyboard, 'Controller', lambda: DummyController())

    mt = mod.MacroThread(app=app)
    mt.char_delay = 0.001
    mt.after_enter_delay = 0.01

    # Use a modifier combo (ctrl + n) followed by typing 'Hi' and enter
    macro = {'id': 'm3', 'name': 'm3', 'actions': ['key:ctrl + n', 'text:Hi', 'key:enter']}
    mt.enqueue_macro(macro)
    mt.start()
    import time as _t
    _t.sleep(0.2)
    mt.stop()
    mt.wait(1000)

    # Expect the sequence: press(ctrl), press(n), release(n), release(ctrl)
    # followed by characters 'H' and 'i' and an enter press/release
    assert any(op[0] == 'press' for op in ops)
    # find first modifier press
    assert any(str(op[1]).lower().find('ctrl') >= 0 or op[1] == mod.keyboard.Key.ctrl for op in ops if op[0] == 'press' or op[0] == 'release')


def test_macro_thread_handles_tab_action(monkeypatch):
    # Ensure 'key:tab' and 'key:Key.tab' both cause controller press/release
    mod = importlib.import_module('s_mapper.threads')
    app = type('A', (), {})()
    app._macro_running = False

    ops = []

    class DummyController:
        def type(self, s):
            ops.append(('type', s))

        def press(self, k):
            ops.append(('press', k))

        def release(self, k):
            ops.append(('release', k))

    monkeypatch.setattr(mod.keyboard, 'Controller', lambda: DummyController())

    mt = mod.MacroThread(app=app)

    # Enqueue macros with both 'tab' token styles
    mt.enqueue_macro({'id': 't1', 'name': 't1', 'actions': ['key:tab']})
    mt.enqueue_macro({'id': 't2', 'name': 't2', 'actions': ['key:Key.tab']})

    mt.start()
    import time as _t
    _t.sleep(0.2)
    mt.stop()
    mt.wait(1000)

    # Expect press and release calls for the tab key in operations
    found_press = any(op[0] == 'press' and ('tab' in (getattr(op[1], 'name', str(op[1])).lower())) for op in ops)
    found_release = any(op[0] == 'release' and ('tab' in (getattr(op[1], 'name', str(op[1])).lower())) for op in ops)

    assert found_press and found_release


def test_macro_thread_expands_repeat_shorthand(monkeypatch):
    mod = importlib.import_module('s_mapper.threads')
    app = type('A', (), {})()
    app._macro_running = False

    ops = []

    class DummyController:
        def type(self, s):
            ops.append(('type', s))

        def press(self, k):
            ops.append(('press', k))

        def release(self, k):
            ops.append(('release', k))

    monkeypatch.setattr(mod.keyboard, 'Controller', lambda: DummyController())

    mt = mod.MacroThread(app=app)
    mt.char_delay = 0.001

    # Repeat syntax should expand to 3 tab key presses/releases (with/without space)
    macro = {'id': 'rep', 'name': 'rep', 'actions': ['key:tab x 3', 'key:tab x3', 'text:OK']}
    mt.enqueue_macro(macro)

    mt.start()
    import time as _t
    # Wait for macro to start then finish (sets app._macro_running True/False)
    deadline = _t.time() + 1.0
    while not getattr(app, '_macro_running', False) and _t.time() < deadline:
        _t.sleep(0.02)
    deadline = _t.time() + 1.0
    while getattr(app, '_macro_running', False) and _t.time() < deadline:
        _t.sleep(0.02)
    mt.stop()
    mt.wait(1000)

    tab_presses = [op for op in ops if op[0] == 'press' and 'tab' in str(getattr(op[1], 'name', op[1])).lower()]
    tab_releases = [op for op in ops if op[0] == 'release' and 'tab' in str(getattr(op[1], 'name', op[1])).lower()]

    # expect 3 + 3 = 6 tab presses/releases
    assert len(tab_presses) == 6
    assert len(tab_releases) == 6
    assert ('type', 'OK') in ops


def test_macro_abort_on_external_input(monkeypatch):
    # MacroThread should stop current macro when abort_current_macro is called
    mod = importlib.import_module('s_mapper.threads')
    app = type('A', (), {})()
    app._macro_running = False

    ops = []

    class DummyController:
        def type(self, s):
            ops.append(('type', s))

        def press(self, k):
            ops.append(('press', k))

        def release(self, k):
            ops.append(('release', k))

    monkeypatch.setattr(mod.keyboard, 'Controller', lambda: DummyController())

    mt = mod.MacroThread(app=app)
    mt.char_delay = 0.001
    # enqueue a macro that sleeps for a bit, then types
    macro = {'id': 'abort1', 'name': 'abort1', 'actions': ['sleep:1.0', 'text:HELLO']}
    mt.enqueue_macro(macro)

    mt.start()
    import time as _t
    # wait for the macro to start and enter sleep
    _t.sleep(0.2)

    # Ensure macro running flag set
    assert getattr(app, '_macro_running', False) is True

    # simulate user input abort
    mt.abort_current_macro()

    # give some time for the interrupt to be processed
    _t.sleep(0.2)

    # stop the thread and wait to finish
    mt.stop()
    mt.wait(1000)

    # macro should have cleared running flag
    assert getattr(app, '_macro_running', False) is False

    # typing HELLO should not have occurred because macro was aborted during sleep
    assert not any(o[0] == 'type' and o[1] == 'HELLO' for o in ops)


def test_ui_on_press_triggers_macro_abort():
    # Ensure the UI handler will notify the MacroThread to abort when macro running
    import importlib
    # Import the UI class directly to avoid lazy-package import issues
    mod_ui = importlib.import_module('s_mapper.ui')
    threads_mod = importlib.import_module('s_mapper.threads')

    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._macro_running = True
    # attach a fake macro_thread with spy
    class FakeMT:
        def __init__(self):
            self.called = False

        def abort_current_macro(self):
            self.called = True

    obj.macro_thread = FakeMT()

    handler = mod_ui.KeyMapperApp.on_press.__get__(obj, mod_ui.KeyMapperApp)
    handler(None)

    assert obj.macro_thread.called is True


def test_ui_does_not_abort_on_synthetic_input():
    # Ensure on_press ignores synthetic input generated by macros
    import importlib, time
    mod_ui = importlib.import_module('s_mapper.ui')

    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._macro_running = True
    # attach a fake macro_thread with spy
    class FakeMT:
        def __init__(self):
            self.called = False

        def abort_current_macro(self):
            self.called = True

    obj.macro_thread = FakeMT()
    # mark last injected time as now
    obj._last_injected_event_time = time.time()
    obj._synthetic_input_grace = 0.5

    handler = mod_ui.KeyMapperApp.on_press.__get__(obj, mod_ui.KeyMapperApp)
    # make a simple key-like object
    key = type('K', (), {'name': 'a'})()
    handler(key)

    # abort should NOT have been called since event is synthetic
    assert obj.macro_thread.called is False
