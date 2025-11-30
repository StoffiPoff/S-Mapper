import importlib
import threading

m = importlib.import_module('s_mapper')


class Dummy:
    pass


obj = Dummy()
obj._active_title_lock = threading.Lock()
obj._cached_active_title = ''
obj._update_hooks_for_active_title = lambda active_title: None
obj._kbd_available = True
obj.mappings = {'': {'Mapping 1': {'source_key': 'a', 'target_key': 'b', 'window_title': ''}}}
obj._keyboard_hooks = {}
obj._kbd_ignore = {}
obj._source_index = {}
class Sig:
    def emit(self, x):
        print('EMIT', x)
obj.mapping_action_signal = Sig()
obj._refresh_keyboard_hooks = m.KeyMapperApp._refresh_keyboard_hooks.__get__(obj, m.KeyMapperApp)
obj._refresh_keyboard_hooks()
print('hooks installed:', list(obj._keyboard_hooks.keys()))
