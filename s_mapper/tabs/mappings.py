from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QListWidget, QRadioButton, QFrame,
    QDoubleSpinBox, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor


def build_mappings_tab(app):
    """Create and attach the 'Mappings' tab UI to the given app instance.

    This function mirrors the UI construction previously in KeyMapperApp
    and sets attributes on the app object so the rest of the logic can
    remain unchanged.
    """
    app.mappings_tab = QWidget()
    app.tabs.addTab(app.mappings_tab, "Mappings")

    mappings_layout = QVBoxLayout(app.mappings_tab)

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
    app.mouse_button_combobox = QComboBox()
    app.mouse_button_combobox.addItems(['', 'left', 'right', 'middle', 'x1', 'x2'])
    layout.addWidget(app.mouse_button_combobox)

    layout.addWidget(QLabel("Number of Presses:"))
    app.press_count_entry = QLineEdit()
    layout.addWidget(app.press_count_entry)

    interval_frame = QHBoxLayout()
    interval_frame.addWidget(QLabel("Double-click window (sec):"))
    app.click_interval_spinbox = QDoubleSpinBox()
    app.click_interval_spinbox.setRange(0.05, 5.0)
    app.click_interval_spinbox.setSingleStep(0.05)
    app.click_interval_spinbox.setDecimals(2)
    app.click_interval_spinbox.setValue(app.click_interval)
    app.click_interval_spinbox.setToolTip("Maximum time between consecutive clicks for them to count as one mapping (seconds)")
    interval_frame.addWidget(app.click_interval_spinbox)
    layout.addLayout(interval_frame)

    app.source_key_label = QLabel("Source Keyboard Key:")
    layout.addWidget(app.source_key_label)
    # keyboard_keys is expected to be present on the app instance
    app.source_keyboard_combobox = QComboBox()
    app.source_keyboard_combobox.addItems(app.keyboard_keys)
    layout.addWidget(app.source_keyboard_combobox)

    layout.addWidget(QLabel("Target Keyboard Key:"))
    app.target_keyboard_combobox = QComboBox()
    app.target_keyboard_combobox.addItems(app.keyboard_keys)
    layout.addWidget(app.target_keyboard_combobox)

    # Modifier
    layout.addWidget(QLabel("Modifier Key:"))
    app.modifier_key_combobox = QComboBox()
    app.modifier_key_combobox.addItems(['', 'ctrl', 'alt', 'shift', 'ctrl + alt', 'ctrl + shift', 'alt + shift'])
    layout.addWidget(app.modifier_key_combobox)

    # Target Window
    layout.addWidget(QLabel("Select Target Window:"))
    app.window_selection_var_group = QVBoxLayout()
    app.window_selection_radio1 = QRadioButton("Free Text (Partial Match)")
    app.window_selection_radio1.setChecked(True)
    app.window_selection_radio2 = QRadioButton("Select from Active Windows")
    app.window_selection_var_group.addWidget(app.window_selection_radio1)
    app.window_selection_var_group.addWidget(app.window_selection_radio2)
    layout.addLayout(app.window_selection_var_group)

    window_frame = QFrame()
    window_frame_layout = QHBoxLayout()
    window_frame.setLayout(window_frame_layout)
    app.window_selection_entry = QLineEdit()
    app.window_selection_combobox = QComboBox()
    window_frame_layout.addWidget(app.window_selection_entry)
    window_frame_layout.addWidget(app.window_selection_combobox)
    layout.addWidget(window_frame)
    app.refresh_window_list()

    button_layout = QHBoxLayout()
    app.add_button = QPushButton("Add Mapping")
    app.remove_button = QPushButton("Remove Selected")
    app.edit_button = QPushButton("Edit Selected")
    app.cancel_edit_button = QPushButton("Cancel Edit")
    app.cancel_edit_button.setVisible(False)
    app.refresh_button = QPushButton("Refresh Windows")
    app.clear_button = QPushButton("Clear Fields")
    button_layout.addWidget(app.add_button)
    button_layout.addWidget(app.edit_button)
    button_layout.addWidget(app.cancel_edit_button)
    button_layout.addWidget(app.remove_button)
    button_layout.addWidget(app.refresh_button)
    button_layout.addWidget(app.clear_button)
    layout.addLayout(button_layout)

    app.mappings_listbox = QListWidget()
    app.mappings_listbox.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    app.mappings_listbox.customContextMenuRequested.connect(app._on_mappings_context_menu)
    layout.addWidget(app.mappings_listbox)

    # IP monitor panel gets inserted into mappings tab
    ip_monitor_frame = QFrame()
    ip_monitor_frame.setFrameShape(QFrame.Shape.StyledPanel)
    ip_monitor_layout = QVBoxLayout()
    ip_monitor_frame.setLayout(ip_monitor_layout)

    ip_monitor_layout.addWidget(QLabel("Clipboard IP Ping Monitor"))

    ip_monitor_hbox = QHBoxLayout()
    ip_monitor_hbox.addWidget(QLabel("Target Window Contains:"))
    app.ip_monitor_window_entry = QLineEdit()
    ip_monitor_hbox.addWidget(app.ip_monitor_window_entry)

    app.ping_status_indicator = QLabel()
    app.ping_status_indicator.setFixedSize(20, 20)
    app.ping_status_indicator.setStyleSheet("background-color: #555; border-radius: 10px;")
    ip_monitor_hbox.addWidget(app.ping_status_indicator)
    ip_monitor_layout.addLayout(ip_monitor_hbox)

    app.ip_monitor_toggle_button = QPushButton("Start Monitoring")
    app.ip_monitor_toggle_button.setCheckable(True)
    ip_monitor_layout.addWidget(app.ip_monitor_toggle_button)

    # the caller (KeyMapperApp) is responsible for creating kbd_status_label & checkbox
    try:
        app.kbd_suppression_checkbox  # may exist already
    except Exception:
        # leave missing attributes to be handled in UI init
        app.kbd_suppression_checkbox = None
        app.kbd_status_label = QLabel()

    layout.addWidget(ip_monitor_frame)

    # wire up signals that require handlers on app
    app.add_button.clicked.connect(app.add_mapping)
    app.edit_button.clicked.connect(app.edit_mapping)
    app.cancel_edit_button.clicked.connect(app._cancel_editing)
    app.remove_button.clicked.connect(app.remove_mapping)
    app.refresh_button.clicked.connect(app.refresh_window_list)
    app.clear_button.clicked.connect(app.clear)
    app.mouse_button_combobox.currentTextChanged.connect(app.on_combobox_selected)
    app.source_keyboard_combobox.currentTextChanged.connect(app.on_combobox_selected)
    app.window_selection_radio1.toggled.connect(app.update_window_selection_visibility)
    app.ip_monitor_toggle_button.toggled.connect(app.toggle_ip_monitoring)
    app.click_interval_spinbox.valueChanged.connect(app._on_interval_changed)

    # Clipboard handling is connected centrally by the main UI initializer
    # (KeyMapperApp.initUI) — avoid connecting the same signal here which
    # could cause duplicate handlers and duplicate ping triggers.

    # Exposed expected attributes already created; function complete.
