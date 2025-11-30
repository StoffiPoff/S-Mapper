import importlib
import threading
from types import SimpleNamespace

m = importlib.import_module('s_mapper')


def make_common_attrs():
    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj._active_title_lock = threading.Lock()
    # Provide safe default UI attributes used by _save_edited_mapping/_cancel_editing
    obj.source_keyboard_combobox = SimpleNamespace(currentText=lambda: '')
    obj.mouse_button_combobox = SimpleNamespace(currentText=lambda: '')
    obj.target_keyboard_combobox = SimpleNamespace(currentText=lambda: '')
    obj.press_count_entry = SimpleNamespace(text=lambda: '')
    obj.window_selection_radio1 = SimpleNamespace(isChecked=lambda: True)
    obj.window_selection_entry = SimpleNamespace(text=lambda: '')
    obj.window_selection_combobox = SimpleNamespace(currentText=lambda: '')
    obj.modifier_key_combobox = SimpleNamespace(currentText=lambda: '')
    obj.clear = lambda: None
    # Provide a simple _exit_edit_mode implementation for tests that clears edit state
    obj._exit_edit_mode = lambda: setattr(obj, '_editing_mapping_id', None)
    obj.update_mappings_display = lambda: None
    return obj


def test_save_edited_keyboard_mapping_moves_and_updates():
    obj = make_common_attrs()

    # initial mapping in old window
    obj.mappings = {'oldwin': {'Mapping 1': {'source_key': 'a', 'target_key': 'b', 'window_title': 'oldwin'}}}
    obj.mapping_ids = ['Mapping 1']

    obj._editing_mapping_id = 'Mapping 1'

    # UI fields
    obj.source_keyboard_combobox = SimpleNamespace(currentText=lambda: 'x')
    obj.mouse_button_combobox = SimpleNamespace(currentText=lambda: '')
    obj.target_keyboard_combobox = SimpleNamespace(currentText=lambda: 'y')
    obj.press_count_entry = SimpleNamespace(text=lambda: '')
    obj.window_selection_radio1 = SimpleNamespace(isChecked=lambda: True)
    obj.window_selection_entry = SimpleNamespace(text=lambda: 'newwin')
    obj.window_selection_combobox = SimpleNamespace(currentText=lambda: '')
    obj.modifier_key_combobox = SimpleNamespace(currentText=lambda: '')

    handler = m.KeyMapperApp._save_edited_mapping.__get__(obj, m.KeyMapperApp)
    handler()

    # mapping should be moved to newwin and updated
    assert 'oldwin' not in obj.mappings or 'Mapping 1' not in obj.mappings.get('oldwin', {})
    assert 'newwin' in obj.mappings
    assert 'Mapping 1' in obj.mappings['newwin']
    d = obj.mappings['newwin']['Mapping 1']
    assert d['source_key'] == 'x'
    assert d['target_key'] == 'y'
    assert d['window_title'] == 'newwin'


def test_save_edited_mouse_mapping_moves_and_updates():
    obj = make_common_attrs()

    obj.mappings = {'oldwin': {'Mapping 1': {'mouse_button': 'left', 'press_count': 2, 'keyboard_button': 'z', 'window_title': 'oldwin'}}}
    obj.mapping_ids = ['Mapping 1']

    obj._editing_mapping_id = 'Mapping 1'

    obj.source_keyboard_combobox = SimpleNamespace(currentText=lambda: '')
    obj.mouse_button_combobox = SimpleNamespace(currentText=lambda: 'right')
    obj.target_keyboard_combobox = SimpleNamespace(currentText=lambda: 'ctrl + alt + d')
    obj.press_count_entry = SimpleNamespace(text=lambda: '3')
    obj.window_selection_radio1 = SimpleNamespace(isChecked=lambda: True)
    obj.window_selection_entry = SimpleNamespace(text=lambda: 'newmousewin')
    obj.window_selection_combobox = SimpleNamespace(currentText=lambda: '')
    obj.modifier_key_combobox = SimpleNamespace(currentText=lambda: '')

    handler = m.KeyMapperApp._save_edited_mapping.__get__(obj, m.KeyMapperApp)
    handler()

    assert 'oldwin' not in obj.mappings or 'Mapping 1' not in obj.mappings.get('oldwin', {})
    assert 'newmousewin' in obj.mappings
    d = obj.mappings['newmousewin']['Mapping 1']
    assert d['mouse_button'] == 'right'
    assert d['press_count'] == 3
    assert d['keyboard_button'] == 'ctrl + alt + d' or d['keyboard_button'] == 'ctrl+alt+d'
    assert d['window_title'] == 'newmousewin'


def test_cancel_edit_preserves_original_mapping():
    obj = make_common_attrs()

    obj.mappings = {'win': {'Mapping 1': {'source_key': 'a', 'target_key': 'b', 'window_title': 'win'}}}
    obj.mapping_ids = ['Mapping 1']
    obj._editing_mapping_id = 'Mapping 1'

    # Simulate some UI fields changed while editing
    obj.source_keyboard_combobox = SimpleNamespace(currentText=lambda: 'changed')
    obj.window_selection_radio1 = SimpleNamespace(isChecked=lambda: True)
    obj.window_selection_entry = SimpleNamespace(text=lambda: 'win')

    # run cancel
    fn = m.KeyMapperApp._cancel_editing.__get__(obj, m.KeyMapperApp)
    fn()

    # editing id cleared
    assert getattr(obj, '_editing_mapping_id', None) is None

    # mapping remains unchanged
    assert 'Mapping 1' in obj.mappings['win']
    d = obj.mappings['win']['Mapping 1']
    assert d['source_key'] == 'a'
    assert d['target_key'] == 'b'


def test_reject_save_without_target_key_for_keyboard(monkeypatch):
    obj = make_common_attrs()
    obj.mappings = {'win': {'Mapping 1': {'source_key': 'a', 'target_key': 'b', 'window_title': 'win'}}}
    obj.mapping_ids = ['Mapping 1']
    obj._editing_mapping_id = 'Mapping 1'

    obj.source_keyboard_combobox = SimpleNamespace(currentText=lambda: 'x')
    obj.target_keyboard_combobox = SimpleNamespace(currentText=lambda: '')
    obj.window_selection_radio1 = SimpleNamespace(isChecked=lambda: True)
    obj.window_selection_entry = SimpleNamespace(text=lambda: 'win')

    # patch QMessageBox.warning to avoid GUI popups in tests and record calls
    called = {'warned': False}

    def fake_warning(parent, title, msg):
        called['warned'] = True

    monkeypatch.setattr(m, 'QMessageBox', SimpleNamespace(warning=fake_warning))

    fn = m.KeyMapperApp._save_edited_mapping.__get__(obj, m.KeyMapperApp)
    fn()

    # It should have presented a warning and not changed mappings
    assert called['warned'] is True
    assert obj._editing_mapping_id == 'Mapping 1'
    assert obj.mappings['win']['Mapping 1']['target_key'] == 'b'


def test_reject_save_without_target_key_for_mouse(monkeypatch):
    obj = make_common_attrs()
    obj.mappings = {'win': {'Mapping 1': {'mouse_button': 'left', 'press_count': 1, 'keyboard_button': 'z', 'window_title': 'win'}}}
    obj.mapping_ids = ['Mapping 1']
    obj._editing_mapping_id = 'Mapping 1'

    obj.source_keyboard_combobox = SimpleNamespace(currentText=lambda: '')
    obj.mouse_button_combobox = SimpleNamespace(currentText=lambda: 'left')
    obj.target_keyboard_combobox = SimpleNamespace(currentText=lambda: '')
    obj.press_count_entry = SimpleNamespace(text=lambda: '1')
    obj.window_selection_radio1 = SimpleNamespace(isChecked=lambda: True)
    obj.window_selection_entry = SimpleNamespace(text=lambda: 'win')

    called = {'warned': False}

    def fake_warning(parent, title, msg):
        called['warned'] = True

    monkeypatch.setattr(m, 'QMessageBox', SimpleNamespace(warning=fake_warning))

    fn = m.KeyMapperApp._save_edited_mapping.__get__(obj, m.KeyMapperApp)
    fn()

    assert called['warned'] is True
    assert obj._editing_mapping_id == 'Mapping 1'
    assert obj.mappings['win']['Mapping 1']['keyboard_button'] == 'z'
