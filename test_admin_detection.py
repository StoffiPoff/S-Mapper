import importlib

m = importlib.import_module('s_mapper')


def test_is_running_as_admin_windows_true(monkeypatch):
    # Simulate running on Windows with elevated privileges
    monkeypatch.setattr(m, '_check_admin_windows', lambda: True)
    monkeypatch.setattr(m.os, 'name', 'nt', raising=False)
    assert m.is_running_as_admin() is True


def test_is_running_as_admin_windows_false(monkeypatch):
    monkeypatch.setattr(m, '_check_admin_windows', lambda: False)
    monkeypatch.setattr(m.os, 'name', 'nt', raising=False)
    assert m.is_running_as_admin() is False


def test_is_running_as_admin_unix_true(monkeypatch):
    monkeypatch.setattr(m, '_check_admin_unix', lambda: True)
    monkeypatch.setattr(m.os, 'name', 'posix', raising=False)
    assert m.is_running_as_admin() is True


def test_is_running_as_admin_unix_false(monkeypatch):
    monkeypatch.setattr(m, '_check_admin_unix', lambda: False)
    monkeypatch.setattr(m.os, 'name', 'posix', raising=False)
    assert m.is_running_as_admin() is False
