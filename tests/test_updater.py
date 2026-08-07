"""app/utils/updater.py 自动更新逻辑单元测试。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.utils import updater

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_get_current_version_matches_app_version():
    from app.version import APP_VERSION

    assert updater.get_current_version() == str(APP_VERSION)


@pytest.mark.unit
def test_normalize_version():
    assert updater.normalize_version("1.2.3") == (1, 2, 3)
    assert updater.normalize_version("v2.0.0") == (2, 0, 0)
    assert updater.normalize_version("1.2.3.4") == (1, 2, 3, 4)
    assert updater.normalize_version("") == (0,)
    assert updater.normalize_version("abc") == (0,)


@pytest.mark.unit
def test_is_newer():
    assert updater.is_newer("1.1.0", "1.0.0") is True
    assert updater.is_newer("1.0.0", "1.0.0") is False
    assert updater.is_newer("1.0.0", "1.1.0") is False
    assert updater.is_newer("2.0", "1.9.9") is True
    assert updater.is_newer("1.0.1", "1.0") is True
    assert updater.is_newer("0.9.9", "1.0.0") is False


@pytest.mark.unit
def test_fetch_update_info_from_local_file(tmp_path):
    manifest = tmp_path / "update.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "2.0.0",
                "release_notes": "test notes",
                "download_url": "https://example.com/app.exe",
                "installer_url": "https://example.com/setup.exe",
                "required": True,
                "published_at": "2026-08-07",
            }
        ),
        encoding="utf-8",
    )
    url = manifest.as_uri()
    info = updater.fetch_update_info(url)
    assert info.version == "2.0.0"
    assert info.release_notes == "test notes"
    assert info.required is True
    assert info.download_url == "https://example.com/app.exe"
    assert info.installer_url == "https://example.com/setup.exe"
    assert info.published_at == "2026-08-07"
    assert info.manifest_url == url


@pytest.mark.unit
def test_fetch_update_info_missing_fields_default(tmp_path):
    manifest = tmp_path / "update.json"
    manifest.write_text(json.dumps({"version": "2.0.0"}), encoding="utf-8")
    info = updater.fetch_update_info(manifest.as_uri())
    assert info.release_notes == ""
    assert info.download_url == ""
    assert info.installer_url == ""
    assert info.required is False


@pytest.mark.unit
def test_check_for_update_detects_newer(tmp_path):
    manifest = tmp_path / "update.json"
    manifest.write_text(
        json.dumps({"version": "1.1.0", "download_url": "https://example.com/u"}),
        encoding="utf-8",
    )
    info = updater.check_for_update(manifest.as_uri(), current_version="1.0.0")
    assert info is not None
    assert info.version == "1.1.0"


@pytest.mark.unit
def test_check_for_update_returns_none_when_same_or_older(tmp_path):
    manifest = tmp_path / "update.json"
    manifest.write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")
    assert updater.check_for_update(manifest.as_uri(), current_version="1.0.0") is None
    manifest.write_text(json.dumps({"version": "0.9.0"}), encoding="utf-8")
    assert updater.check_for_update(manifest.as_uri(), current_version="1.0.0") is None


@pytest.mark.unit
def test_download_file_from_local(tmp_path):
    source = tmp_path / "source.bin"
    payload = b"0123456789" * 100
    source.write_bytes(payload)
    dest = tmp_path / "out" / "file.bin"
    progress = []
    result = updater.download_file(
        source.as_uri(),
        dest,
        progress_cb=lambda received, total: progress.append((received, total)),
    )
    assert result == dest
    assert dest.read_bytes() == payload
    assert progress[-1][0] == len(payload)


@pytest.mark.unit
def test_committed_update_manifest_is_in_sync():
    manifest_path = REPO_ROOT / "update" / "update.json"
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["version"] == updater.get_current_version()
    assert payload["download_url"].startswith("https://github.com/")
    assert payload["installer_url"].startswith("https://github.com/")


@pytest.mark.unit
def test_parse_apply_update_args():
    new_exe, wait_pid, relaunch = updater.parse_apply_update_args(
        ["--apply-update", r"C:\tmp\批图王_new.exe", "--wait-pid", "1234"]
    )
    assert new_exe == r"C:\tmp\批图王_new.exe"
    assert wait_pid == 1234
    assert relaunch is True

    new_exe, wait_pid, relaunch = updater.parse_apply_update_args(["--no-relaunch"])
    assert new_exe == ""
    assert wait_pid == 0
    assert relaunch is False

    new_exe, wait_pid, _ = updater.parse_apply_update_args(["--wait-pid", "abc"])
    assert wait_pid == 0
    assert new_exe == ""


@pytest.mark.unit
def test_main_forwards_apply_update_flag_to_argument_parser():
    source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")

    assert "parse_apply_update_args(sys.argv[1:])" in source


@pytest.mark.unit
def test_apply_update_stops_when_main_process_does_not_exit(tmp_path, monkeypatch):
    current_exe = tmp_path / "batch-image-king.exe"
    new_exe = tmp_path / "batch-image-king_new.exe"
    current_exe.write_bytes(b"old")
    new_exe.write_bytes(b"new")
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "wait_for_process", lambda *args, **kwargs: False)

    result = updater.apply_update(
        new_exe,
        current_exe=current_exe,
        wait_pid=1234,
        relaunch=False,
    )

    assert result == 4
    assert current_exe.read_bytes() == b"old"
    assert new_exe.read_bytes() == b"new"


@pytest.mark.unit
def test_wait_for_process_returns_when_pid_gone():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert updater.wait_for_process(proc.pid, timeout=5) is True


@pytest.mark.unit
def test_qml_registers_update_manager():
    qml_main = (REPO_ROOT / "app" / "qml" / "qml_main.py").read_text(encoding="utf-8")
    main_qml = (REPO_ROOT / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")

    assert "UpdateViewModel" in qml_main
    assert 'setContextProperty("updateManager", update_manager)' in qml_main
    assert "checkForUpdatesSilent" in qml_main
    assert 'id: "updateDialog"' in main_qml or "id: updateDialog" in main_qml
    assert "id: helpMenu" in main_qml
    assert "id: updateBanner" in main_qml
    assert "updateManager.readyToInstall" in main_qml
    assert "updateManager.installDownloadedUpdate()" in main_qml
    assert "pendingUpdateInstall" in main_qml
    assert "restartRequested.connect" not in qml_main


@pytest.mark.unit
def test_download_completion_waits_for_explicit_install(tmp_path, monkeypatch):
    from app.qml.viewmodels.update_view_model import UpdateViewModel

    downloaded_exe = tmp_path / "batch-image-king_new.exe"
    downloaded_exe.write_bytes(b"new")
    spawn_calls = []
    finished = []
    restarts = []
    monkeypatch.setattr(updater, "new_exe_path", lambda: downloaded_exe)
    monkeypatch.setattr(
        updater,
        "spawn_apply_update",
        lambda **kwargs: spawn_calls.append(kwargs) or True,
    )
    view_model = UpdateViewModel()
    view_model.updateFinished.connect(lambda ok, message: finished.append((ok, message)))
    view_model.restartRequested.connect(lambda: restarts.append(True))

    view_model._on_download_done(True, "")

    assert view_model.readyToInstall is True
    assert spawn_calls == []
    assert finished and finished[-1][0] is True

    assert view_model.installDownloadedUpdate() is True
    assert len(spawn_calls) == 1
    assert spawn_calls[0]["new_exe"] == downloaded_exe
    assert restarts == [True]


@pytest.mark.unit
def test_install_failure_keeps_application_open(tmp_path, monkeypatch):
    from app.qml.viewmodels.update_view_model import UpdateViewModel

    downloaded_exe = tmp_path / "batch-image-king_new.exe"
    downloaded_exe.write_bytes(b"new")
    monkeypatch.setattr(updater, "new_exe_path", lambda: downloaded_exe)
    monkeypatch.setattr(updater, "spawn_apply_update", lambda **kwargs: False)
    view_model = UpdateViewModel()
    failures = []
    restarts = []
    view_model.updateFinished.connect(lambda ok, message: failures.append((ok, message)))
    view_model.restartRequested.connect(lambda: restarts.append(True))
    view_model._on_download_done(True, "")

    assert view_model.installDownloadedUpdate() is False
    assert view_model.readyToInstall is True
    assert view_model.errorMessage
    assert failures[-1][0] is False
    assert restarts == []


@pytest.mark.unit
def test_nsis_installer_script_has_utf8_bom():
    script = REPO_ROOT / "installer" / "批图王.nsi"
    assert script.exists()
    assert script.read_bytes()[:3] == b"\xef\xbb\xbf"
