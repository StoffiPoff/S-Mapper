import importlib


def test_save_and_load_ip_monitor_window_field(monkeypatch, tmp_path):
    m = importlib.import_module('s_mapper')

    obj = type('O', (), {})()
    from PyQt6.QtCore import QMutex
    obj.mappings_lock = QMutex()
    obj.mappings = {}
    obj.mapping_ids = []
    obj._kbd_available = False
    obj._kbd_enabled = False
    obj.update_mappings_display = lambda: None
    obj._refresh_macros_display = lambda: None
    obj._refresh_macros_display = lambda: None
    obj.ip_monitor_window_entry = type('E', (), {'text': lambda self: 'MyPingWin', 'setText': lambda self, v: setattr(obj, 'loaded_ip', v)})()
    obj.click_interval = 1.23
    obj.click_interval_spinbox = type('S', (), {'setValue': lambda self, v: setattr(obj, 'spin', v)})()

    # ensure config path lands in tmpdir
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    obj._get_config_filepath = lambda: str(tmp_path / 'mappings.ini')

    saver = m.KeyMapperApp.save_mappings_to_config.__get__(obj, m.KeyMapperApp)
    saver()

    # clear the setting then load
    obj.ip_monitor_window_entry = type('E2', (), {'text': lambda self: '', 'setText': lambda self, v: setattr(obj, 'loaded_ip', v)})()

    loader = m.KeyMapperApp.load_mappings_from_config.__get__(obj, m.KeyMapperApp)
    loader()

    assert getattr(obj, 'loaded_ip', None) == 'MyPingWin'