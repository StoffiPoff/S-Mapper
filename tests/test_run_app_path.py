import importlib, runpy, sys
from pathlib import Path


def test_run_app_inserts_parent_dir_into_syspath(tmp_path, monkeypatch):
    # Simulate running run_app.py from a different working directory
    repo = Path(__file__).resolve().parents[1]
    runner = repo / 'run_app.py'
    assert runner.exists()

    # Emulate running run_app in a different working directory
    monkeypatch.chdir(tmp_path)

    # Import the runner module and call the helper to ensure it adds the repo
    # to sys.path. Importing won't execute the __main__ block.
    mod = importlib.import_module('run_app')
    result = mod.ensure_repo_on_syspath()
    assert result is not None
    assert str(repo) in sys.path
