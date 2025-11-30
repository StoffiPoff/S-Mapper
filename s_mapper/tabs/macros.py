from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget, QComboBox,
    QDoubleSpinBox, QPushButton, QTextEdit, QLineEdit
)


def build_macros_tab(app):
    """Create and attach the 'Macros' tab UI to the app instance."""
    macros_tab = QWidget()
    app.tabs.addTab(macros_tab, "Macros")
    macros_layout = QHBoxLayout(macros_tab)

    # Left: list of macros
    left_frame = QWidget()
    left_layout = QVBoxLayout(left_frame)
    app.macros_listbox = QListWidget()
    left_layout.addWidget(QLabel("Saved Macros"))
    left_layout.addWidget(app.macros_listbox)

    btn_layout = QHBoxLayout()
    app.add_macro_button = QPushButton("Add Macro")
    app.edit_macro_button = QPushButton("Edit Macro")
    app.cancel_macro_edit_button = QPushButton("Cancel Edit")
    app.cancel_macro_edit_button.setVisible(False)
    app.remove_macro_button = QPushButton("Remove Macro")
    app.run_macro_button = QPushButton("Run Selected")
    btn_layout.addWidget(app.add_macro_button)
    btn_layout.addWidget(app.edit_macro_button)
    btn_layout.addWidget(app.cancel_macro_edit_button)
    btn_layout.addWidget(app.remove_macro_button)
    btn_layout.addWidget(app.run_macro_button)
    left_layout.addLayout(btn_layout)

    macros_layout.addWidget(left_frame, stretch=1)

    # Right: macro editor
    right_frame = QWidget()
    right_layout = QVBoxLayout(right_frame)
    right_layout.addWidget(QLabel("Trigger (optional)"))
    trigger_frame = QHBoxLayout()
    app.macro_trigger_none_rb = QLineEdit() if False else None  # small placeholder
    # We'll create the three radio buttons expected by the rest of the app
    from PyQt6.QtWidgets import QRadioButton
    app.macro_trigger_none_rb = QRadioButton("None")
    app.macro_trigger_key_rb = QRadioButton("Key")
    app.macro_trigger_mouse_rb = QRadioButton("Mouse")
    app.macro_trigger_none_rb.setChecked(True)
    trigger_frame.addWidget(app.macro_trigger_none_rb)
    trigger_frame.addWidget(app.macro_trigger_key_rb)
    trigger_frame.addWidget(app.macro_trigger_mouse_rb)
    right_layout.addLayout(trigger_frame)

    app.macro_key_combobox = QComboBox()
    app.macro_key_combobox.addItems(app.keyboard_keys)
    app.macro_key_combobox.setEnabled(False)
    right_layout.addWidget(app.macro_key_combobox)

    mouse_trigger_frame = QHBoxLayout()
    app.macro_mouse_button_combobox = QComboBox()
    app.macro_mouse_button_combobox.addItems(['', 'left', 'right', 'middle', 'x1', 'x2'])
    app.macro_mouse_presses = QDoubleSpinBox()
    app.macro_mouse_presses.setRange(1, 10)
    app.macro_mouse_presses.setValue(1)
    app.macro_mouse_presses.setSingleStep(1)
    app.macro_mouse_presses.setEnabled(False)
    app.macro_mouse_button_combobox.setEnabled(False)
    mouse_trigger_frame.addWidget(QLabel("Button:"))
    mouse_trigger_frame.addWidget(app.macro_mouse_button_combobox)
    mouse_trigger_frame.addWidget(QLabel("Presses:"))
    mouse_trigger_frame.addWidget(app.macro_mouse_presses)
    right_layout.addLayout(mouse_trigger_frame)

    right_layout.addWidget(QLabel("Trigger Window (partial, required for triggers):"))
    app.macro_trigger_window_entry = QLineEdit()
    right_layout.addWidget(app.macro_trigger_window_entry)

    right_layout.addWidget(QLabel("Macro Name"))
    app.macro_name_entry = QLineEdit()
    right_layout.addWidget(app.macro_name_entry)

    # (No additional builder UI — keep the editor simple and focused)

    record_btn_layout = QHBoxLayout()
    app.record_macro_button = QPushButton("Record")
    app.stop_record_button = QPushButton("Stop")
    app.stop_record_button.setEnabled(False)
    record_btn_layout.addWidget(app.record_macro_button)
    record_btn_layout.addWidget(app.stop_record_button)
    right_layout.addLayout(record_btn_layout)
    right_layout.addWidget(QLabel("Actions (one per line): text:Hello | key:enter | sleep:0.2"))
    app.macro_actions_text = QTextEdit()
    right_layout.addWidget(app.macro_actions_text)

    macros_layout.addWidget(right_frame, stretch=2)

    # simple in-memory store for macros
    app.macros = []
    app.macros_by_id = {}
    app._macro_recorder = None

    # wire up macro buttons
    app.add_macro_button.clicked.connect(app._add_macro_from_editor)
    # Clicking "Edit" should put the macro into edit mode (populate editor + switch to save)
    app.edit_macro_button.clicked.connect(app.edit_macro)
    app.cancel_macro_edit_button.clicked.connect(app._cancel_macro_editing)
    app.remove_macro_button.clicked.connect(app._remove_selected_macro)
    app.run_macro_button.clicked.connect(app._run_selected_macro)

    # trigger toggles enable/disable trigger inputs
    app.macro_trigger_key_rb.toggled.connect(lambda s: app.macro_key_combobox.setEnabled(s))

    def _mouse_toggle(s):
        app.macro_mouse_button_combobox.setEnabled(s)
        app.macro_mouse_presses.setEnabled(s)

    app.macro_trigger_mouse_rb.toggled.connect(_mouse_toggle)

    # recording controls
    app.record_macro_button.clicked.connect(app._start_recording)
    app.stop_record_button.clicked.connect(app._stop_recording)

    # No builder helper functions — editing actions directly is simpler

    app.update_window_selection_visibility()

    return macros_tab
