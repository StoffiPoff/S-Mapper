import sys
import os
import time
import configparser
import re
import logging
import html

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QListWidget, QRadioButton, QFrame, QMessageBox,
    QSystemTrayIcon, QMenu, QDoubleSpinBox, QScrollArea, QTabWidget, QTextEdit,
    QMainWindow
)
from PyQt6.QtCore import pyqtSignal, Qt, QMutex, QMutexLocker, QTimer, QEvent
from PyQt6.QtGui import QCursor, QIcon, QAction, QTextCursor
from pynput import keyboard
import threading
try:
    import pygetwindow as gw
except Exception:
    class _GWStub:
        @staticmethod
        def getActiveWindow():
            return None

        @staticmethod
        def getWindowsWithTitle(title):
            return []

    gw = _GWStub()
from pynput.keyboard import Key

from .utils import is_running_as_admin, resource_path
from .threads import KeyboardListenerThread, ActiveWindowEventThread, MouseListenerThread, PingThread
from .widgets import HelpWindow, PingStatusLabel

# Optional low-level keyboard interception via the 'keyboard' package.
# Import at module-level so all methods in this module can reference `kbd`.
try:
    import keyboard as kbd  # type: ignore
    _KBD_AVAILABLE = True
except Exception:
    kbd = None
    _KBD_AVAILABLE = False


class KeyMapperApp(QMainWindow):
    mapping_action_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.help_window = None
        self.ping_status_label = PingStatusLabel()
        self.mappings_lock = QMutex()
        self.keyboard_controller = keyboard.Controller()
        self.mappings = {}
        self.mapping_ids = []
        self.mapping_counter = 1
        self._editing_mapping_id = None
        self.last_click_time = {}
        self.click_counts = {}
        self.click_interval = 0.6
        self._ignore_keys = {}
        # keyboard package availability is discovered at module-level above
        # and mirrored into the instance for convenience.
        self._kbd_available = bool(_KBD_AVAILABLE)

        self._keyboard_hooks = {}
        self._kbd_ignore = {}
        self._source_index = {}
        self._kbd_enabled = bool(self._kbd_available)
        self.initUI()
        self.load_mappings_from_config()
        self.mapping_action_signal.connect(self._handle_mapping_action)
        self.start_listeners()

        self._cached_active_title = ""
        self._active_title_lock = threading.Lock()

        self._active_watcher = None
        self._active_watcher_available = False
        try:
            self._active_watcher = ActiveWindowEventThread(self)
            self._active_watcher.active_window_changed.connect(self._on_active_window_changed)
            self._active_watcher.start()
            self._active_watcher_available = True
        except Exception:
            self._active_watcher = None
            self._active_watcher_available = False

        self._active_title_timer = QTimer(self)
        self._active_title_timer.setInterval(500)
        self._active_title_timer.timeout.connect(self._update_cached_active_title)
        if not self._active_watcher_available:
            self._active_title_timer.start()

        self._ping_threads = set()

    def initUI(self):
        self.setWindowTitle("S-Mapper")
        # Use the app store / assets icon for the window icon
        self.setWindowIcon(QIcon(resource_path(os.path.join('assets', 'Square150x150Logo.png'))))
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

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Create Tab widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- Mappings Tab ---
        self.mappings_tab = QWidget()
        self.tabs.addTab(self.mappings_tab, "Mappings")
        mappings_layout = QVBoxLayout(self.mappings_tab)

        # Scroll area to contain the main content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        mappings_layout.addWidget(scroll_area)

        # Container widget for the scroll area's content
        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        layout = QVBoxLayout(scroll_content)
        scroll_content.setLayout(layout)

        layout.addWidget(QLabel("Configure Mouse to Keyboard Mappings"))

        layout.addWidget(QLabel("Mouse Button:"))
        self.mouse_button_combobox = QComboBox()
        self.mouse_button_combobox.addItems(['', 'left', 'right', 'middle', 'x1', 'x2'])
        layout.addWidget(self.mouse_button_combobox)

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

        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Mapping")
        self.remove_button = QPushButton("Remove Selected")
        self.edit_button = QPushButton("Edit Selected")
        self.cancel_edit_button = QPushButton("Cancel Edit")
        # Hidden until we're in edit mode
        self.cancel_edit_button.setVisible(False)
        self.refresh_button = QPushButton("Refresh Windows")
        self.clear_button = QPushButton("Clear Fields")
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.cancel_edit_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.clear_button)
        layout.addLayout(button_layout)

        self.mappings_listbox = QListWidget()
        # Enable a right-click context menu for edit/delete actions
        self.mappings_listbox.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mappings_listbox.customContextMenuRequested.connect(self._on_mappings_context_menu)
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
        
        # --- Ping Log Tab ---
        ping_log_tab = QWidget()
        self.tabs.addTab(ping_log_tab, "Ping Log")
        ping_log_layout = QVBoxLayout(ping_log_tab)
        
        self.ping_output_view = QTextEdit()
        self.ping_output_view.setReadOnly(True)
        self.ping_output_view.setStyleSheet("background-color: #0d0d0d; color: #d4d4d4; font-family: 'Courier New', Courier, monospace;")
        ping_log_layout.addWidget(self.ping_output_view)
        
        self.add_button.clicked.connect(self.add_mapping)
        self.edit_button.clicked.connect(self.edit_mapping)
        self.cancel_edit_button.clicked.connect(self._cancel_editing)
        self.remove_button.clicked.connect(self.remove_mapping)
        self.refresh_button.clicked.connect(self.refresh_window_list)
        self.clear_button.clicked.connect(self.clear)
        self.mouse_button_combobox.currentTextChanged.connect(self.on_combobox_selected)
        self.source_keyboard_combobox.currentTextChanged.connect(self.on_combobox_selected)
        self.window_selection_radio1.toggled.connect(self.update_window_selection_visibility)
        self.ip_monitor_toggle_button.toggled.connect(self.toggle_ip_monitoring)
        self.click_interval_spinbox.valueChanged.connect(self._on_interval_changed)
        
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.on_clipboard_change)

        self.update_window_selection_visibility()

        # --- System Tray Icon ---
        # Detect whether the system tray is available on this platform / session.
        # Some runtime environments (AppContainer/MSIX, headless sessions, or
        # restrictive remote sessions) may not provide a system tray — guard
        # the minimize-to-tray behavior accordingly.
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()

        # Try to load the icon; if loading fails we'll also consider the tray
        # effectively unavailable so we don't end up hiding the window and
        # losing the user when showMessage can't be delivered.
        # Prefer the smaller 44x44 asset for the tray icon (better for small tray sizes)
        icon = QIcon(resource_path(os.path.join('assets', 'Square44x44Logo.png')))
        if icon.isNull():
            # Icon failed to load. Log a short diagnostic and disable tray usage.
            logging.warning('s_mapper: tray icon failed to load, disabling tray behavior')
            self._tray_available = False

        if self._tray_available:
            self.tray_icon = QSystemTrayIcon(self)
            try:
                self.tray_icon.setIcon(icon)
            except Exception:
                # Guard against unexpected errors setting an icon
                logging.warning('s_mapper: failed to set tray icon')
            self.tray_icon.setToolTip("S-Mapper App")

            tray_menu = QMenu()
            show_action = QAction("Show", self)
            quit_action = QAction("Exit", self)

            show_action.triggered.connect(self.show_window)
            quit_action.triggered.connect(self.close)

            tray_menu.addAction(show_action)
            tray_menu.addAction(quit_action)

            try:
                self.tray_icon.setContextMenu(tray_menu)
            except Exception:
                logging.warning('s_mapper: failed to set tray context menu')

            try:
                self.tray_icon.show()
            except Exception:
                logging.warning('s_mapper: warning - tray_icon.show() failed')

            try:
                self.tray_icon.activated.connect(self.on_tray_icon_activated)
            except Exception:
                logging.warning('s_mapper: warning - failed to connect tray activation')
        else:
            # No system tray available in this environment — store a lightweight
            # None so other code can detect and fall back.
            self.tray_icon = None

        # Setup toolbar and menu (hideable toolbar + Help button)
        try:
            self.setup_toolbar_and_menu()
        except Exception:
            logging.warning('Failed to setup toolbar/menu')

    def setup_toolbar_and_menu(self):
        # Create a toolbar and a View menu entry to toggle it
        self.toolbar = self.addToolBar("Main Toolbar")
        self.toolbar.setMovable(False)

        help_action = QAction("Help", self)
        help_action.triggered.connect(self.show_help_window)
        self.toolbar.addAction(help_action)

        menu_bar = self.menuBar()
        view_menu = menu_bar.addMenu("&View")
        self.toggle_toolbar_action = QAction("Toolbar", self)
        self.toggle_toolbar_action.setCheckable(True)
        self.toggle_toolbar_action.setChecked(True)
        self.toggle_toolbar_action.triggered.connect(self.toggle_toolbar)
        view_menu.addAction(self.toggle_toolbar_action)

    def toggle_toolbar(self, checked):
        try:
            self.toolbar.setVisible(checked)
        except Exception:
            pass

    def show_help_window(self):
        if self.help_window is None:
            try:
                self.help_window = HelpWindow()
            except Exception:
                logging.exception('Failed to create HelpWindow')
                return
        self.help_window.show()
        self.help_window.activateWindow()

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

    def _on_active_window_changed(self, new_title: str):
        """
        Slot used by ActiveWindowEventThread. The event thread provides a
        lower-cased title string. Update the cached title and refresh hooks
        similarly to the polling path.
        """
        try:
            tnorm = (new_title or '').strip().lower()
            with self._active_title_lock:
                old = self._cached_active_title
                self._cached_active_title = tnorm

            if tnorm != old and self._kbd_available and getattr(self, '_kbd_enabled', False):
                try:
                    self._update_hooks_for_active_title(tnorm)
                except Exception:
                    pass
        except Exception:
            pass

    def toggle_ip_monitoring(self, checked):
        if checked:
            self.ip_monitor_toggle_button.setText("Stop Monitoring")
        else:
            self.ip_monitor_toggle_button.setText("Start Monitoring")

    def on_clipboard_change(self):
        if not self.ip_monitor_toggle_button.isChecked():
            return

        target_window_text = self.ip_monitor_window_entry.text()
        with self._active_title_lock:
            active_window_title = self._cached_active_title

        if not target_window_text or not active_window_title or target_window_text.lower() not in active_window_title.lower():
            return

        clipboard_text = self.clipboard.text()
        ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
        
        if re.match(ip_pattern, clipboard_text):
            self.ping_status_indicator.setStyleSheet("background-color: #f0ad4e; border-radius: 10px;")
            cursor_pos = QCursor.pos()
            self.ping_status_label.show_message("Ping sent...", "#FFA500", cursor_pos)
            self.mouse_thread.mouse_moved.connect(self.update_label_position)
            pt = PingThread(clipboard_text)
            pt.ping_result.connect(self.handle_ping_result)
            self._ping_threads.add(pt)
            pt.finished.connect(lambda: self._ping_threads.discard(pt))
            pt.start()

    def handle_ping_result(self, color, output):
        self.update_ping_indicator(color)
        
        header = f"--- Ping results for {self.clipboard.text()} ---"
        escaped_output = html.escape(output)

        # Prepend a newline if there's already content
        leading_br = "<br>" if self.ping_output_view.toPlainText() else ""
        
        html_content = (
            f'{leading_br}<div style="color: {color}; font-family: \'Courier New\', Courier, monospace;">'
            f'<b>{header}</b><br>'
            f'<pre>{escaped_output}</pre>'
            '</div>'
        )

        cursor = self.ping_output_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.ping_output_view.setTextCursor(cursor)
        self.ping_output_view.insertHtml(html_content)

    def update_ping_indicator(self, color):
        self.ping_status_indicator.setStyleSheet(f"background-color: {color}; border-radius: 10px;")
        cursor_pos = QCursor.pos()
        if color == 'red':
            self.ping_status_label.show_message("Ping failed", "red", cursor_pos)
        else:
            self.ping_status_label.show_message("Ping succeeded", "green", cursor_pos)

        QTimer.singleShot(1000, self.hide_ping_status_and_disconnect)
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
        # If we're editing an existing mapping, use the save flow instead
        if getattr(self, '_editing_mapping_id', None):
            return self._save_edited_mapping()

        source_key = self.source_keyboard_combobox.currentText()
        mouse_button = self.mouse_button_combobox.currentText()
        if source_key:
            self.add_keyboard_mapping()
        elif mouse_button:
            self.add_mouse_mapping()
        else:
            QMessageBox.warning(self, "Input Error", "Please select a trigger key or button.")

    def edit_mapping(self):
        """Populate the form with the selected mapping for editing."""
        selected_item = self.mappings_listbox.currentItem()
        if not selected_item:
            return

        selected_index = self.mappings_listbox.row(selected_item)
        if selected_index < 0 or selected_index >= len(self.mapping_ids):
            return

        mapping_id = self.mapping_ids[selected_index]

        # Find the mapping details
        details = None
        for win_title, mappings in self.mappings.items():
            if mapping_id in mappings:
                details = mappings[mapping_id]
                break

        if not details:
            return

        # Populate UI fields based on mapping type
        # Put UI into edit mode
        self._editing_mapping_id = mapping_id
        self.add_button.setText("Save Changes")
        # Show the cancel button while editing
        try:
            self.cancel_edit_button.setVisible(True)
        except Exception:
            pass

        # Clear fields first
        self.clear()

        if 'source_key' in details:
            # Keyboard mapping
            self.source_keyboard_combobox.setCurrentText(details.get('source_key', ''))
            self.target_keyboard_combobox.setCurrentText(details.get('target_key', ''))
            # window
            self.window_selection_radio1.setChecked(True)
            self.window_selection_entry.setText(details.get('window_title', ''))

        elif 'mouse_button' in details:
            # Mouse mapping
            self.mouse_button_combobox.setCurrentText(details.get('mouse_button', ''))
            self.press_count_entry.setText(str(details.get('press_count', '')))
            kb_button = details.get('keyboard_button')
            if isinstance(kb_button, Key):
                kb_button = kb_button.name
            self.target_keyboard_combobox.setCurrentText(str(kb_button))
            self.window_selection_radio1.setChecked(True)
            self.window_selection_entry.setText(details.get('window_title', ''))

        # Ensure combobox visibility logic is up to date
        self.on_combobox_selected()

    def _save_edited_mapping(self):
        """Save changes from form back into the existing mapping id."""
        mapping_id = getattr(self, '_editing_mapping_id', None)
        if not mapping_id:
            return

        # Determine values from form
        source_key = self.source_keyboard_combobox.currentText().lower().strip()
        mouse_button = self.mouse_button_combobox.currentText().lower().strip()
        target_key = self.target_keyboard_combobox.currentText().lower().strip()

        if self.window_selection_radio1.isChecked():
            target_window = self.window_selection_entry.text().lower().strip()
        else:
            target_window = self.window_selection_combobox.currentText().lower().strip()

        if not target_window:
            QMessageBox.warning(self, "Input Error", "Please select/enter a target window when saving changes.")
            return

        # Build new details dict depending on type
        if source_key:
            # keyboard mapping
            modifier_key = self.modifier_key_combobox.currentText()
            if modifier_key:
                target_key = f"{modifier_key} + {target_key}"

            if not target_key or not str(target_key).strip():
                QMessageBox.warning(self, "Input Error", "Please specify a target key when saving a keyboard mapping.")
                return

            new_details = {
                'source_key': source_key,
                'target_key': target_key,
                'window_title': target_window
            }

        elif mouse_button:
            try:
                press_count = int(self.press_count_entry.text())
            except ValueError:
                QMessageBox.warning(self, "Input Error", "Invalid press count. Please enter a number.")
                return

            modifier_key = self.modifier_key_combobox.currentText()
            if modifier_key:
                target_key = f"{modifier_key} + {target_key}"

            if not target_key or not str(target_key).strip():
                QMessageBox.warning(self, "Input Error", "Please specify a target key when saving a mouse mapping.")
                return

            final_key = target_key
            if target_key.startswith('f') and target_key[1:].isdigit():
                final_key = getattr(Key, target_key.lower(), target_key)

            new_details = {
                'mouse_button': mouse_button,
                'press_count': press_count,
                'keyboard_button': final_key,
                'window_title': target_window
            }

        else:
            QMessageBox.warning(self, "Input Error", "Please select a trigger key or button.")
            return

        # Update mapping in self.mappings (move if window changed)
        with QMutexLocker(self.mappings_lock):
            # Remove from old location
            old_window = None
            for w, mappings in list(self.mappings.items()):
                if mapping_id in mappings:
                    old_window = w
                    break

            if old_window is None:
                QMessageBox.warning(self, "Internal Error", "Original mapping not found; cannot save changes.")
                self._exit_edit_mode()
                return

            # Delete old mapping reference
            try:
                del self.mappings[old_window][mapping_id]
                # If the old window group is now empty, remove it
                if not self.mappings[old_window]:
                    del self.mappings[old_window]
            except Exception:
                pass

            # Insert into new window group
            if target_window not in self.mappings:
                self.mappings[target_window] = {}

            self.mappings[target_window][mapping_id] = new_details

        # Reset UI and display
        self._exit_edit_mode()
        self.update_mappings_display()
        self.clear()

    def _exit_edit_mode(self):
        self._editing_mapping_id = None
        try:
            self.add_button.setText("Add Mapping")
        except Exception:
            pass
        # Hide cancel button when not editing
        try:
            self.cancel_edit_button.setVisible(False)
        except Exception:
            pass

    def _cancel_editing(self):
        """Abort the current edit and restore UI to Add mode without saving."""
        # Reset UI fields to a clean state
        try:
            self.clear()
        except Exception:
            pass

        # Exit edit mode (resets Add button label and hides Cancel)
        self._exit_edit_mode()

    def _on_mappings_context_menu(self, pos):
        """Show right-click menu for mapping list with Edit/Delete actions."""
        item = self.mappings_listbox.itemAt(pos)
        if not item:
            return

        menu = QMenu()
        edit_action = QAction("Edit", self)
        delete_action = QAction("Delete", self)

        def on_edit():
            # Select the item and call edit
            self.mappings_listbox.setCurrentItem(item)
            self.edit_mapping()

        def on_delete():
            # Select the item and call remove mapping
            self.mappings_listbox.setCurrentItem(item)
            self.remove_mapping()

        edit_action.triggered.connect(on_edit)
        delete_action.triggered.connect(on_delete)

        menu.addAction(edit_action)
        menu.addAction(delete_action)

        menu.exec(self.mappings_listbox.mapToGlobal(pos))

    def _add_mapping_details(self, details):
        """Adds a validated mapping details dictionary to the central store."""
        with QMutexLocker(self.mappings_lock):
            target_window = details.get('window_title', '')
            if not target_window:
                return

            mapping_id = f"Mapping {self.mapping_counter}"
            self.mapping_counter += 1

            if target_window not in self.mappings:
                self.mappings[target_window] = {}

            self.mappings[target_window][mapping_id] = details
            self.mapping_ids.append(mapping_id)
            self.update_mappings_display()
        
        if self._kbd_available and getattr(self, '_kbd_enabled', False):
            try:
                self._refresh_keyboard_hooks()
            except Exception:
                pass
        self.clear()

    def add_mouse_mapping(self):
        mouse_button = self.mouse_button_combobox.currentText().lower().strip()
        try:
            press_count = int(self.press_count_entry.text())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid press count. Please enter a number.")
            return
        
        keyboard_button = self.target_keyboard_combobox.currentText().lower().strip()

        if self.window_selection_radio1.isChecked():
            target_window = self.window_selection_entry.text().lower().strip()
        else:
            target_window = self.window_selection_combobox.currentText().lower().strip()

        if not all([mouse_button, keyboard_button, target_window]):
            QMessageBox.warning(self, "Input Error", "Please fill all required fields.")
            return

        modifier_key = self.modifier_key_combobox.currentText()
        if modifier_key:
            keyboard_button = f"{modifier_key} + {keyboard_button}"

        final_key = keyboard_button
        if keyboard_button.startswith('f') and keyboard_button[1:].isdigit():
            final_key = getattr(Key, keyboard_button.lower(), keyboard_button)

        details = {
            'mouse_button': mouse_button,
            'press_count': press_count,
            'keyboard_button': final_key,
            'window_title': target_window
        }
        self._add_mapping_details(details)

    def add_keyboard_mapping(self):
        source_key = self.source_keyboard_combobox.currentText().lower().strip()
        target_key = self.target_keyboard_combobox.currentText().lower().strip()

        if self.window_selection_radio1.isChecked():
            target_window = self.window_selection_entry.text().lower().strip()
        else:
            target_window = self.window_selection_combobox.currentText().lower().strip()

        if not all([source_key, target_key, target_window]):
            QMessageBox.warning(self, "Input Error", "Please fill all required fields.")
            return
        
        modifier_key = self.modifier_key_combobox.currentText()
        if modifier_key:
            target_key = f"{modifier_key} + {target_key}"
        
        details = {
            'source_key': source_key,
            'target_key': target_key,
            'window_title': target_window
        }
        self._add_mapping_details(details)
        
    def remove_mapping(self):
        selected_item = self.mappings_listbox.currentItem()
        if not selected_item:
            return
        
        selected_index = self.mappings_listbox.row(selected_item)
        
        with QMutexLocker(self.mappings_lock):
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
                # Only minimize-to-tray if we have a usable system tray and icon
                if getattr(self, '_tray_available', False) and getattr(self, 'tray_icon', None):
                    try:
                        self.hide()
                        # showMessage may raise or be ignored depending on platform
                        try:
                            self.tray_icon.showMessage(
                                "S-Mapper",
                                "Application was minimized to tray.",
                                QSystemTrayIcon.MessageIcon.Information,
                                2000
                            )
                        except Exception:
                            logging.warning('s_mapper: tray_icon.showMessage() failed')
                    except Exception:
                        # If hiding fails for some reason, avoid leaving the
                        # application invisible with no recovery path — keep it
                        # visible instead.
                        logging.warning('s_mapper: hide() failed while minimizing; leaving window visible')
                else:
                    # If the system tray is not available, do not hide the window
                    # when minimized. This provides a safe fallback for environments
                    # where the tray is not present (e.g., MSIX/AppContainer).
                    logging.info('s_mapper: system tray unavailable - not hiding window on minimize')
        # In some test or shim scenarios the instance we bound the method to
        # won't be a true QWidget instance and calling super().changeEvent
        # will raise a TypeError. Guard this call so tests and thin stubs can
        # exercise the logic above without failing.
        try:
            super().changeEvent(event)
        except Exception:
            pass

    def on_press(self, key):
        try:
            with QMutexLocker(self.mappings_lock):
                if self._kbd_available and getattr(self, '_kbd_enabled', False):
                    return

                pressed_key = None
                if isinstance(key, keyboard.KeyCode):
                    pressed_key = getattr(key, 'char', None)
                else:
                    pressed_key = getattr(key, 'name', None)

                if not pressed_key:
                    return

                pressed_key = pressed_key.lower().strip()

                with self._active_title_lock:
                    current_title = self._cached_active_title

                if not current_title:
                    return

                for window_title, mappings in self.mappings.items():
                    if not window_title:
                        continue
                    if window_title.strip().lower() in current_title:
                        for details in mappings.values():
                            if details.get('source_key', '').lower().strip() == pressed_key:
                                self.mapping_action_signal.emit(details['target_key'])
                                return
        except Exception:
            logging.exception("on_press")

    def on_click(self, x, y, button, pressed):
        if not pressed:
            return

        with self._active_title_lock:
            target_window_title = self._cached_active_title

        if not target_window_title:
            return

        button_name = button.name.lower().strip()
        current_time = time.time()

        self.click_counts.setdefault(button_name, 0)

        last_click = self.last_click_time.get(button_name)
        if last_click and (current_time - last_click) > self.click_interval:
            self.click_counts[button_name] = 0
        
        self.click_counts[button_name] += 1
        self.last_click_time[button_name] = current_time

        action_to_run = None

        with QMutexLocker(self.mappings_lock):
            for partial_title, mappings in self.mappings.items():
                if partial_title.strip().lower() in target_window_title:
                    for details in mappings.values():
                        if 'mouse_button' not in details:
                            continue

                        if (details['mouse_button'].lower().strip() == button_name and
                                details['press_count'] == self.click_counts[button_name]):

                            self.click_counts[button_name] = 0
                            action_to_run = details['keyboard_button']
                            break

                    if action_to_run:
                        break
            pass

        if not action_to_run:
            return

        self.mapping_action_signal.emit(action_to_run)

    def _get_config_filepath(self):
        """
        Returns the platform-specific, user-writable path for the mappings.ini file.
        """
        app_data_path = os.environ.get('LOCALAPPDATA') or os.path.expanduser(r"~\AppData\Local")
        config_dir = os.path.join(app_data_path, 'S-Mapper')
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception:
            return 'mappings.ini'
        return os.path.join(config_dir, 'mappings.ini')

    def save_mappings_to_config(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        
        self.mappings_lock.lock()
        try:
            all_mappings = {}
            for mappings_by_window in self.mappings.values():
                all_mappings.update(mappings_by_window)
        finally:
            self.mappings_lock.unlock()

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

    def _handle_mapping_action(self, keyboard_button):
        """
        Slot executed on the GUI thread (via mapping_action_signal) that
        runs the keyboard action using the shared controller. This keeps
        key injection consistent with the app's main controller.
        """
        try:
            kb_button_str = keyboard_button if isinstance(keyboard_button, str) else keyboard_button.name
            

            parts = [p.strip() for p in kb_button_str.replace(' + ', '+').split('+')]
            main_key = parts[-1]
            # mapping for known modifier names -> Key attributes
            mod_map = {'ctrl': Key.ctrl, 'control': Key.ctrl, 'shift': Key.shift, 'alt': Key.alt,
                       'win': Key.cmd, 'windows': Key.cmd, 'cmd': Key.cmd, 'meta': Key.cmd}

            modifiers = [m.lower() for m in parts[:-1] if m]
            modifier_keys = [mod_map.get(m) for m in modifiers if mod_map.get(m) is not None]
            key_to_press = getattr(Key, main_key, main_key)

            if modifier_keys:
                with self.keyboard_controller.pressed(*modifier_keys):
                    self.keyboard_controller.press(key_to_press)
                    self.keyboard_controller.release(key_to_press)
            else:
                self.keyboard_controller.press(key_to_press)
                self.keyboard_controller.release(key_to_press)

        except Exception as e:
            logging.exception(f"Mapping action failed (main thread): {e}")

    def load_mappings_from_config(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        
        config_path = self._get_config_filepath()
        if not os.path.exists(config_path):
            try:
                with open(config_path, 'w') as configfile:
                    pass
                return
            except IOError as e:
                QMessageBox.critical(self, "File Creation Error", f"Failed to create {config_path}: {e}")
                return

        config.read(config_path)
        highest_mapping_number = 0

        self.mappings_lock.lock()
        try:
            self.mappings.clear()
            self.mapping_ids.clear()

            for section_name in config.sections():
                if section_name in ['DEFAULT', 'Settings']:
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
                    logging.warning(f"Skipping malformed or incomplete section {section_name}: {e}")
                    continue
        finally:
            self.mappings_lock.unlock()

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
        # Some tests (or lightweight shims) use a Dummy object without a
        # mappings_lock. Be defensive: only lock when the attribute exists
        # and exposes a .lock()/.unlock() API. This keeps test doubles
        # and non-Qt shims from raising AttributeError during collection.
        _mlock = getattr(self, 'mappings_lock', None)
        if _mlock:
            with QMutexLocker(_mlock):
                for mappings in getattr(self, 'mappings', {}).values():
                    for details in mappings.values():
                        if 'source_key' in details and details['source_key']:
                            sk = details['source_key']
                            source_keys.add(sk)
                            self._source_index.setdefault(sk, []).append(
                                (details.get('window_title', ''), details.get('target_key'))
                            )
        else:
            for mappings in getattr(self, 'mappings', {}).values():
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
        try:
            self.save_mappings_to_config()
        except Exception:
            pass

        try:
            for pt in list(getattr(self, '_ping_threads', [])):
                try:
                    pt.stop()
                except Exception:
                    pass
            for pt in list(getattr(self, '_ping_threads', [])):
                try:
                    pt.wait(1000)
                except Exception:
                    pass
        except Exception:
            pass

        # Stop listeners and wait for them. If they don't stop in a reasonable
        # time, attempt stronger termination to avoid leaving background
        # processes running after the GUI closes.
        def _stop_and_wait(thread_obj, name, timeout_ms=2000):
            try:
                if thread_obj:
                    try:
                        thread_obj.stop()
                    except Exception:
                        pass
                    try:
                        if not thread_obj.wait(timeout_ms):
                            # If wait returned False, try to terminate the thread
                            try:
                                thread_obj.terminate()
                            except Exception:
                                pass
                            try:
                                thread_obj.wait(500)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                logging.warning(f's_mapper: failed to stop/kill {name}')

        _stop_and_wait(getattr(self, 'keyboard_thread', None), 'keyboard_thread')
        _stop_and_wait(getattr(self, 'mouse_thread', None), 'mouse_thread')

        try:
            self._active_title_timer.stop()
        except Exception:
            pass

        try:
            if getattr(self, '_active_watcher', None):
                try:
                    self._active_watcher.stop()
                except Exception:
                    pass
                try:
                    self._active_watcher.wait(2000)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self._unhook_all_keyboard_hooks()
        except Exception:
            pass

        try:
            if getattr(self, 'tray_icon', None):
                try:
                    self.tray_icon.hide()
                except Exception:
                    pass
        except Exception:
            pass

        # Allow Qt main loop to exit -- ensures the app finishes cleanly.
        try:
            QApplication.quit()
        except Exception:
            pass

        # Last-resort: if configured, force the process to exit to ensure no
        # lingering background threads/processes remain. This is intended as
        # a last-resort option exposed via the environment variable
        # S_MAPPER_FORCE_EXIT_ON_CLOSE or an instance attribute
        # KeyMapperApp.force_exit_on_close = True.
        try:
            env_force = os.environ.get('S_MAPPER_FORCE_EXIT_ON_CLOSE', '')
            fb = getattr(self, 'force_exit_on_close', False)
            env_flag = str(env_force).lower() in ('1', 'true', 'yes', 'on')
            if fb or env_flag:
                try:
                    # Use os._exit to force immediate termination (no cleanup).
                    os._exit(0)
                except SystemExit:
                    # os._exit doesn't raise, but just in case default path
                    # raises SystemExit, fall back to exit(0).
                    try:
                        sys.exit(0)
                    except Exception:
                        pass
        except Exception:
            pass

        event.accept()
