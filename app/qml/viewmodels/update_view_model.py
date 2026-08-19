"""更新检测/下载 ViewModel，桥接 app.utils.updater 到 QML。

向 QML 暴露：
- 属性：checking / downloading / readyToInstall / updateAvailable / currentVersion /
         latestVersion / releaseNotes / required / errorMessage / downloadProgress /
         progressText
- 槽：checkForUpdates() / checkForUpdatesSilent() / downloadAndInstall() /
      installDownloadedUpdate() / openReleasePage()
- 信号：stateChanged() / progressChanged() / updateFinished(bool, str) /
        autoUpdateDetected(str) / restartRequested()
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from app.utils import updater
from app.utils.updater import UpdateInfo


class _UpdateTaskSignals(QObject):
    checked = Signal(object, str)
    downloaded = Signal(bool, str)
    failed = Signal(str)


class _UpdateCheckTask(QRunnable):
    def __init__(self, silent: bool) -> None:
        super().__init__()
        self.silent = silent
        self.signals = _UpdateTaskSignals()

    def run(self) -> None:
        try:
            info = updater.check_for_update()
            self.signals.checked.emit(info, "")
        except Exception as error:
            self.signals.checked.emit(None, str(error))


class _UpdateDownloadTask(QRunnable):
    def __init__(
        self,
        urls,
        dest: Path,
        progress_cb,
        sha256: str = "",
    ) -> None:
        super().__init__()
        self.urls = urls
        self.dest = dest
        self.progress_cb = progress_cb
        self.sha256 = sha256
        self.signals = _UpdateTaskSignals()

    def run(self) -> None:
        try:
            updater.download_update(
                self.urls,
                self.dest,
                self.progress_cb,
                sha256=self.sha256,
            )
            self.signals.downloaded.emit(True, "")
        except Exception as error:
            try:
                if self.dest.exists():
                    self.dest.unlink()
            except OSError:
                pass
            self.signals.failed.emit(str(error))


class UpdateViewModel(QObject):
    stateChanged = Signal()
    progressChanged = Signal()
    updateFinished = Signal(bool, str)
    autoUpdateDetected = Signal(str)
    restartRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checking = False
        self._downloading = False
        self._ready_to_install = False
        self._update_available = False
        self._current_version = updater.get_current_version()
        self._latest_version = ""
        self._release_notes = ""
        self._required = False
        self._error_message = ""
        self._download_progress = 0
        self._progress_text = ""
        self._info: Optional[UpdateInfo] = None
        self._pending_silent_found = False
        self._lock = threading.RLock()
        self._active_task = None

    @Property(str, notify=stateChanged)
    def currentVersion(self) -> str:
        return self._current_version

    @Property(str, notify=stateChanged)
    def latestVersion(self) -> str:
        return self._latest_version

    @Property(str, notify=stateChanged)
    def releaseNotes(self) -> str:
        return self._release_notes

    @Property(bool, notify=stateChanged)
    def required(self) -> bool:
        return self._required

    @Property(bool, notify=stateChanged)
    def checking(self) -> bool:
        return self._checking

    @Property(bool, notify=stateChanged)
    def downloading(self) -> bool:
        return self._downloading

    @Property(bool, notify=stateChanged)
    def readyToInstall(self) -> bool:
        return self._ready_to_install

    @Property(bool, notify=stateChanged)
    def updateAvailable(self) -> bool:
        return self._update_available

    @Property(str, notify=stateChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @Property(int, notify=progressChanged)
    def downloadProgress(self) -> int:
        return self._download_progress

    @Property(str, notify=progressChanged)
    def progressText(self) -> str:
        return self._progress_text

    @Slot()
    def checkForUpdates(self) -> None:
        self._start_check(silent=False)

    @Slot()
    def checkForUpdatesSilent(self) -> None:
        self._start_check(silent=True)

    def _start_check(self, silent: bool) -> None:
        with self._lock:
            if self._checking or self._downloading or self._ready_to_install:
                return
            self._checking = True
            self._error_message = ""
            self.stateChanged.emit()
        task = _UpdateCheckTask(silent=silent)
        task.signals.checked.connect(self._on_checked)
        self._active_task = task
        QThreadPool.globalInstance().start(task)

    @Slot(object, str)
    def _on_checked(self, info, error: str) -> None:
        self._active_task = None
        self._checking = False
        if error or info is None:
            self._update_available = False
            self._error_message = str(error or "未发现新版本")
            if not error:
                self._error_message = "当前已是最新版本"
            self.stateChanged.emit()
            return
        self._info = info
        self._update_available = True
        self._latest_version = info.version
        self._release_notes = info.release_notes
        self._required = bool(info.required)
        self._error_message = ""
        self.stateChanged.emit()
        self.autoUpdateDetected.emit(info.version)

    @Slot()
    def downloadAndInstall(self) -> None:
        if self._downloading or self._info is None or not self._info.download_url:
            return
        self._downloading = True
        self._ready_to_install = False
        self._error_message = ""
        self._download_progress = 0
        self._progress_text = "准备下载…"
        self.stateChanged.emit()
        self.progressChanged.emit()
        dest = updater.new_exe_path()
        urls = updater.expand_download_urls(self._info.download_url)
        task = _UpdateDownloadTask(
            urls,
            dest,
            self._on_download_progress,
            sha256=self._info.sha256,
        )
        task.signals.downloaded.connect(self._on_download_done)
        task.signals.failed.connect(self._on_download_failed)
        self._active_task = task
        QThreadPool.globalInstance().start(task)

    def _on_download_progress(self, received: int, total: int) -> None:
        if total > 0:
            percent = int(received * 100 / total)
            text = f"已下载 {percent}%"
        else:
            percent = 0
            text = f"已下载 {received / 1024 / 1024:.1f} MB"
        self._download_progress = percent
        self._progress_text = text
        self.progressChanged.emit()

    @Slot(bool, str)
    def _on_download_done(self, ok: bool, message: str) -> None:
        self._active_task = None
        self._downloading = False
        if ok:
            self._ready_to_install = True
            self._download_progress = 100
            self._progress_text = "下载完成，等待安装"
            self._error_message = ""
            self.stateChanged.emit()
            self.progressChanged.emit()
            self.updateFinished.emit(True, "新版已下载，请点击“立即安装并重启”完成更新")
        else:
            self._ready_to_install = False
            self.stateChanged.emit()
            self.progressChanged.emit()
            self.updateFinished.emit(False, message or "下载失败")

    @Slot(str)
    def _on_download_failed(self, message: str) -> None:
        self._active_task = None
        self._downloading = False
        self._ready_to_install = False
        self._error_message = message
        self.stateChanged.emit()
        hint = "自动下载失败，可点击“打开下载页”手动下载最新版。"
        self.updateFinished.emit(False, f"{message}\n{hint}" if message else hint)

    @Slot(result=bool)
    def installDownloadedUpdate(self) -> bool:
        if not self._ready_to_install:
            self._error_message = "尚未下载可安装的新版"
            self.stateChanged.emit()
            self.updateFinished.emit(False, self._error_message)
            return False
        return self._launch_apply_update()

    def _launch_apply_update(self) -> bool:
        try:
            spawned = updater.spawn_apply_update(
                wait_pid=os.getpid(),
                new_exe=updater.new_exe_path(),
            )
        except Exception:
            spawned = False
        if spawned:
            self._ready_to_install = False
            self.stateChanged.emit()
            self.restartRequested.emit()
            return True
        self._error_message = (
            "无法启动自动安装程序。新版已保留在程序目录，请重试或手动运行批图王_new.exe。"
        )
        self.stateChanged.emit()
        self.updateFinished.emit(False, self._error_message)
        return False

    @Slot(result=bool)
    def openReleasePage(self) -> bool:
        if self._info is None:
            return False
        url = QUrl.fromUserInput(self._info.installer_url or self._info.download_url)
        if url.isEmpty():
            return False
        return QDesktopServices.openUrl(url)
