import sys
import os
import time
import configparser
import re
import subprocess

# Properties for the executable
__company__ = "Stoffi Software Solutions"
__product__ = "S-Mapper"
__version__ = "1.0.0"
__description__ = "A versatile tool for remapping keyboard and mouse inputs."
__copyright__ = "Copyright (c) 2025 Stoffi Software Solutions"
__license__ = "MIT"
__internal_name__ = "s-mapper-app"

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QListWidget, QRadioButton, QFrame, QMessageBox,
    QSystemTrayIcon, QMenu, QStyle
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QMutex, QMutexLocker, QTimer, QEvent
from PyQt6.QtGui import QCursor, QIcon, QAction
from pynput import mouse, keyboard
import pygetwindow as gw
from pynput.keyboard import Key

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

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
    def __init__(self):
        super().__init__()
        self.ping_status_label = PingStatusLabel()
        self.mappings_lock = QMutex()
        self.keyboard_controller = keyboard.Controller()
        self.mappings = {}
        self.mapping_ids = []
        self.mapping_counter = 1
        self.last_click_time = None
        self.click_counts = {}
        self.initUI()
        self.load_mappings_from_config()
        self.start_listeners()

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

        layout = QVBoxLayout()
        self.setLayout(layout)

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

    def update_label_position(self, x, y):
        if self.ping_status_label.isVisible():
            # Position it above the cursor, slightly to the right
            self.ping_status_label.move(x + 10, y - self.ping_status_label.height())

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
            pressed_key = key.char if isinstance(key, keyboard.KeyCode) else key.name
            current_window = gw.getActiveWindow()
            if not pressed_key or not current_window:
                return

            current_window_title = current_window.title
            
            for window_title, mappings in self.mappings.items():
                if window_title in current_window_title:
                    for details in mappings.values():
                        if 'source_key' in details and details['source_key'] == pressed_key:
                            target_key = details['target_key']
                            
                            parts = target_key.split(' + ')
                            key_to_press_str = parts[-1].strip()
                            modifiers_str = [p.strip() for p in parts[:-1]]

                            key_to_press = getattr(Key, key_to_press_str, key_to_press_str)
                            modifier_keys = [getattr(Key, m) for m in modifiers_str]
                            
                            if modifier_keys:
                                with self.keyboard_controller.pressed(*modifier_keys):
                                    self.keyboard_controller.press(key_to_press)
                                    self.keyboard_controller.release(key_to_press)
                            else:
                                self.keyboard_controller.press(key_to_press)
                                self.keyboard_controller.release(key_to_press)
                            return
        except (AttributeError, KeyError, ValueError):
            pass

    def on_click(self, x, y, button, pressed):
        locker = QMutexLocker(self.mappings_lock)
        if not pressed:
            return

        active_window = gw.getActiveWindow()
        if not active_window:
            return

        button_name = button.name
        current_time = time.time()

        self.click_counts.setdefault(button_name, 0)

        if self.last_click_time and (current_time - self.last_click_time) > 0.3:
            self.click_counts[button_name] = 0
        
        self.click_counts[button_name] += 1
        self.last_click_time = current_time

        target_window_title = active_window.title

        for partial_title, mappings in self.mappings.items():
            if partial_title in target_window_title:
                for details in mappings.values():
                    if 'mouse_button' not in details: continue
                    
                    if (details['mouse_button'] == button_name and 
                        details['press_count'] == self.click_counts[button_name]):
                        
                        self.click_counts[button_name] = 0
                        keyboard_button = details['keyboard_button']

                        # Convert to string for consistent processing
                        kb_button_str = keyboard_button
                        if isinstance(keyboard_button, Key):
                            kb_button_str = keyboard_button.name

                        parts = kb_button_str.split(' + ')
                        key_to_press_str = parts[-1].strip()
                        modifiers_str = [p.strip() for p in parts[:-1]]

                        key_to_press = getattr(Key, key_to_press_str, key_to_press_str)
                        modifier_keys = [getattr(Key, m) for m in modifiers_str]

                        if modifier_keys:
                            with self.keyboard_controller.pressed(*modifier_keys):
                                self.keyboard_controller.press(key_to_press)
                                self.keyboard_controller.release(key_to_press)
                        else:
                            self.keyboard_controller.press(key_to_press)
                            self.keyboard_controller.release(key_to_press)
                        return

    def save_mappings_to_config(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        
        locker = QMutexLocker(self.mappings_lock)

        all_mappings = {}
        for mappings_by_window in self.mappings.values():
            all_mappings.update(mappings_by_window)

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

        with open('mappings.ini', 'w') as configfile:
            config.write(configfile)

    def load_mappings_from_config(self):
        config = configparser.ConfigParser()
        config.optionxform = str
        
        if not os.path.exists('mappings.ini'):
            try:
                # Create an empty file so the app can save to it later.
                with open('mappings.ini', 'w') as configfile:
                    pass
                return # Stop here since there's nothing to load
            except IOError as e:
                QMessageBox.critical(self, "File Creation Error", f"Failed to create mappings.ini: {e}")
                return

        config.read('mappings.ini')
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


    def closeEvent(self, event):
        self.save_mappings_to_config()
        self.keyboard_thread.stop()
        self.mouse_thread.stop()
        self.tray_icon.hide()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = KeyMapperApp()
    ex.show()
    sys.exit(app.exec())
