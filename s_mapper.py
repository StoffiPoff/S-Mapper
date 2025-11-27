import sys
import os
import time
import configparser
import re
import subprocess

# Properties for the executable
__company__ = "JafsWorks"
__product__ = "Stoffi-S-Mapper"
__version__ = "1.0.0"
__description__ = "A versatile tool for remapping keyboard and mouse inputs."
__copyright__ = "Copyright (c) 2025 JafsWorks"
__license__ = "MIT"
__internal_name__ = "stoffi-s-mapper"

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QListWidget, QRadioButton, QFrame, QMessageBox,
    QSystemTrayIcon, QMenu, QDoubleSpinBox, QScrollArea
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QMutex, QMutexLocker, QTimer, QEvent
from PyQt6.QtGui import QCursor, QIcon, QAction
from pynput import mouse, keyboard
import threading
import pygetwindow as gw
from pynput.keyboard import Key

# Optional low-level keyboard interception via the 'keyboard' package.
# We import lazily and safely since the user may not have it installed.
try:
    import keyboard as kbd  # type: ignore
    _KBD_AVAILABLE = True
except Exception:
    kbd = None
    _KBD_AVAILABLE = False


def _check_admin_windows() -> bool:
    """Return True if the current process is running elevated (Windows).

    This uses ctypes.windll.shell32.IsUserAnAdmin which returns a non-zero
    value when running elevated. Wrap in try/except to avoid import-time
    errors in environments where ctypes/win32 APIs are restricted.
    """
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _check_admin_unix() -> bool:
    """Return True if the current process is running as root on UNIX-like OSes."""
    try:
        return os.geteuid() == 0
    except Exception:
        return False


def is_running_as_admin() -> bool:
    """Cross-platform check whether the current process is elevated/privileged.

    Returns True on Windows when running elevated, and True on Unix when
    running as root. Fails safe and returns False on unexpected errors.
    """
    if os.name == 'nt':
        return _check_admin_windows()
    return _check_admin_unix()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Fall back to the directory containing this file which is the
        # correct resource location during development (avoids relying
        # on the current working directory which can vary).
        base_path = os.path.abspath(os.path.dirname(__file__))

    return os.path.join(base_path, relative_path)

class KeyboardListenerThread(QThread):
    """
    A QThread that runs the pynput keyboard listener.
    """
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

class MouseListenerThread(QThread):
    """
    A QThread that runs the pynput mouse listener.
    """
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

class PingStatusLabel(QLabel):
    """
    A frameless, floating QLabel used to display ping status near the cursor.
    """
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool  # Prevents it from appearing in the taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 5px;")

    def show_message(self, text, color, position):
        self.setText(text)
        self.setStyleSheet(f"color: {color}; font-size: 14pt; font-weight: bold; padding: 5px; background-color: rgba(20, 20, 20, 0.7); border-radius: 5px;")
        self.adjustSize()
        # Position it above the cursor, slightly to the right
        self.move(position.x() + 10, position.y() - self.height())
        self.show()

class PingThread(QThread):
    """
    A QThread that runs a ping command and emits the result.
    """
    ping_result = pyqtSignal(str)

    def __init__(self, ip_address):
        super().__init__()
        self.ip_address = ip_address

    def run(self):
        try:
            # The command for Windows
            command = ['ping', '-n', '4', self.ip_address]
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            output = result.stdout.lower()
            if "received = 0" in output or "100% loss" in output:
                self.ping_result.emit('red')
            else:
                self.ping_result.emit('green')

        except Exception as e:
            print(f"Ping failed: {e}")
            self.ping_result.emit('red')

class KeyMapperApp(QWidget):
    # Signal used to run mapping actions on the main (GUI) thread. Emitting
    # this from the listener thread queues the action onto the Qt event loop
    # where the single shared keyboard Controller owned by the app will
    # perform the key presses reliably.
    mapping_action_signal = pyqtSignal(object)
    def __init__(self):
        super().__init__()
        self.ping_status_label = PingStatusLabel()
        self.mappings_lock = QMutex()
        self.keyboard_controller = keyboard.Controller()
        self.mappings = {}
        self.mapping_ids = []
        self.mapping_counter = 1
        self.last_click_time = {}
        self.click_counts = {}
        # How long between clicks counts as a separate sequence (seconds)
        # Defaults to 0.6s (configurable via UI)
        self.click_interval = 0.6
        # Optional in-memory guards for synthetic key events and low-level hooks
        # (_kbd_available reflects whether the optional 'keyboard' package
        # is available on the system).
        self._ignore_keys = {}
        self._kbd_available = _KBD_AVAILABLE
        self._keyboard_hooks = {}  # map source_key -> handler from 'keyboard' package
        self._kbd_ignore = {}
        # fast lookup table: source_key -> list of mapping details
        # (window_title, target_key) to avoid iterating full mapping set
        # on every key event.
        self._source_index = {}
        # runtime flag: low-level keyboard suppression enabled at startup
        # only available when keyboard package is installed
        self._kbd_enabled = bool(self._kbd_available)
        self.initUI()
        self.load_mappings_from_config()
        # Connect mapping action signal -> handler which runs on main thread
        self.mapping_action_signal.connect(self._handle_mapping_action)
        self.start_listeners()

        # Cache of active window title to avoid expensive per-key calls to
        # pygetwindow in tight keyboard hook loops. Updated periodically on
        # the GUI thread; keyboard hook reads it under a simple lock.
        self._cached_active_title = ""
        self._active_title_lock = threading.Lock()
        # Start a short QTimer that updates the cached active window title.
        # 100ms is a good balance between freshness and overhead.
        self._active_title_timer = QTimer(self)
        self._active_title_timer.setInterval(100)
        self._active_title_timer.timeout.connect(self._update_cached_active_title)
        self._active_title_timer.start()

    def initUI(self):
        self.setWindowTitle("S-Mapper")
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.setGeometry(100, 100, 800, 800)

        # Dark mode stylesheet
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-size: 10pt;
            }
            QScrollArea {
                border: none;
            }
            QComboBox {
                background-color: #252526;
                border: 1px solid #3a3d41;
                padding: 5px;
                selection-background-color: #007acc;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                selection-background-color: #007acc;
                border: 1px solid #3a3d41;
            }
            QComboBox::drop-down {
                border: none;
            }
            QLineEdit {
                background-color: #252526;
                border: 1px solid #3a3d41;
                padding: 5px;
                selection-background-color: #007acc;
            }
            QPushButton {
                background-color: #3a3d41;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #4a4d51;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
            QListWidget {
                background-color: #252526;
                border: 1px solid #3a3d41;
                selection-background-color: #007acc;
            }
            QRadioButton {
                color: #888888;
            }
        """)

        # Main layout for the entire window
        main_layout = QVBoxLayout(self)
        self.setLayout(main_layout)

        # Scroll area to contain the main content
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        # Container widget for the scroll area's content
        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        # This is the layout that will hold all your UI components
        layout = QVBoxLayout(scroll_content)
        scroll_content.setLayout(layout)

        # --- UI Components ---

        layout.addWidget(QLabel("Configure Mouse to Keyboard Mappings"))

        # Mouse Button
        layout.addWidget(QLabel("Mouse Button:"))
        self.mouse_button_combobox = QComboBox()
        self.mouse_button_combobox.addItems(['', 'left', 'right', 'middle', 'x1', 'x2'])
        layout.addWidget(self.mouse_button_combobox)

        # Press Count
        layout.addWidget(QLabel("Number of Presses:"))
        self.press_count_entry = QLineEdit()
        layout.addWidget(self.press_count_entry)

        # Click interval (double spin) — lets the user tune how fast clicks
        # must occur to be considered a multi-press mapping.
        interval_frame = QHBoxLayout()
        interval_frame.addWidget(QLabel("Double-click window (sec):"))
        self.click_interval_spinbox = QDoubleSpinBox()
        self.click_interval_spinbox.setRange(0.05, 5.0)
        self.click_interval_spinbox.setSingleStep(0.05)
        self.click_interval_spinbox.setDecimals(2)
        self.click_interval_spinbox.setValue(self.click_interval)
        self.click_interval_spinbox.setToolTip("Maximum time between consecutive clicks for them to count as one mapping (seconds)")
        interval_frame.addWidget(self.click_interval_spinbox)
        layout.addLayout(interval_frame)

        # Source Key
        self.source_key_label = QLabel("Source Keyboard Key:")
        layout.addWidget(self.source_key_label)
        self.keyboard_keys = [
            '', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
            'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
            '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
            'enter', 'esc', 'space', 'shift', 'ctrl', 'alt', 'tab', 'backspace', 'delete',
            'up', 'down', 'left', 'right',
            'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
            '!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '-', '=', '[', ']', '\\',
            ';', "'", ',', '.', '/', '`', '~', '{', '}', '|', ':', '"', '<', '>', '?',
            '§', '´', '¨', '±', 'ä', 'å', 'ö', 'ø', 'æ'
        ]
        self.source_keyboard_combobox = QComboBox()
        self.source_keyboard_combobox.addItems(self.keyboard_keys)
        layout.addWidget(self.source_keyboard_combobox)
        
        # Target Key
        layout.addWidget(QLabel("Target Keyboard Key:"))
        self.target_keyboard_combobox = QComboBox()
        self.target_keyboard_combobox.addItems(self.keyboard_keys)
        layout.addWidget(self.target_keyboard_combobox)

        # Modifier
        layout.addWidget(QLabel("Modifier Key:"))
        self.modifier_key_combobox = QComboBox()
        self.modifier_key_combobox.addItems(['', 'ctrl', 'alt', 'shift', 'ctrl + alt', 'ctrl + shift', 'alt + shift'])
        layout.addWidget(self.modifier_key_combobox)

        # Target Window
        layout.addWidget(QLabel("Select Target Window:"))
        self.window_selection_var_group = QVBoxLayout()
        self.window_selection_radio1 = QRadioButton("Free Text (Partial Match)")
        self.window_selection_radio1.setChecked(True)
        self.window_selection_radio2 = QRadioButton("Select from Active Windows")
        self.window_selection_var_group.addWidget(self.window_selection_radio1)
        self.window_selection_var_group.addWidget(self.window_selection_radio2)
        layout.addLayout(self.window_selection_var_group)

        window_frame = QFrame()
        window_frame_layout = QHBoxLayout()
        window_frame.setLayout(window_frame_layout)
        self.window_selection_entry = QLineEdit()
        self.window_selection_combobox = QComboBox()
        window_frame_layout.addWidget(self.window_selection_entry)
        window_frame_layout.addWidget(self.window_selection_combobox)
        layout.addWidget(window_frame)
        self.refresh_window_list()

        # Buttons
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Mapping")
        self.remove_button = QPushButton("Remove Selected")
        self.refresh_button = QPushButton("Refresh Windows")
        self.clear_button = QPushButton("Clear Fields")
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.clear_button)
        layout.addLayout(button_layout)

        # Mappings List
        self.mappings_listbox = QListWidget()
        layout.addWidget(self.mappings_listbox)

        # --- IP Ping Monitor UI ---
        ip_monitor_frame = QFrame()
        ip_monitor_frame.setFrameShape(QFrame.Shape.StyledPanel)
        ip_monitor_layout = QVBoxLayout()
        ip_monitor_frame.setLayout(ip_monitor_layout)
        
        ip_monitor_layout.addWidget(QLabel("Clipboard IP Ping Monitor"))
        
        ip_monitor_hbox = QHBoxLayout()
        ip_monitor_hbox.addWidget(QLabel("Target Window Contains:"))
        self.ip_monitor_window_entry = QLineEdit()
        ip_monitor_hbox.addWidget(self.ip_monitor_window_entry)

        self.ping_status_indicator = QLabel()
        self.ping_status_indicator.setFixedSize(20, 20)
        self.ping_status_indicator.setStyleSheet("background-color: #555; border-radius: 10px;")
        ip_monitor_hbox.addWidget(self.ping_status_indicator)
        ip_monitor_layout.addLayout(ip_monitor_hbox)

        self.ip_monitor_toggle_button = QPushButton("Start Monitoring")
        self.ip_monitor_toggle_button.setCheckable(True)
        ip_monitor_layout.addWidget(self.ip_monitor_toggle_button)

        # A small UI toggle to enable/disable the optional low-level
        # keyboard suppression. Only shown when the 'keyboard' package
        # is present in the environment.
        try:
            from PyQt6.QtWidgets import QCheckBox
            # Add a status label that explains whether the optional low-level
            # suppression is available (keyboard package bundled) and whether
            # the process has the elevated privileges required to perform
            # global low-level hooks reliably.
            self._is_admin = is_running_as_admin()
            self.kbd_status_label = QLabel()

            if self._kbd_available:
                # Only show the toggle when the package is installed. If the
                # app is not elevated, show the checkbox disabled with an
                # explanation so the user knows to use the elevated build.
                self.kbd_suppression_checkbox = QCheckBox("Enable low-level suppression (keyboard package)")
                self.kbd_suppression_checkbox.setChecked(self._kbd_enabled)
                self.kbd_suppression_checkbox.toggled.connect(self._on_kbd_suppression_toggled)

                if not self._is_admin:
                    # Allow toggling the checkbox even when not elevated. Some
                    # systems can still install hooks without admin; the enable
                    # attempt will validate at runtime and present a friendly
                    # warning on failure. Provide a tooltip explaining the
                    # potential limitation rather than disabling the UI.
                    self.kbd_status_label.setText("Low-level suppression available — app not elevated. Enabling may still work but could require administrator privileges.")
                    self.kbd_status_label.setStyleSheet('color: #f39c12;')
                    self.kbd_suppression_checkbox.setToolTip("May require elevated privileges to fully work on some systems; enabling will attempt to install hooks and will warn on failure.")
                else:
                    self.kbd_status_label.setText("Low-level suppression available — running elevated.")
                    self.kbd_status_label.setStyleSheet('color: #8bc34a;')

                ip_monitor_layout.addWidget(self.kbd_suppression_checkbox)
                ip_monitor_layout.addWidget(self.kbd_status_label)

            else:
                # keyboard package not present; show a helpful message and
                # keep the checkbox reference None for backwards compatibility.
                self.kbd_suppression_checkbox = None
                self.kbd_status_label.setText("Low-level suppression unavailable — 'keyboard' package not bundled. Use the 'full' build to enable.")
                self.kbd_status_label.setStyleSheet('color: #e74c3c;')
                ip_monitor_layout.addWidget(self.kbd_status_label)
        except Exception:
            # If for some reason QCheckBox isn't available, fall back
            # to not showing the toggle.
            self.kbd_suppression_checkbox = None

        layout.addWidget(ip_monitor_frame)
        
        # --- Connections ---
        self.add_button.clicked.connect(self.add_mapping)
        self.remove_button.clicked.connect(self.remove_mapping)
        self.refresh_button.clicked.connect(self.refresh_window_list)
        self.clear_button.clicked.connect(self.clear)
        self.mouse_button_combobox.currentTextChanged.connect(self.on_combobox_selected)
        self.source_keyboard_combobox.currentTextChanged.connect(self.on_combobox_selected)
        self.window_selection_radio1.toggled.connect(self.update_window_selection_visibility)
        self.ip_monitor_toggle_button.toggled.connect(self.toggle_ip_monitoring)
        self.click_interval_spinbox.valueChanged.connect(self._on_interval_changed)
        
        # Clipboard monitoring setup
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.on_clipboard_change)

        # Set initial visibility
        self.update_window_selection_visibility()

        # --- System Tray Icon ---
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(resource_path('icon.png')))
        self.tray_icon.setToolTip("S-Mapper App")

        tray_menu = QMenu()
        show_action = QAction("Show", self)
        quit_action = QAction("Exit", self)

        show_action.triggered.connect(self.show_window)
        quit_action.triggered.connect(self.close)

        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def start_listeners(self):
        self.keyboard_thread = KeyboardListenerThread(self)
        self.keyboard_thread.start()
        self.mouse_thread = MouseListenerThread(self)
        self.mouse_thread.start()
        # If keyboard package-based low-level suppression is available,
        # ensure handlers are registered now (best-effort).
        if self._kbd_available and getattr(self, '_kbd_enabled', False):
            try:
                self._refresh_keyboard_hooks()
            except Exception:
                pass

    def update_label_position(self, x, y):
        if self.ping_status_label.isVisible():
            # Position it above the cursor, slightly to the right
            self.ping_status_label.move(x + 10, y - self.ping_status_label.height())

    def _update_cached_active_title(self):
        """Periodically run on the GUI thread to update the cached active
        window title. The keyboard hook reads the cached value under a lock
        to minimize expensive calls to pygetwindow in the handler path.
        """
        try:
            w = gw.getActiveWindow()
            title = w.title if (w and w.title) else ""
        except Exception:
            title = ""

        # store a lower-cased title to simplify case-insensitive matching
        tnorm = title.strip().lower()
        # Detect changes so we only refresh hooks when the active window actually changed
        with self._active_title_lock:
            old = self._cached_active_title
            self._cached_active_title = tnorm

        if tnorm != old and self._kbd_available and getattr(self, '_kbd_enabled', False):
            try:
                # Update keyboard hooks for the new active title
                self._update_hooks_for_active_title(tnorm)
            except Exception:
                pass

    def toggle_ip_monitoring(self, checked):
        if checked:
            self.ip_monitor_toggle_button.setText("Stop Monitoring")
            # Logic to start monitoring can be placed here if needed
        else:
            self.ip_monitor_toggle_button.setText("Start Monitoring")
            # Logic to stop monitoring can be placed here if needed

    def on_clipboard_change(self):
        if not self.ip_monitor_toggle_button.isChecked():
            return

        target_window_text = self.ip_monitor_window_entry.text()
        active_window = gw.getActiveWindow()

        if not target_window_text or not active_window or target_window_text.lower() not in active_window.title.lower():
            return

        clipboard_text = self.clipboard.text()
        # Regex to validate an IPv4 address
        ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
        
        if re.match(ip_pattern, clipboard_text):
            self.ping_status_indicator.setStyleSheet("background-color: #f0ad4e; border-radius: 10px;") # Yellow for "in progress"
            cursor_pos = QCursor.pos()
            self.ping_status_label.show_message("Ping sent...", "#FFA500", cursor_pos) # Orange
            self.mouse_thread.mouse_moved.connect(self.update_label_position)
            self.ping_thread = PingThread(clipboard_text)
            self.ping_thread.ping_result.connect(self.update_ping_indicator)
            self.ping_thread.start()

    def update_ping_indicator(self, color):
        self.ping_status_indicator.setStyleSheet(f"background-color: {color}; border-radius: 10px;")
        cursor_pos = QCursor.pos()
        if color == 'red':
            self.ping_status_label.show_message("Ping failed", "red", cursor_pos)
        else:
            self.ping_status_label.show_message("Ping succeeded", "green", cursor_pos)

        # Hide floating label and disconnect listener after 1 second
        QTimer.singleShot(1000, self.hide_ping_status_and_disconnect)
        # Reset indicator light after 5 seconds
        QTimer.singleShot(5000, lambda: self.ping_status_indicator.setStyleSheet("background-color: #555; border-radius: 10px;"))

    def hide_ping_status_and_disconnect(self):
        self.ping_status_label.hide()
        try:
            self.mouse_thread.mouse_moved.disconnect(self.update_label_position)
        except TypeError:
            # Signal was not connected, which is fine.
            pass

    def refresh_window_list(self):
        self.window_selection_combobox.clear()
        windows = gw.getWindowsWithTitle('')
        window_titles = [window.title for window in windows if window.title]
        self.window_selection_combobox.addItems(window_titles)

    def clear(self):
        self.mouse_button_combobox.setCurrentIndex(0)
        self.press_count_entry.clear()
        self.target_keyboard_combobox.setCurrentIndex(0)
        self.modifier_key_combobox.setCurrentIndex(0)
        self.window_selection_entry.clear()
        self.window_selection_combobox.setCurrentIndex(-1)
        self.source_keyboard_combobox.setCurrentIndex(0)
        self.on_combobox_selected()

    def on_combobox_selected(self):
        mouse_button_value = self.mouse_button_combobox.currentText()
        source_key_value = self.source_keyboard_combobox.currentText()

        if mouse_button_value:
            self.source_keyboard_combobox.setEnabled(False)
            self.source_key_label.setEnabled(False)
        else:
            self.source_keyboard_combobox.setEnabled(True)
            self.source_key_label.setEnabled(True)

        if source_key_value:
            self.mouse_button_combobox.setEnabled(False)
            self.press_count_entry.setEnabled(False)
        else:
            self.mouse_button_combobox.setEnabled(True)
            self.press_count_entry.setEnabled(True)

    def update_window_selection_visibility(self):
        if self.window_selection_radio1.isChecked():
            self.window_selection_entry.setVisible(True)
            self.window_selection_combobox.setVisible(False)
        else:
            self.window_selection_entry.setVisible(False)
            self.window_selection_combobox.setVisible(True)

    def _on_kbd_suppression_toggled(self, checked: bool):
        """Enable or disable low-level keyboard suppression at runtime.
        When enabled we register hooks for all current mappings; when
        disabled we unhook them so the normal pynput on_press handling
        resumes.
        """
        # Try to enable/disable low-level suppression even when not elevated.
        # Some environments will allow the hooks to be installed without
        # administrative rights; attempt to install and if it fails notify the
        # user and fall back to the high-level path without crashing.
        self._kbd_enabled = bool(checked)

        if self._kbd_available and self._kbd_enabled:
            try:
                # Attempt to create hooks. This may fail for lack of
                # privileges or platform restrictions — surface a friendly
                # warning to the user but keep the app running.
                self._refresh_keyboard_hooks()
                # Update status to show enabled (if we have a label)
                try:
                    self.kbd_status_label.setText("Low-level suppression enabled.")
                    self.kbd_status_label.setStyleSheet('color: #8bc34a;')
                except Exception:
                    pass
            except Exception as e:
                # Failed to enable. Revert the toggle and notify user.
                self._kbd_enabled = False
                try:
                    if self.kbd_suppression_checkbox:
                        self.kbd_suppression_checkbox.setChecked(False)
                except Exception:
                    pass

                try:
                    QMessageBox.warning(self, "Enable failed", f"Failed to enable low-level suppression: {e}\nThe app will continue using high-level listeners.")
                except Exception:
                    # If QMessageBox cannot be shown (tests/headless), ignore
                    pass

                try:
                    self.kbd_status_label.setText("Low-level suppression failed to enable. Using high-level listeners.")
                    self.kbd_status_label.setStyleSheet('color: #e67e22;')
                except Exception:
                    pass
        else:
            try:
                # When disabling, unhook any active keyboard hooks
                self._unhook_all_keyboard_hooks()
            except Exception:
                pass
            try:
                self.kbd_status_label.setText("Low-level suppression disabled.")
                self.kbd_status_label.setStyleSheet('color: #888888;')
            except Exception:
                pass

    def add_mapping(self):
        source_key = self.source_keyboard_combobox.currentText()
        mouse_button = self.mouse_button_combobox.currentText()
        if source_key:
            self.add_keyboard_mapping()
        elif mouse_button:
            self.add_mouse_mapping()
        else:
            QMessageBox.warning(self, "Input Error", "Please select a trigger key or button.")

    def add_mouse_mapping(self):
        locker = QMutexLocker(self.mappings_lock)
        mouse_button = self.mouse_button_combobox.currentText()
        try:
            press_count = int(self.press_count_entry.text())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid press count. Please enter a number.")
            return
        
        keyboard_button = self.target_keyboard_combobox.currentText()

        if self.window_selection_radio1.isChecked():
            target_window = self.window_selection_entry.text()
        else:
            target_window = self.window_selection_combobox.currentText()

        if not all([mouse_button, keyboard_button, target_window]):
            QMessageBox.warning(self, "Input Error", "Please fill all required fields.")
            return

        modifier_key = self.modifier_key_combobox.currentText()
        if modifier_key:
            keyboard_button = f"{modifier_key} + {keyboard_button}"

        mapping_id = f"Mapping {self.mapping_counter}"
        self.mapping_counter += 1

        if target_window not in self.mappings:
            self.mappings[target_window] = {}

        final_key = keyboard_button
        if keyboard_button.startswith('f') and keyboard_button[1:].isdigit():
            final_key = getattr(Key, keyboard_button.lower(), keyboard_button)

        self.mappings[target_window][mapping_id] = {
            'mouse_button': mouse_button,
            'press_count': press_count,
            'keyboard_button': final_key,
            'window_title': target_window
        }
        self.mapping_ids.append(mapping_id)
        self.update_mappings_display()
        # Keep low-level hooks in sync when present
        if self._kbd_available and getattr(self, '_kbd_enabled', False):
            try:
                self._refresh_keyboard_hooks()
            except Exception:
                pass
        self.clear()

    def add_keyboard_mapping(self):
        locker = QMutexLocker(self.mappings_lock)
        source_key = self.source_keyboard_combobox.currentText()
        target_key = self.target_keyboard_combobox.currentText()

        if self.window_selection_radio1.isChecked():
            target_window = self.window_selection_entry.text()
        else:
            target_window = self.window_selection_combobox.currentText()

        if not all([source_key, target_key, target_window]):
            QMessageBox.warning(self, "Input Error", "Please fill all required fields.")
            return
        
        modifier_key = self.modifier_key_combobox.currentText()
        if modifier_key:
            target_key = f"{modifier_key} + {target_key}"

        mapping_id = f"Mapping {self.mapping_counter}"
        self.mapping_counter += 1

        if target_window not in self.mappings:
            self.mappings[target_window] = {}
        
        self.mappings[target_window][mapping_id] = {
            'source_key': source_key,
            'target_key': target_key,
            'window_title': target_window
        }
        self.mapping_ids.append(mapping_id)
        self.update_mappings_display()
        if self._kbd_available and getattr(self, '_kbd_enabled', False):
            try:
                self._refresh_keyboard_hooks()
            except Exception:
                pass
        self.clear()
        
    def remove_mapping(self):
        locker = QMutexLocker(self.mappings_lock)
        selected_item = self.mappings_listbox.currentItem()
        if not selected_item:
            return
        
        selected_index = self.mappings_listbox.row(selected_item)
        mapping_id = self.mapping_ids.pop(selected_index)

        for target_window in self.mappings:
            if mapping_id in self.mappings[target_window]:
                del self.mappings[target_window][mapping_id]
                break
        
        self.update_mappings_display()
        # Update low-level hooks if suppression is enabled
        if self._kbd_available and getattr(self, '_kbd_enabled', False):
            try:
                self._refresh_keyboard_hooks()
            except Exception:
                pass

    def update_mappings_display(self):
        self.mappings_listbox.clear()
        
        temp_id_list = []
        for target_window, mappings in self.mappings.items():
            for mapping_id, details in mappings.items():
                if not details: continue
                
                temp_id_list.append(mapping_id)
                display_text = ""
                if 'source_key' in details:
                    display_text = (f"[{target_window}] Source: {details['source_key']} -> "
                                    f"Target: {details['target_key']}")
                elif 'mouse_button' in details:
                    kb_button_str = details['keyboard_button']
                    if isinstance(kb_button_str, Key):
                        kb_button_str = kb_button_str.name
                    display_text = (f"[{target_window}] Mouse: {details['mouse_button']} "
                                    f"x{details['press_count']} -> Keyboard: {kb_button_str}")
                self.mappings_listbox.addItem(display_text)
        self.mapping_ids = temp_id_list


    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # Left click
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.activateWindow()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                self.hide()
                self.tray_icon.showMessage(
                    "S-Mapper",
                    "Application was minimized to tray.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        super().changeEvent(event)

    def on_press(self, key):
        locker = QMutexLocker(self.mappings_lock)
        try:
            # When using the low-level keyboard hooks we register separate
            # handlers and suppress the original event, so skip the
            # pynput on_press mapping behavior to avoid duplication.
            if self._kbd_available and getattr(self, '_kbd_enabled', False):
                return
            pressed_key = key.char if isinstance(key, keyboard.KeyCode) else key.name
            current_window = gw.getActiveWindow()
            if not pressed_key or not current_window:
                return

            current_window_title = current_window.title
            
            for window_title, mappings in self.mappings.items():
                if window_title in current_window_title:
                    for details in mappings.values():
                        if 'source_key' in details and details['source_key'] == pressed_key:
                            self.mapping_action_signal.emit(details['target_key'])
                            return
        except (AttributeError, KeyError, ValueError):
            pass

    def on_click(self, x, y, button, pressed):
        locker = QMutexLocker(self.mappings_lock)
        if not pressed:
            # We only care about press events
            return

        active_window = gw.getActiveWindow()
        if not active_window:
            return

        button_name = button.name
        current_time = time.time()

        self.click_counts.setdefault(button_name, 0)

        last_click = self.last_click_time.get(button_name)
        if last_click and (current_time - last_click) > self.click_interval:
            self.click_counts[button_name] = 0
        
        self.click_counts[button_name] += 1
        self.last_click_time[button_name] = current_time

        target_window_title = active_window.title

        # Find a matching mapping while holding the lock briefly, but don't
        # perform the keyboard action inside the listener thread to avoid
        # blocking the mouse listener. Instead collect action details and
        # run them on a background thread.
        action_to_run = None

        for partial_title, mappings in self.mappings.items():
            if partial_title in target_window_title:
                for details in mappings.values():
                    if 'mouse_button' not in details:
                        continue

                    if (details['mouse_button'] == button_name and
                            details['press_count'] == self.click_counts[button_name]):

                        # Reset click counter inside the lock quickly so any
                        # subsequent clicks don't interfere.
                        self.click_counts[button_name] = 0
                        action_to_run = details['keyboard_button']
                        break

                if action_to_run:
                    break

        # release the lock (QMutexLocker destructor on function exit)

        if not action_to_run:
            return

        # Run the actual keyboard press on a separate, short-lived thread
        # so we don't block the mouse listener.
        # Use Qt signal to queue action to main thread. This avoids
        # the timing/focus problems that can happen when actions run in
        # independent worker threads, and keeps the listener non-blocking.
        self.mapping_action_signal.emit(action_to_run)

    def _get_config_filepath(self):
        """
        Returns the platform-specific, user-writable path for the mappings.ini file.
        """
        # Use LOCALAPPDATA for Windows, which is the correct place for user-specific config.
        app_data_path = os.environ.get('LOCALAPPDATA')
        if not app_data_path:
            # Fallback for unusual cases, though LOCALAPPDATA is standard on Windows.
            return 'mappings.ini'

        config_dir = os.path.join(app_data_path, 'S-Mapper')
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, 'mappings.ini')

    def save_mappings_to_config(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        
        locker = QMutexLocker(self.mappings_lock)

        all_mappings = {}
        for mappings_by_window in self.mappings.values():
            all_mappings.update(mappings_by_window)

        # Persist application settings in a dedicated section so the
        # click interval is preserved between runs.
        config['Settings'] = {}
        config['Settings']['click_interval'] = str(self.click_interval)

        for mapping_id, details in all_mappings.items():
            config[mapping_id] = {}
            section = config[mapping_id]
            section['window_title'] = details.get('window_title', '')

            if 'mouse_button' in details:
                section['type'] = 'mouse'
                section['mouse_button'] = details['mouse_button']
                section['press_count'] = str(details['press_count'])
                
                kb_button = details['keyboard_button']
                if isinstance(kb_button, Key):
                    kb_button = f"Key.{kb_button.name}"
                section['target_key'] = kb_button
            
            elif 'source_key' in details:
                section['type'] = 'keyboard'
                section['source_key'] = details['source_key']
                section['target_key'] = details['target_key']

        with open(self._get_config_filepath(), 'w') as configfile:
            config.write(configfile)

    def _run_keyboard_action_worker(self, keyboard_button):
        """
        Worker used to execute keyboard press/release for a mapping off the
        listener thread. Using a local Controller instance is safer and keeps
        the listener responsive.
        """
        try:
            # Use a dedicated Controller instance in this thread
            local_controller = keyboard.Controller()

            # Convert Key objects to their name string if necessary
            if isinstance(keyboard_button, Key):
                kb_button_str = keyboard_button.name
            else:
                kb_button_str = keyboard_button

            # Parse modifiers and the main key
            parts = kb_button_str.split(' + ')
            key_to_press_str = parts[-1].strip()
            modifiers_str = [p.strip() for p in parts[:-1] if p.strip()]

            key_to_press = getattr(Key, key_to_press_str, key_to_press_str)
            modifier_keys = [getattr(Key, m) for m in modifiers_str]

            if modifier_keys:
                with local_controller.pressed(*modifier_keys):
                    local_controller.press(key_to_press)
                    local_controller.release(key_to_press)
            else:
                local_controller.press(key_to_press)
                local_controller.release(key_to_press)

        except Exception as e:
            # Keep logs minimal to avoid spamming the listener thread.
            print(f"Mapping action failed: {e}")

    def _handle_mapping_action(self, keyboard_button):
        """
        Slot executed on the GUI thread (via mapping_action_signal) that
        runs the keyboard action using the shared controller. This keeps
        key injection consistent with the app's main controller.
        """
        try:
            # Use the shared controller already created by the app
            kb_button = keyboard_button
            if isinstance(kb_button, Key):
                kb_button_str = kb_button.name
            else:
                kb_button_str = kb_button

            parts = kb_button_str.split(' + ')
            key_to_press_str = parts[-1].strip()
            modifiers_str = [p.strip() for p in parts[:-1] if p.strip()]

            key_to_press = getattr(Key, key_to_press_str, key_to_press_str)
            modifier_keys = [getattr(Key, m) for m in modifiers_str]

            if modifier_keys:
                with self.keyboard_controller.pressed(*modifier_keys):
                    self.keyboard_controller.press(key_to_press)
                    self.keyboard_controller.release(key_to_press)
            else:
                self.keyboard_controller.press(key_to_press)
                self.keyboard_controller.release(key_to_press)

        except Exception as e:
            print(f"Mapping action failed (main thread): {e}")

    def load_mappings_from_config(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        
        config_path = self._get_config_filepath()
        if not os.path.exists(config_path):
            try:
                # Create an empty file so the app can save to it later.
                with open(config_path, 'w') as configfile:
                    pass
                return # Stop here since there's nothing to load
            except IOError as e:
                QMessageBox.critical(self, "File Creation Error", f"Failed to create {config_path}: {e}")
                return

        config.read(config_path)
        highest_mapping_number = 0

        locker = QMutexLocker(self.mappings_lock)
        self.mappings.clear()
        self.mapping_ids.clear()

        for section_name in config.sections():
            if section_name == 'DEFAULT':
                continue

            try:
                mapping_id = section_name
                details = {}
                config_section = config[section_name]
                
                mapping_type = config_section.get('type')
                target_window = config_section.get('window_title', '')
                details['window_title'] = target_window

                if mapping_type == 'mouse':
                    details['mouse_button'] = config_section.get('mouse_button')
                    details['press_count'] = config_section.getint('press_count')
                    kb_button_str = config_section.get('target_key')
                    
                    if kb_button_str.startswith('Key.'):
                        key_name = kb_button_str.split('.', 1)[1]
                        details['keyboard_button'] = getattr(Key, key_name, key_name)
                    else:
                        details['keyboard_button'] = kb_button_str

                elif mapping_type == 'keyboard':
                    details['source_key'] = config_section.get('source_key')
                    details['target_key'] = config_section.get('target_key')

                else:
                    continue

                if target_window not in self.mappings:
                    self.mappings[target_window] = {}
                
                self.mappings[target_window][mapping_id] = details
                self.mapping_ids.append(mapping_id)

                num_part = mapping_id.split()[-1]
                if num_part.isdigit():
                    mapping_number = int(num_part)
                    if mapping_number > highest_mapping_number:
                        highest_mapping_number = mapping_number
            
            except (configparser.NoOptionError, ValueError, IndexError) as e:
                print(f"Skipping malformed or incomplete section {section_name}: {e}")
                continue

        self.mapping_counter = highest_mapping_number + 1
        self.update_mappings_display()

        # Sync low-level hooks after loading mappings from disk
        if self._kbd_available and getattr(self, '_kbd_enabled', False):
            try:
                self._refresh_keyboard_hooks()
            except Exception:
                pass

        # Load click interval from settings if present
        try:
            if config.has_section('Settings') and config['Settings'].get('click_interval'):
                val = float(config['Settings'].get('click_interval'))
                # clamp to reasonable bounds
                self.click_interval = max(0.05, min(5.0, val))
                # update UI spinbox if available
                try:
                    self.click_interval_spinbox.setValue(self.click_interval)
                except Exception:
                    pass
        except Exception:
            # Fail silently — incorrect value shouldn't crash loading
            pass

    def _on_interval_changed(self, value: float):
        # Called when the UI spinbox changes; keep internal state in sync
        try:
            self.click_interval = float(value)
        except Exception:
            pass

    # --------------------- keyboard package integration -----------------
    def _refresh_keyboard_hooks(self):
        """
        Register per-source-key keyboard hooks using the 'keyboard'
        package. Hooks are installed with suppress=True so the original
        key press will not be delivered to the OS when it matches a
        configured mapping.
        """
        if not self._kbd_available:
            return

        # Build a fast lookup: source_key -> list of (window_title, target_key)
        # so callbacks don't need to iterate the entire mapping set each time.
        source_keys = set()
        self._source_index.clear()
        for mappings in self.mappings.values():
            for details in mappings.values():
                if 'source_key' in details and details['source_key']:
                    sk = details['source_key']
                    source_keys.add(sk)
                    self._source_index.setdefault(sk, []).append(
                        (details.get('window_title', ''), details.get('target_key'))
                    )

        # After rebuilding the index, update hooks to match the current
        # active window title (so only keys targeted to the current
        # app are intercepted).
        # First, remove hooks that no longer correspond to any known keys
        for k in list(self._keyboard_hooks.keys()):
            if k not in source_keys:
                try:
                    kbd.unhook(self._keyboard_hooks[k])
                except Exception:
                    pass
                del self._keyboard_hooks[k]

        # Now build an index of active keys for the current active title and
        # ensure hooks are only installed for those.
        with self._active_title_lock:
            active_title = self._cached_active_title

        # Only update hooks for keys that match the active title.
        self._update_hooks_for_active_title(active_title)
        return

    def _update_hooks_for_active_title(self, active_title: str):
        """
        Ensure that low-level keyboard hooks are installed only for
        source keys which have mappings that match the provided
        active_title. This is fast and runs on the GUI thread.
        """
        if not self._kbd_available or not getattr(self, '_kbd_enabled', False):
            return

        # Compute keys that match the active title
        active_keys = set()
        if active_title:
            for sk, bucket in self._source_index.items():
                for (w_title, _) in bucket:
                    if w_title and (w_title.strip().lower() in active_title):
                        active_keys.add(sk)
                        break

        # Add hooks for newly active keys
        for key in active_keys:
            if key in self._keyboard_hooks:
                continue

            # create a stable callback closure
            def make_callback(src_key):
                def callback(event):
                    # only handle key down
                    if event.event_type != 'down':
                        return

                    # periodically clean up expired ignore entries
                    now = time.time()
                    to_delete = [n for n, t in self._kbd_ignore.items() if t < now]
                    for n in to_delete:
                        del self._kbd_ignore[n]

                    # If this press was caused by our own synthetic
                    # input, ignore it here.
                    if event.name in self._kbd_ignore:
                        return

                    # Quick safety: if any modifier key is held down
                    # (ctrl/alt/shift/windows/meta) we SHOULD NOT
                    # intercept this press — let hotkeys like Ctrl+C
                    # behave normally. Re-send the original key so the
                    # suppressed hardware event is delivered.
                    try:
                        if any(kbd.is_pressed(m) for m in ('ctrl', 'shift', 'alt', 'win', 'windows', 'meta', 'cmd')):
                            # short ignore to avoid loop when re-sending
                            expiry2 = time.time() + 0.25
                            self._kbd_ignore[event.name] = expiry2
                            kbd.send(event.name)
                            return
                    except Exception:
                        # If checking modifier state fails for any reason
                        # fall back to existing behavior and continue.
                        pass

                    # Use the cached active window title (updated periodically
                    # on the GUI thread) instead of calling getActiveWindow()
                    # inside the hot path.
                    with self._active_title_lock:
                        title = self._cached_active_title
                    if not title:
                        return

                    # Look up matching mappings for this source key only
                    bucket = self._source_index.get(src_key, [])
                    for (w_title, tk) in bucket:
                        # Only match when a non-empty mapping window title is
                        # provided and is present as a substring in the
                        # active window title (case-insensitive).
                        if w_title and (w_title.strip().lower() in title.lower()):
                            # Mark the target as ignored briefly to avoid
                            # re-triggering our hooks when we inject synthetic
                            # events. Normalize the target into the 'keyboard'
                            # package format (e.g. 'ctrl+alt+d').
                            # Shorter expiry — only needed to filter the
                            # synthetic injected target key event so it
                            # doesn't retrigger hooks.
                            expiry = time.time() + 0.25
                            if isinstance(tk, Key):
                                tn = tk.name
                            else:
                                # Convert space-padded "ctrl + alt + d" -> "ctrl+alt+d"
                                tn = str(tk).replace(' + ', '+').replace(' ', '')

                            self._kbd_ignore[tn] = expiry

                            try:
                                # Inject the mapped key using the keyboard package
                                # directly for minimal latency.
                                kbd.send(tn)
                            except Exception:
                                # Fallback: if send fails, emit to main thread
                                # for the shared controller path.
                                self.mapping_action_signal.emit(tk)

                            return

                    # No mapping matched for the active window — we
                    # must re-emit the original source key so normal
                    # behavior is preserved. The hook was installed with
                    # suppress=True so the original hardware event was
                    # swallowed by the library; here we send a synthetic
                    # keypress which will be delivered to the active app.
                    try:
                        expiry2 = time.time() + 0.25
                        self._kbd_ignore[event.name] = expiry2
                        kbd.send(event.name)
                    except Exception:
                        # best-effort: if re-send fails nothing else to do
                        pass

                    return

                return callback

            try:
                handler = kbd.on_press_key(key, make_callback(key), suppress=True)
                self._keyboard_hooks[key] = handler
            except Exception:
                # Ignore failures adding a hook for a particular key.
                pass

        # Unhook any active hooks for keys that are no longer matching
        for k in list(self._keyboard_hooks.keys()):
            if k not in active_keys:
                try:
                    kbd.unhook(self._keyboard_hooks[k])
                except Exception:
                    pass
                del self._keyboard_hooks[k]

    def _unhook_all_keyboard_hooks(self):
        if not self._kbd_available:
            return

        for h in list(self._keyboard_hooks.values()):
            try:
                kbd.unhook(h)
            except Exception:
                pass
        self._keyboard_hooks.clear()


    def closeEvent(self, event):
        self.save_mappings_to_config()
        self.keyboard_thread.stop()
        # Wait briefly for listener threads to shut down so we exit cleanly
        # instead of leaving background listeners still running. Use a
        # short timeout to avoid blocking shutdown indefinitely.
        try:
            self.keyboard_thread.wait(1000)
        except Exception:
            # Best effort; continue shutdown even if wait fails
            pass

        self.mouse_thread.stop()
        try:
            self.mouse_thread.wait(1000)
        except Exception:
            pass
        # Stop the active-title timer and remove any low-level keyboard hooks that were installed.
        try:
            self._active_title_timer.stop()
        except Exception:
            pass
        try:
            self._unhook_all_keyboard_hooks()
        except Exception:
            pass
        self.tray_icon.hide()
        event.accept()

if __name__ == "__main__":
    # Enable High-DPI scaling before creating the QApplication
    # This is the most reliable method across Qt versions
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    ex = KeyMapperApp()
    ex.show()
    sys.exit(app.exec())
