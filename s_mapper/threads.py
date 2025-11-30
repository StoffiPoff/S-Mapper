import subprocess
import threading
import logging
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
