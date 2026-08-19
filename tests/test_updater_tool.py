"""updater_tool.py（安装版独立更新工具）单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from updater_tool import apply_installer, main


@pytest.mark.unit
def test_main_missing_args():
    assert main([]) == 1


@pytest.mark.unit
def test_apply_installer_missing_setup(tmp_path):
    assert apply_installer(tmp_path / "nope.exe", install_dir="") == 2


@pytest.mark.unit
def test_apply_installer_waits_and_runs(tmp_path, monkeypatch):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"MZ")
    calls = []
    monkeypatch.setattr("updater_tool.wait_for_pid", lambda pid, timeout=120.0: True)
    monkeypatch.setattr(
        "updater_tool.run_installer",
        lambda setup, install_dir="", timeout=600.0: calls.append(
            (str(setup), install_dir)
        )
        or 0,
    )
    monkeypatch.setattr(
        "updater_tool.subprocess.Popen", lambda *a, **k: None
    )
    code = apply_installer(setup, install_dir=r"C:\Apps\批图王", wait_pid=1234)
    assert code == 0
    assert calls == [(str(setup), r"C:\Apps\批图王")]


@pytest.mark.unit
def test_apply_installer_wait_timeout(tmp_path, monkeypatch):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"MZ")
    monkeypatch.setattr("updater_tool.wait_for_pid", lambda pid, timeout=120.0: False)
    assert apply_installer(setup, wait_pid=9) == 3


@pytest.mark.unit
def test_apply_installer_install_failure(tmp_path, monkeypatch):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"MZ")
    monkeypatch.setattr("updater_tool.wait_for_pid", lambda pid, timeout=120.0: True)
    monkeypatch.setattr(
        "updater_tool.run_installer", lambda setup, install_dir="", timeout=600.0: 1
    )
    assert apply_installer(setup, wait_pid=0) == 4


@pytest.mark.unit
def test_apply_installer_relaunch_when_target_exists(tmp_path, monkeypatch):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"MZ")
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    (install_dir / "批图王.exe").write_bytes(b"MZ")
    spawned = []
    monkeypatch.setattr("updater_tool.wait_for_pid", lambda pid, timeout=120.0: True)
    monkeypatch.setattr(
        "updater_tool.run_installer", lambda setup, install_dir="", timeout=600.0: 0
    )
    monkeypatch.setattr(
        "updater_tool.subprocess.Popen",
        lambda cmd, **kwargs: spawned.append(cmd) or None,
    )
    code = apply_installer(setup, install_dir=str(install_dir), wait_pid=0)
    assert code == 0
    assert spawned and spawned[0][0] == str(install_dir / "批图王.exe")


@pytest.mark.unit
def test_main_apply_installer_args(tmp_path, monkeypatch):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"MZ")
    calls = []
    monkeypatch.setattr(
        "updater_tool.apply_installer",
        lambda *a, **k: calls.append((a, k)) or 0,
    )
    code = main(
        [
            "--apply-installer",
            str(setup),
            "--install-dir",
            r"C:\Apps",
            "--wait-pid",
            "42",
        ]
    )
    assert code == 0
    assert calls and calls[0][0][0] == str(setup)
    assert calls[0][1]["install_dir"] == r"C:\Apps"
    assert calls[0][1]["wait_pid"] == 42
