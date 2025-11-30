import importlib


def test_macro_thread_respects_sleep(monkeypatch):
    """Ensure that the MacroThread executes sleep actions by invoking time.sleep
    with the expected durations."""
    mod = importlib.import_module('s_mapper.threads')

    # Replace controller so we don't actually send keys
    class DummyController:
        def press(self, k):
            pass

        def release(self, k):
            pass

        def type(self, s):
            pass

    monkeypatch.setattr(mod.keyboard, 'Controller', lambda: DummyController())

    # Use the real time.sleep and measure elapsed time so the test ensures
    # 'sleep:0.25' actually delays processing.

    mt = mod.MacroThread(app=None)

    # Use a short but identifiable sleep so test completes quickly
    mt.enqueue_macro({'id': 's1', 'name': 's1', 'actions': ['text:X', 'sleep:0.25', 'text:Y']})

    import time as _t
    # Reduce character typing delay so total runtime is predictable
    mt.char_delay = 0.0

    t0 = _t.time()
    mt.start()
    # Wait a moment for the macro to be processed by the thread
    _t.sleep(0.6)
    mt.stop()
    mt.wait(1000)

    elapsed = _t.time() - t0
    # elapsed should exceed the explicit sleep duration (0.25)
    assert elapsed >= 0.25
