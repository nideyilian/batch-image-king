"""app/utils/updater.py 自动更新逻辑单元测试。"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import subprocess
import sys
import threading
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


@pytest.mark.unit
def test_nsis_downgrade_guard_aborts_only_when_installed_is_higher():
    """降级保护必须仅在「本机版本高于安装包」时中止。

    VersionCompare 返回：0=相等，1=第一个参数(本机)更高，2=第二个参数(安装包)更高。
    因此中止条件必须是 $1 == 1；写成 $1 > 0 会把「安装包更高」(2) 也误判为降级。
    """
    script = REPO_ROOT / "installer" / "批图王.nsi"
    text = script.read_text(encoding="utf-8-sig")
    assert '${VersionCompare} "$0" "${APP_VERSION}" $1' in text
    assert "${If} $1 == 1" in text
    assert "${If} $1 > 0" not in text


@pytest.mark.unit
def test_manifest_candidates_include_default_and_mirrors(monkeypatch):
    monkeypatch.delenv("BTPW_UPDATE_URL", raising=False)
    urls = updater._manifest_url_candidates()
    assert urls[0] == updater.DEFAULT_MANIFEST_URL
    assert updater.MANIFEST_MIRRORS[0] in urls


@pytest.mark.unit
def test_manifest_candidates_prefers_explicit_and_env(monkeypatch):
    monkeypatch.setenv("BTPW_UPDATE_URL", "https://mirror.example/update.json")
    urls = updater._manifest_url_candidates("https://explicit.example/update.json")
    assert urls[0] == "https://explicit.example/update.json"
    assert urls[1] == "https://mirror.example/update.json"
    assert updater.DEFAULT_MANIFEST_URL in urls


@pytest.mark.unit
def test_expand_download_urls_adds_proxies():
    official = (
        "https://github.com/nideyilian/batch-image-king/releases/download/"
        "v1.2.0/batch-image-king.exe"
    )
    urls = updater.expand_download_urls(official)
    assert urls[0] == official
    assert len(urls) == 1 + len(updater.GITHUB_PROXY_PREFIXES)
    for prefix in updater.GITHUB_PROXY_PREFIXES:
        assert prefix + official in urls


@pytest.mark.unit
def test_expand_download_urls_keeps_non_github():
    url = "https://example.com/app.exe"
    assert updater.expand_download_urls(url) == [url]


@pytest.mark.unit
def test_download_update_falls_back_to_next_url(tmp_path):
    good = tmp_path / "good.bin"
    payload = b"hello" * 100
    good.write_bytes(payload)
    missing = (tmp_path / "missing.bin").as_uri()
    dest = tmp_path / "out" / "app.bin"
    result = updater.download_update([missing, good.as_uri()], dest)
    assert result == dest
    assert dest.read_bytes() == payload


@pytest.mark.unit
def test_download_update_all_fail_raises(tmp_path):
    missing1 = (tmp_path / "m1.bin").as_uri()
    missing2 = (tmp_path / "m2.bin").as_uri()
    dest = tmp_path / "out" / "app.bin"
    with pytest.raises(Exception):
        updater.download_update([missing1, missing2], dest)


@pytest.mark.unit
def test_download_update_verifies_sha256(tmp_path):
    import hashlib

    good = tmp_path / "good.bin"
    payload = b"payload" * 50
    good.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    dest = tmp_path / "out" / "app.bin"
    assert updater.download_update([good.as_uri()], dest, sha256=digest) == dest
    assert dest.read_bytes() == payload


@pytest.mark.unit
def test_download_update_rejects_wrong_sha256(tmp_path):
    good = tmp_path / "good.bin"
    good.write_bytes(b"payload" * 50)
    dest = tmp_path / "out" / "app.bin"
    with pytest.raises(updater.UpdateIntegrityError):
        updater.download_update([good.as_uri()], dest, sha256="0" * 64)
    assert not dest.exists()


@pytest.mark.unit
def test_check_for_update_falls_back_to_mirror(tmp_path, monkeypatch):
    manifest = tmp_path / "update.json"
    manifest.write_text(
        json.dumps({"version": "2.0.0", "download_url": "https://example.com/u"}),
        encoding="utf-8",
    )
    missing = (tmp_path / "missing.json").as_uri()
    monkeypatch.setattr(updater, "DEFAULT_MANIFEST_URL", missing)
    monkeypatch.setattr(updater, "MANIFEST_MIRRORS", [manifest.as_uri()])
    monkeypatch.delenv("BTPW_UPDATE_URL", raising=False)
    info = updater.check_for_update(missing, current_version="1.0.0")
    assert info is not None
    assert info.version == "2.0.0"


# ---------------------------------------------------------------- 安装形态与分流


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    payload = b""
    support_range = True
    requested_ranges = []

    def do_GET(self):  # noqa: N802
        type(self).requested_ranges.append(self.headers.get("Range", ""))
        if not self.support_range:
            body = self.payload
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            body = self.payload[start:]
            self.send_response(206)
            self.send_header(
                "Content-Range",
                f"bytes {start}-{len(self.payload) - 1}/{len(self.payload)}",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = self.payload
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *args):  # noqa: A002
        pass


@pytest.fixture
def range_server():
    _RangeHandler.payload = os.urandom(200 * 1024)
    _RangeHandler.support_range = True
    _RangeHandler.requested_ranges = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/file.bin"
    try:
        yield url
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.unit
def test_download_file_resumes_from_partial(tmp_path, range_server):
    url = range_server
    payload = _RangeHandler.payload
    dest = tmp_path / "app.bin"
    tmp = dest.with_name(dest.name + ".download")
    tmp.write_bytes(payload[:1000])  # 模拟已有部分下载
    assert updater.download_file(url, dest) == dest
    assert dest.read_bytes() == payload
    assert _RangeHandler.requested_ranges[-1] == "bytes=1000-"


@pytest.mark.unit
def test_download_file_restarts_when_server_no_range(tmp_path, range_server):
    url = range_server
    payload = _RangeHandler.payload
    _RangeHandler.support_range = False
    dest = tmp_path / "app.bin"
    tmp = dest.with_name(dest.name + ".download")
    tmp.write_bytes(b"garbage-partial")
    assert updater.download_file(url, dest) == dest
    assert dest.read_bytes() == payload


@pytest.mark.unit
def test_download_file_resume_progress_starts_at_offset(tmp_path, range_server):
    url = range_server
    payload = _RangeHandler.payload
    dest = tmp_path / "app.bin"
    tmp = dest.with_name(dest.name + ".download")
    tmp.write_bytes(payload[:1000])
    progress = []
    updater.download_file(url, dest, progress_cb=lambda r, t: progress.append((r, t)))
    # 进度从已有偏移之后开始累计，最终等于完整大小
    assert progress[0][0] > 1000
    assert progress[-1][0] == len(payload)


@pytest.mark.unit
def test_download_update_keeps_partial_for_resume(tmp_path, monkeypatch):
    good = tmp_path / "good.bin"
    good.write_bytes(b"x" * 100)
    dest = tmp_path / "out" / "app.bin"
    tmp = dest.with_name(dest.name + ".download")

    def fake_download(url, dest, progress_cb=None):
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(b"partial")
        raise ConnectionError("broken")

    monkeypatch.setattr(updater, "download_file", fake_download)
    with pytest.raises(Exception):
        updater.download_update([good.as_uri()], dest)
    assert tmp.exists()  # 部分下载保留，供续传
    assert not dest.exists()


@pytest.mark.unit
def test_fetch_update_info_parses_installer_sha256(tmp_path):
    manifest = tmp_path / "update.json"
    manifest.write_text(
        json.dumps({"version": "2.0.0", "installer_sha256": "abc123"}),
        encoding="utf-8",
    )
    info = updater.fetch_update_info(manifest.as_uri())
    assert info.installer_sha256 == "abc123"
    assert info.sha256 == ""


@pytest.mark.unit
def test_is_onedir_install(tmp_path):
    onedir_exe = tmp_path / "app" / "批图王.exe"
    onedir_exe.parent.mkdir(parents=True)
    (onedir_exe.parent / "_internal").mkdir()
    assert updater.is_onedir_install(onedir_exe) is True
    assert updater.is_onedir_install(tmp_path / "portable.exe") is False


@pytest.mark.unit
def test_update_download_target_installer(tmp_path, monkeypatch):
    info = updater.UpdateInfo(
        version="2.0.0",
        download_url="https://example.com/a.exe",
        installer_url="https://example.com/setup.exe",
        sha256="aa",
        installer_sha256="bb",
    )
    exe = tmp_path / "批图王.exe"
    (tmp_path / "_internal").mkdir()
    (tmp_path / "updater_tool.exe").write_bytes(b"MZ")
    monkeypatch.setattr(updater, "exe_path", lambda: exe)
    target = updater.update_download_target(info)
    assert target.kind == "installer"
    assert target.url == info.installer_url
    assert target.sha256 == "bb"
    assert target.dest.name == "批图王-Setup_new.exe"


@pytest.mark.unit
def test_update_download_target_portable(tmp_path, monkeypatch):
    info = updater.UpdateInfo(
        version="2.0.0",
        download_url="https://example.com/a.exe",
        installer_url="https://example.com/setup.exe",
        sha256="aa",
    )
    exe = tmp_path / "批图王.exe"
    monkeypatch.setattr(updater, "exe_path", lambda: exe)  # 无 _internal → 便携版
    target = updater.update_download_target(info)
    assert target.kind == "portable"
    assert target.url == info.download_url
    assert target.sha256 == "aa"
    assert target.dest.name == "批图王_new.exe"


@pytest.mark.unit
def test_find_local_update_returns_newer(tmp_path, monkeypatch):
    local = tmp_path / "批图王_new.exe"
    local.write_bytes(b"MZ")
    monkeypatch.setattr(updater, "new_exe_path", lambda: local)
    monkeypatch.setattr(updater, "get_current_version", lambda: "1.0.0")
    monkeypatch.setattr(updater, "read_exe_version", lambda path: "1.2.0")
    assert updater.find_local_update() == local


@pytest.mark.unit
def test_find_local_update_ignores_older(tmp_path, monkeypatch):
    local = tmp_path / "批图王_new.exe"
    local.write_bytes(b"MZ")
    monkeypatch.setattr(updater, "new_exe_path", lambda: local)
    monkeypatch.setattr(updater, "get_current_version", lambda: "2.0.0")
    monkeypatch.setattr(updater, "read_exe_version", lambda path: "1.2.0")
    assert updater.find_local_update() is None


@pytest.mark.unit
def test_spawn_installer_update_command(monkeypatch, tmp_path):
    tool = tmp_path / "updater_tool.exe"
    tool.write_bytes(b"MZ")
    setup = tmp_path / "setup_new.exe"
    setup.write_bytes(b"MZ")
    monkeypatch.setattr(updater, "updater_tool_path", lambda: tool)
    spawns = []

    def fake_popen(cmd, **kwargs):
        spawns.append(cmd)
        return None

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)
    assert updater.spawn_installer_update(setup, install_dir=r"C:\Apps", wait_pid=42) is True
    assert spawns[0][0] == str(tool)
    assert "--apply-installer" in spawns[0]
    assert str(setup) in spawns[0]
    assert "--install-dir" in spawns[0]
    assert r"C:\Apps" in spawns[0]


# ---------------------------------------------------------------- ViewModel 分流


@pytest.mark.unit
def test_launch_installer_update_uses_tool(tmp_path, monkeypatch):
    from app.qml.viewmodels.update_view_model import UpdateViewModel

    setup = tmp_path / "setup_new.exe"
    setup.write_bytes(b"MZ")
    target = updater.DownloadTarget(kind="installer", url="", sha256="", dest=setup)
    calls = []
    monkeypatch.setattr(
        updater,
        "installed_dir",
        lambda: r"C:\Apps\批图王",
    )
    monkeypatch.setattr(
        updater,
        "spawn_installer_update",
        lambda setup_exe, install_dir="", wait_pid=0, relaunch=True: calls.append(
            (str(setup_exe), install_dir, wait_pid)
        )
        or True,
    )
    vm = UpdateViewModel()
    vm._target = target
    restarts = []
    vm.restartRequested.connect(lambda: restarts.append(True))
    assert vm._launch_apply_update() is True
    assert calls and calls[0][0] == str(setup)
    assert calls[0][1] == r"C:\Apps\批图王"
    assert restarts == [True]


@pytest.mark.unit
def test_install_local_update_spawns_apply(tmp_path, monkeypatch):
    from app.qml.viewmodels.update_view_model import UpdateViewModel

    local = tmp_path / "批图王_new.exe"
    local.write_bytes(b"MZ")
    calls = []
    monkeypatch.setattr(
        updater,
        "spawn_apply_update",
        lambda wait_pid, new_exe, current_exe=None: calls.append(str(new_exe)) or True,
    )
    vm = UpdateViewModel()
    vm._local_update_path = local
    vm.prepareLocalInstall()
    assert vm.installDownloadedUpdate() is True
    assert calls == [str(local)]


# ---------------------------------------------------------------- build.py 清单


@pytest.mark.unit
def test_build_manifest_includes_installer_sha256(tmp_path, monkeypatch):
    import build as build_module

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "批图王.exe").write_bytes(b"portable")
    (dist / "批图王-Setup.exe").write_bytes(b"setup")
    monkeypatch.setattr(build_module, "REPO_ROOT", tmp_path)
    manifest = build_module.write_update_manifest("9.9.9")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["version"] == "9.9.9"
    assert payload["sha256"] == build_module._sha256_hex(dist / "批图王.exe")
    assert payload["installer_sha256"] == build_module._sha256_hex(
        dist / "批图王-Setup.exe"
    )
