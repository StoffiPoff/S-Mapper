import importlib
from types import SimpleNamespace

m = importlib.import_module('s_mapper')


def make_macro_obj():
    obj = type('O', (), {})()
    # minimal attributes used by _save_edited_macro/_cancel_macro_editing
    obj.macros = []
    obj.macros_by_id = {}
    obj.mappings = {}
    obj.mapping_ids = []
    obj._editing_macro_id = None
    # UI fields
    obj.macro_name_entry = SimpleNamespace(text=lambda: '')
    obj.macro_actions_text = SimpleNamespace(toPlainText=lambda: '')
    obj.macro_trigger_key_rb = SimpleNamespace(isChecked=lambda: False)
    obj.macro_key_combobox = SimpleNamespace(currentText=lambda: '')
    obj.macro_trigger_mouse_rb = SimpleNamespace(isChecked=lambda: False)
    obj.macro_mouse_button_combobox = SimpleNamespace(currentText=lambda: '')
    obj.macro_mouse_presses = SimpleNamespace(value=lambda: 1)
    obj.macro_trigger_window_entry = SimpleNamespace(text=lambda: '')
    obj._add_mapping_details = lambda details, mapping_id=None: setattr(obj, '_last_added_mapping', (details, mapping_id))
    obj._refresh_macros_display = lambda: None
    obj.add_macro_button = SimpleNamespace(setText=lambda s: setattr(obj, '_add_text', s))
    obj.cancel_macro_edit_button = SimpleNamespace(setVisible=lambda v: setattr(obj, '_cancel_visible', v))
    return obj


def test_save_edited_macro_updates_macro_and_mapping():
    obj = make_macro_obj()

    # existing macro
    macro = {'id': 'Macro 1', 'name': 'orig', 'actions': ['text:old'], 'trigger_type': 'none'}
    obj.macros = [macro]
    obj.macros_by_id = {'Macro 1': macro}

    # Enter edit mode
    obj._editing_macro_id = 'Macro 1'

    # UI fields changed
    obj.macro_name_entry = SimpleNamespace(text=lambda: 'newname')
    obj.macro_actions_text = SimpleNamespace(toPlainText=lambda: 'text:Hello')
    obj.macro_trigger_key_rb = SimpleNamespace(isChecked=lambda: True)
    obj.macro_key_combobox = SimpleNamespace(currentText=lambda: 'g')
    obj.macro_trigger_window_entry = SimpleNamespace(text=lambda: 'Win')

    handler = m.KeyMapperApp._save_edited_macro.__get__(obj, m.KeyMapperApp)
    handler()

    # macro updated in place
    assert obj.macros[0]['name'] == 'newname'
    assert obj.macros_by_id['Macro 1']['actions'] == ['text:Hello']

    # mapping was added for macro id
    assert getattr(obj, '_last_added_mapping', None) is not None
    details, mapping_id = obj._last_added_mapping
    assert mapping_id == 'Macro 1'
    assert details['type'] == 'macro'
    assert details['source_key'] == 'g'


def test_cancel_macro_editing_clears_edit_state_and_preserves_macro():
    obj = make_macro_obj()
    macro = {'id': 'Macro X', 'name': 'keep', 'actions': ['text:ok'], 'trigger_type': 'none'}
    obj.macros = [macro]
    obj.macros_by_id = {'Macro X': macro}

    obj._editing_macro_id = 'Macro X'

    # simulate changes in UI but cancel should discard them
    obj.macro_name_entry = SimpleNamespace(text=lambda: 'changed')

    fn = m.KeyMapperApp._cancel_macro_editing.__get__(obj, m.KeyMapperApp)
    fn()

    assert getattr(obj, '_editing_macro_id', None) is None
    # original unchanged
    assert obj.macros[0]['name'] == 'keep'
