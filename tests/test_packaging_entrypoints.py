import re
from pathlib import Path


def test_specs_use_run_app():
    root = Path(__file__).resolve().parents[1]
    specs = ['s_mapper.spec', 's_mapper_full.spec', 's_mapper_lite.spec', 's_mapper_rebuild.spec']
    for s in specs:
        p = root / s
        assert p.exists(), f"Spec file {s} missing"
        content = p.read_text(encoding='utf8')
        # Ensure they reference run_app.py rather than s_mapper/app.py or s_mapper.py
        assert 'run_app.py' in content, f"{s} should use run_app.py as entrypoint"
        assert 's_mapper\\app.py' not in content and "s_mapper.py" not in content, f"{s} still references legacy script"


def test_build_script_uses_run_app():
    root = Path(__file__).resolve().parents[1]
    bs = root / 'build_msix.ps1'
    assert bs.exists()
    txt = bs.read_text(encoding='utf8')
    assert 'run_app.py' in txt, 'build_msix.ps1 should invoke run_app.py when invoking PyInstaller'