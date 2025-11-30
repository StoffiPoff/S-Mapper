import subprocess
import threading
import logging
import queue
import time
from PyQt6.QtCore import QThread, pyqtSignal
from pynput import mouse, keyboard

from .utils import parse_ping_output


class KeyboardListenerThread(QThread):
    """A QThread that runs the pynput keyboard listener."""
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.listener = None

    def run(self):
        self.listener = keyboard.Listener(on_press=self.app.on_press)
        self.listener.start()
        self.listener.join()

    def stop(self):
        if self.listener:
            self.listener.stop()


class ActiveWindowEventThread(QThread):
    """Windows-only thread that registers a SetWinEventHook for foreground/focus
    change (EVENT_SYSTEM_FOREGROUND). The callback runs on this thread and
    this class emits `active_window_changed` signal with the new title.
    """
    active_window_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._hook = None
        self._user32 = None
        self._stop_event = threading.Event()

    def run(self):
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return

        try:
            user32 = ctypes.windll.user32
        except Exception:
            return

        WINEVENT_OUTOFCONTEXT = 0x0000
        EVENT_SYSTEM_FOREGROUND = 0x0003

        WinEventProcType = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD,
                                             wintypes.HWND, wintypes.LONG,
                                             wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

        def _get_window_text(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ''
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or ''

        @WinEventProcType
        def _callback(hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
            try:
                if not hwnd:
                    title = ''
                else:
                    title = _get_window_text(hwnd)
                self.active_window_changed.emit((title or '').strip().lower())
            except Exception:
                pass

        try:
            hook = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
                                          0, _callback, 0, 0, WINEVENT_OUTOFCONTEXT)
            self._hook = hook
        except Exception:
            return

        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                self.msleep(50)

        try:
            if self._hook:
                user32.UnhookWinEvent(self._hook)
                self._hook = None
        except Exception:
            pass

    def stop(self):
        self._stop_event.set()


class MouseListenerThread(QThread):
    """A QThread that runs the pynput mouse listener."""
    mouse_moved = pyqtSignal(int, int)

    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.listener = None

    def on_move(self, x, y):
        self.mouse_moved.emit(x, y)

    def run(self):
        self.listener = mouse.Listener(
            on_click=self.app.on_click,
            on_move=self.on_move
        )
        self.listener.start()
        self.listener.join()

    def stop(self):
        if self.listener:
            self.listener.stop()


class PingThread(QThread):
    ping_result = pyqtSignal(str, str)

    def __init__(self, ip_address):
        super().__init__()
        self.ip_address = ip_address
        self._proc = None
        self._stopped = False

    def run(self):
        output = ""
        try:
            cmd = ['ping', '-n', '4', self.ip_address]
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                output, _ = self._proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    self._proc.kill()
                except Exception:
                    pass
                self.ping_result.emit('red', 'Ping command timed out.')
                return

            _, color = parse_ping_output(output)

            self.ping_result.emit(color, output)

        except Exception:
            logging.exception("Ping failed")
            self.ping_result.emit('red', output or f"Ping command failed for {self.ip_address}")

    def stop(self):
        self._stopped = True
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=1)
                except Exception:
                    self._proc.kill()
        except Exception:
            pass


class MacroThread(QThread):
    """Background thread that executes queued macros.

    A macro is a dict with keys:
      - name: str
      - actions: list of actions

    Supported action forms (simple):
      - 'text:your text' -> types the literal string
      - 'key:<name>' -> presses & releases the named key (e.g. 'enter')
      - 'sleep:<seconds>' -> sleeps for given seconds

    The thread exposes a simple queue interface via `enqueue_macro()`.
    """
    macro_log = pyqtSignal(str)

    def __init__(self, app=None):
        super().__init__()
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        # event to request aborting the currently executing macro
        self._current_abort = threading.Event()
        # Optional app reference used to mark the app while a macro is executing
        # so mapping handlers can avoid re-triggering during synthetic input.
        self.app = app

        try:
            # reuse the module-level keyboard helper which is a module in this file
            self._controller = keyboard.Controller()
        except Exception:
            self._controller = None

    def enqueue_macro(self, macro: dict):
        """Add a macro dict to the internal queue."""
        if not isinstance(macro, dict):
            return
        self._queue.put(macro)

    def run(self):
        while not self._stop_event.is_set():
            try:
                macro = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            name = macro.get('name', '<unnamed>')
            actions = macro.get('actions', []) or []
            try:
                self.macro_log.emit(f"Starting macro: {name}")
            except Exception:
                pass

            # mark app as running a macro while we execute to prevent
            # mappings from being triggered by our synthetic events
            if getattr(self, 'app', None):
                try:
                    self.app._macro_running = True
                except Exception:
                    pass

            # clear any previous abort requests for this macro
            self._current_abort.clear()

            for act in actions:
                if self._stop_event.is_set() or self._current_abort.is_set():
                    break
                try:
                    if isinstance(act, str) and act.startswith('sleep:'):
                        sec = float(act.split(':', 1)[1]) if ':' in act else 0.1
                        # Sleep in short increments so abort requests can be noticed
                        waited = 0.0
                        step = 0.05
                        while waited < sec:
                            if self._stop_event.is_set() or self._current_abort.is_set():
                                break
                            to_sleep = min(step, sec - waited)
                            time.sleep(to_sleep)
                            waited += to_sleep
                    if isinstance(act, str) and act.startswith('text:'):
                        text = act.split(':', 1)[1]
                        if self._controller:
                            try:
                                # Use the controller.type API to send the full
                                # text payload in one operation where possible.
                                # This is simpler for end-users and matches the
                                # tests which expect 'type' events per text action.
                                try:
                                    # mark that we're about to inject synthetic input
                                    try:
                                        if getattr(self, 'app', None):
                                            setattr(self.app, '_last_injected_event_time', time.time())
                                    except Exception:
                                        pass
                                    self._controller.type(text)
                                except Exception:
                                    # Fallback: try character-by-character with
                                    # a short delay between characters.
                                    char_delay = getattr(self, 'char_delay', 0.02)
                                    for ch in text:
                                        try:
                                            if getattr(self, 'app', None):
                                                setattr(self.app, '_last_injected_event_time', time.time())
                                        except Exception:
                                            pass
                                        try:
                                            self._controller.press(ch)
                                            self._controller.release(ch)
                                        except Exception:
                                            try:
                                                self._controller.type(ch)
                                            except Exception:
                                                pass
                                        try:
                                            time.sleep(char_delay)
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                    elif isinstance(act, str) and act.startswith('key:'):
                        keyname = act.split(':', 1)[1]
                        if self._controller:
                            try:
                                # support modifier + main key combos like "ctrl + n"
                                parts = [p.strip() for p in keyname.replace(' + ', '+').split('+') if p.strip()]
                                # Normalize parts so we accept variations like 'Key.tab', '"tab"' or "'tab'"
                                norm_parts = []
                                for p in parts:
                                    qp = p.strip().strip('"\'').lower()
                                    # Accept tokens of the form Key.tab by stripping the prefix
                                    if qp.lower().startswith('key.'):
                                        qp = qp.split('.', 1)[1]
                                    norm_parts.append(qp)

                                parts = norm_parts

                                # Map modifier names to Key enum where possible
                                mod_map = {'ctrl': keyboard.Key.ctrl, 'control': keyboard.Key.ctrl, 'shift': keyboard.Key.shift, 'alt': keyboard.Key.alt,
                                           'win': keyboard.Key.cmd, 'windows': keyboard.Key.cmd, 'cmd': keyboard.Key.cmd, 'meta': keyboard.Key.cmd}

                                # Resolve parts into Key objects or literal chars
                                resolved = [getattr(keyboard.Key, p, p) for p in parts]

                                # If there are modifiers, press them first then press the final key
                                if len(resolved) > 1:
                                    modifiers = resolved[:-1]
                                    main = resolved[-1]
                                    # press modifiers
                                    for m in modifiers:
                                        try:
                                            if getattr(self, 'app', None):
                                                setattr(self.app, '_last_injected_event_time', time.time())
                                        except Exception:
                                            pass
                                        try:
                                            self._controller.press(m)
                                        except Exception:
                                            pass
                                    # press main
                                    try:
                                        if getattr(self, 'app', None):
                                            setattr(self.app, '_last_injected_event_time', time.time())
                                        self._controller.press(main)
                                        self._controller.release(main)
                                    except Exception:
                                        try:
                                            self._controller.type(str(main))
                                        except Exception:
                                            pass
                                    # release modifiers in reverse order
                                    for m in reversed(modifiers):
                                        try:
                                            self._controller.release(m)
                                        except Exception:
                                            pass
                                else:
                                    # single key
                                    k = resolved[0]
                                    try:
                                        if getattr(self, 'app', None):
                                            setattr(self.app, '_last_injected_event_time', time.time())
                                        self._controller.press(k)
                                        self._controller.release(k)
                                    except Exception:
                                        try:
                                            self._controller.type(str(k))
                                        except Exception:
                                            pass
                                # longer pause after 'enter' or newline keys to
                                # make sure the target app processes the newline
                                # (helps Notepad insert a complete new line)
                                try:
                                    if keyname in ('enter', '\n'):
                                        time.sleep(getattr(self, 'after_enter_delay', 0.12))
                                except Exception:
                                    pass
                            except Exception:
                                try:
                                    self._controller.type(keyname)
                                except Exception:
                                    pass
                    else:
                        # Unknown action — treat as a small delay to be safe
                        time.sleep(0.05)

                    # Small post-action delay to give target applications (e.g.
                    # Notepad) time to process injected events before the next
                    # action begins. This helps avoid dropped characters and
                    # missed Enter presses on some systems.
                    try:
                        # allow aborts to be detected during this short wait as well
                        waited = 0.0
                        tiny_step = 0.02
                        while waited < 0.05:
                            if self._stop_event.is_set() or self._current_abort.is_set():
                                break
                            time.sleep(tiny_step)
                            waited += tiny_step
                    except Exception:
                        pass
                except Exception:
                    logging.exception("Macro action failed")

            try:
                self.macro_log.emit(f"Finished macro: {name}")
            except Exception:
                pass

            # clear running flag
            if getattr(self, 'app', None):
                try:
                    self.app._macro_running = False
                except Exception:
                    pass

    def abort_current_macro(self):
        """Request that the currently executing macro be aborted immediately.

        This does not stop the MacroThread itself; it merely interrupts the
        currently running macro and lets the thread continue to the next
        queued item (if any).
        """
        try:
            self._current_abort.set()
        except Exception:
            pass

    def stop(self):
        self._stop_event.set()
        # drain the queue so we don't attempt further work
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass


class MacroRecorder(QThread):
    """Records a short sequence of keyboard events (and simple mouse clicks).

    Emits recorded signal with a list of action strings when recording stops.
    """
    recorded = pyqtSignal(list)

    def __init__(self, include_mouse=False):
        super().__init__()
        self.include_mouse = include_mouse
        self._stop_event = threading.Event()

    def run(self):
        try:
            from pynput import keyboard as _kbd
            from pynput import mouse as _mouse
        except Exception:
            # Not available in this environment — nothing to record
            self.recorded.emit([])
            return

        actions = []
        last_time = None

        def _maybe_sleep(ts):
            nonlocal last_time
            if last_time is None:
                last_time = ts
                return
            delta = ts - last_time
            last_time = ts
            if delta >= 0.02:
                actions.append(f"sleep:{delta:.2f}")

        def on_press(key):
            try:
                t = time.time()
                _maybe_sleep(t)
                if isinstance(key, _kbd.KeyCode):
                    ch = getattr(key, 'char', None)
                    if ch:
                        actions.append(f"text:{ch}")
                    else:
                        actions.append(f"key:{key}")
                else:
                    # special keys
                    kn = getattr(key, 'name', str(key))
                    actions.append(f"key:{kn}")
            except Exception:
                pass
            if self._stop_event.is_set():
                # Stop listener
                return False

        def on_click(x, y, button, pressed):
            if not self.include_mouse:
                return
            if not pressed:
                return
            t = time.time()
            _maybe_sleep(t)
            try:
                bn = getattr(button, 'name', str(button))
            except Exception:
                bn = str(button)
            actions.append(f"key:mouse_{bn}")
            if self._stop_event.is_set():
                return False

        # Use listeners; they block until stopped via return False
        k_listener = _kbd.Listener(on_press=on_press)
        if self.include_mouse:
            m_listener = _mouse.Listener(on_click=on_click)
        else:
            m_listener = None

        k_listener.start()
        if m_listener:
            m_listener.start()

        # Wait until stop event is set
        while not self._stop_event.is_set():
            self.msleep(50)

        # Ensure listeners stopped
        try:
            k_listener.stop()
        except Exception:
            pass
        try:
            if m_listener:
                m_listener.stop()
        except Exception:
            pass

        self.recorded.emit(actions)

    def stop(self):
        self._stop_event.set()
