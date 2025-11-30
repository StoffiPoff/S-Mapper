import importlib
import tempfile
import os


def test_save_and_load_macros_roundtrip(monkeypatch, tmp_path):
    m = importlib.import_module('s_mapper')

    # Ensure KeyMapperApp methods bound to light stub behave as expected
    obj = type('O', (), {})()
    obj.macros = []
    obj.macros_by_id = {}
    obj.mapping_counter = 1

    # prepare a macro
    macro = {
        'id': 'Macro 3',
        'name': 'Roundtrip',
        'actions': ['text:Hello', 'sleep:0.1'],
        'trigger_type': 'keyboard',
        'source_key': 'x',
        'mouse_button': '',
        'press_count': 0,
        'window_title': 'SomeWin',
    }

    obj.macros.append(macro)
    obj.macros_by_id['Macro 3'] = macro

    # set LOCALAPPDATA to temp dir so file is written there
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))

    # provide config filepath helper so method can resolve destination
    obj._get_macros_filepath = lambda: str(tmp_path / 'macros.ini')
    obj._refresh_macros_display = lambda: None
    saver = m.KeyMapperApp.save_macros_to_config.__get__(obj, m.KeyMapperApp)
    saver()

    # file should exist
    files = list(tmp_path.glob('*'))
    assert any(p.name == 'macros.ini' for p in files)

    # clear and load
    obj.macros = []
    obj.macros_by_id = {}

    loader = m.KeyMapperApp.load_macros_from_config.__get__(obj, m.KeyMapperApp)
    loader()

    assert len(obj.macros) == 1
    loaded = obj.macros[0]
    assert loaded['id'] == 'Macro 3'
    assert loaded['name'] == 'Roundtrip'
    assert loaded['actions'][0] == 'text:Hello'


def test_mapping_counter_updated_by_loaded_macros(monkeypatch, tmp_path):
    m = importlib.import_module('s_mapper')

    obj = type('O', (), {})()
    obj.macros = []
    obj.macros_by_id = {}
    obj.mapping_counter = 2

    # create macros.ini with Macro 99 present
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    ini = tmp_path / 'macros.ini'
    content = """[Macro 99]
name = Big
actions = text:Hi
trigger_type = none
source_key =
mouse_button =
press_count = 0
window_title =
"""
    ini.write_text(content)

    obj._get_macros_filepath = lambda: str(tmp_path / 'macros.ini')
    obj._refresh_macros_display = lambda: None
    loader = m.KeyMapperApp.load_macros_from_config.__get__(obj, m.KeyMapperApp)
    loader()

    # mapping_counter should jump past 99
    assert obj.mapping_counter > 99


def test_remove_selected_macro_deletes_mapping_and_saves(monkeypatch, tmp_path):
    m = importlib.import_module('s_mapper')
    from types import SimpleNamespace

    obj = type('O', (), {})()
    # create a macro and an associated mapping referencing it
    macro = {'id': 'Macro 1', 'name': 'one', 'actions': [], 'trigger_type': 'keyboard'}
    obj.macros = [macro]
    obj.macros_by_id = {'Macro 1': macro}
    obj.mappings = {'somewin': {'Macro 1': {'type': 'macro', 'macro_id': 'Macro 1', 'window_title': 'somewin'}}}
    obj.macros_listbox = SimpleNamespace(currentRow=lambda: 0)
    obj._refresh_macros_display = lambda: None

    called = {'macros_saved': False, 'mappings_saved': False}
    obj.save_macros_to_config = lambda: called.update({'macros_saved': True})
    obj.save_mappings_to_config = lambda: called.update({'mappings_saved': True})

    handler = m.KeyMapperApp._remove_selected_macro.__get__(obj, m.KeyMapperApp)
    handler()

    # mapping removed
    assert 'Macro 1' not in obj.mappings.get('somewin', {})
    # persistence attempted
    assert called['macros_saved'] is True
    assert called['mappings_saved'] is True
