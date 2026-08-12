from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_build_generates_onedir_installer_and_onefile_portable_outputs():
    source = (REPO_ROOT / "build.py").read_text(encoding="utf-8")

    assert "pyinstaller_command(mode='onedir'" in source
    assert "pyinstaller_command(\n            mode='onefile'" in source
    assert "f'--specpath={specpath}'" in source
    assert "build' / 'installer'" in source
    assert "build' / 'portable'" in source


@pytest.mark.unit
def test_nsis_installs_the_onedir_tree():
    source = (REPO_ROOT / "installer" / "批图王.nsi").read_text(encoding="utf-8-sig")

    assert 'File /r "..\\dist\\${APP_NAME}\\*"' in source
    assert 'CreateShortcut "$DESKTOP\\${APP_NAME}.lnk" "$INSTDIR\\${APP_EXE}"' in source
    assert 'RMDir /r "$INSTDIR"' in source


@pytest.mark.unit
def test_checked_in_spec_uses_onedir_collect_layout():
    source = (REPO_ROOT / "批图王.spec").read_text(encoding="utf-8")

    assert "exclude_binaries=True" in source
    assert "coll = COLLECT(" in source
    assert "a.binaries" in source
    assert "a.datas" in source
