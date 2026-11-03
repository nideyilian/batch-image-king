#!/usr/bin/env python3
"""Standalone launcher for the next-generation Batch Image King QML UI."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
import threading

logger = logging.getLogger(__name__)

from app.qml.qml_debug_entries import (  # noqa: E402  (需在 logger 之后)
    apply_window_geometry,
    open_debug_overlays,
    panels_need_window_grab,
    prepare_initial_document,
    wants_initial_document,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动批图王 QML 工作台")
    parser.add_argument("--screenshot", type=Path, help="启动后将窗口保存为 PNG 并退出")
    # 默认 None = 「没指定就沿用上次窗口尺寸」（等价旧版 restore_window_state）。
    # 以前默认写死 1600/960，等于每次启动强制覆盖用户调过的窗口，窗口几何存了也白存。
    parser.add_argument("--width", type=int, default=None, help="窗口宽度（默认恢复上次尺寸）")
    parser.add_argument("--height", type=int, default=None, help="窗口高度（默认恢复上次尺寸）")
    parser.add_argument("--theme", choices=("light", "dark"), help="覆盖并保存界面主题")
    parser.add_argument("--open", dest="open_path", type=Path, help="启动后打开指定 .cmp 项目")
    parser.add_argument("--blank", action="store_true", help="启动为空白文档，不载入内置示例")
    parser.add_argument(
        "--open-presets",
        action="store_true",
        help="启动时直接进入预设工作台（作为首页）",
    )
    parser.add_argument("--demo", action="store_true", help="启动内置演示文档")
    parser.add_argument("--show-batch-export", action="store_true", help="启动后打开批量导出面板")
    parser.add_argument("--show-batch-advanced", action="store_true", help="展示批量导出高级策略")
    parser.add_argument("--show-batch-unique", action="store_true", help="展示单次用图的图层参数")
    parser.add_argument("--show-color-picker", action="store_true", help="启动后打开 QML 取色器")
    parser.add_argument("--show-multi-tab-export", action="store_true", help="展示多标签批量导出")
    parser.add_argument("--show-effects", action="store_true", help="启动后打开图层效果面板")
    parser.add_argument("--show-new-canvas", action="store_true", help="启动后打开新建画布弹窗")
    parser.add_argument("--show-resize-canvas", action="store_true", help="展示原生画布尺寸弹窗")
    parser.add_argument("--show-rename-document", action="store_true", help="展示原生标签页重命名弹窗")
    parser.add_argument("--show-text-layer-dialog", action="store_true", help="展示原生文字图层创建弹窗")
    parser.add_argument("--show-shaped-layer-dialog", action="store_true", help="展示原生异形图层创建弹窗")
    parser.add_argument("--show-close-confirm", action="store_true", help="启动后打开未保存文档关闭确认")
    parser.add_argument("--demo-effects", action="store_true", help="为选中图片图层应用演示效果")
    parser.add_argument("--select-layer", type=int, help="启动后选中指定图层索引")
    parser.add_argument(
        "--select-preset",
        type=int,
        default=None,
        help="兼容 --show-project-presets：启动后选中预设工作台中的第 N 张卡片（0 起）",
    )
    parser.add_argument("--duplicate-selected", action="store_true", help="启动后复制当前选中图层")
    parser.add_argument("--demo-tabs", action="store_true", help="启动后创建多个文档标签用于验收")
    parser.add_argument("--demo-shaped", action="store_true", help="启动后创建真实异形图层用于验收")
    parser.add_argument("--show-advanced-properties", action="store_true", help="展示内嵌高级图层属性")
    parser.add_argument("--cycle-inspector-tabs", action="store_true", help="切换更多参数后返回基本参数")
    parser.add_argument("--show-random-transform", action="store_true", help="展示图片图层随机变换配置")
    parser.add_argument("--show-text-typography", action="store_true", help="展示文字字体与核心排版配置")
    parser.add_argument("--show-text-appearance", action="store_true", help="展示文字填充、背景与局部颜色")
    parser.add_argument("--show-text-effects", action="store_true", help="展示文字阴影、发光与样式工具")
    parser.add_argument("--show-crop-tools", action="store_true", help="展示图片自由裁剪工具")
    parser.add_argument("--show-vector-path", action="store_true", help="展示矢量路径节点编辑")
    parser.add_argument("--show-multi-select", action="store_true", help="展示多图层选择与编排")
    parser.add_argument("--show-grouped-layers", action="store_true", help="展示图层组层级与属性")
    parser.add_argument("--show-guides", action="store_true", help="展示标尺与参考线")
    parser.add_argument("--show-canvas-presets", action="store_true", help="展示画布预设管理")
    parser.add_argument("--show-project-presets", action="store_true", help="展示项目预设管理")
    parser.add_argument("--show-data-relations", action="store_true", help="展示绑定组管理")
    parser.add_argument("--show-size-match", action="store_true", help="展示尺寸匹配管理")
    return parser.parse_args()


_LEGACY_QML_SETTINGS = ("BatchImageKing", "批图王 QML")

# 只搬 QML 工作台自己写的键。经典版的 docks/* / layer_properties_modules/*
# 留在原处不动 —— 两套界面的偏好互不兼容，混在一起只会互相覆盖。
_QML_SETTING_PREFIXES = (
    "uiAppearance/",
    "windowGeometry/",
    "sidebarLayout/",
    "newCanvas/",
)


def _migrate_legacy_qml_settings() -> None:
    """把旧 QML 配置目录搬到统一应用名下（一次性）。

    背景：QML 早期只是 `--qml` 实验入口，应用名带 "QML" 后缀，设置落在
    独立目录。2026-10-28 经典版下线、QML 成为唯一界面，应用名统一成
    「批图王」。不迁移的话，用户既有设置会"凭空消失"——实测主题直接
    从 dark 回落成 light，窗口尺寸和侧栏宽度也一起重置。

    只搬 QML 自己的键；经典版那批（docks/*）留在原处不混进来。
    旧目录不删，万一需要回退还能读到。
    """
    from PySide6.QtCore import QSettings

    legacy = QSettings(*_LEGACY_QML_SETTINGS)
    legacy_keys = legacy.allKeys()
    if not legacy_keys:
        return

    current = QSettings()
    # 用标记键判断"迁移做过没有"，而不是用「目标键是否已存在」——
    # 统一后的命名空间里本来就残留着旧经典版写过的同名键（实测
    # uiAppearance/themeMode 已存在且值为 light），按"存在即跳过"会导致
    # 用户的 QML 偏好（dark）永远搬不过来。
    if current.value("meta/migratedFromLegacyQml", False):
        return

    moved = 0
    for key in legacy_keys:
        if not key.startswith(_QML_SETTING_PREFIXES):
            continue
        current.setValue(key, legacy.value(key))
        moved += 1
    current.setValue("meta/migratedFromLegacyQml", True)
    current.sync()
    # 只搬一次：之后用户在统一命名空间里的改动不会被旧目录覆盖
    if moved:
        print(f"[qml] 已迁移 {moved} 项 QML 设置到统一应用名")


def _schedule_font_warmup(delay_ms: int = 1500) -> None:
    """首屏渲染完成后，在后台线程预热系统字体索引。

    首次调用 ``TextLayer.get_system_fonts()`` 要遍历字体目录、用 fontTools 解析
    TTF/TTC 头部，本机实测 935 个字体约 390ms。这次扫描原本发生在用户第一次
    打开文字属性面板时，整段卡在 GUI 线程上；预热后交互路径直接命中进程级缓存（0ms）。

    只使用 os.walk 与 fontTools，不触碰 QFontDatabase（它绑定了 GUI 线程亲和性），
    因此可以在非 GUI 线程执行。失败只影响「首次使用回退为同步扫描」，不影响功能。
    """

    def _spawn() -> None:
        def _run() -> None:
            try:
                from app.models.text_layer import TextLayer

                TextLayer().get_system_fonts()
            except Exception:
                logger.debug("字体预热失败，首次使用时会回退为同步扫描", exc_info=True)

        threading.Thread(target=_run, name="font-warmup", daemon=True).start()

    from PySide6.QtCore import QTimer

    # 走 QTimer 而不是直接起线程：确保预热排在首屏渲染与启动画面收尾之后，
    # 不和首帧抢 CPU。
    QTimer.singleShot(delay_ms, _spawn)


def _schedule_export_warmup() -> None:
    """应用空闲时预热「独立导出进程」的依赖导入。

    背景：用户点「开始导出」后要等约 1.2 秒子进程启动（纯 python 399ms +
    PySide6 389ms + 业务栈 388ms，2026-11-03 实测）。这段时间界面停在
    「准备导出」，没有进度变化。

    做法：后台起一个 `--warmup-export` 子进程，它只 import 那套依赖就退出
    （不常驻、不建 QApplication、不碰任何文档状态）。目的是让 OS 把相关
    .pyc / .pyd 读进文件缓存，后续真实导出进程的 import 明显更快。

    几个刻意的取舍：
    - **不常驻**：常驻 worker 会让 `_worker_renderers` 之类的实例级累积状态
      跨批次残留（已排查到该风险），换来的收益不值。
    - **延迟 8 秒**：躲开首屏渲染与字体预热，避免和启动抢 CPU / 磁盘。
    - **失败完全静默**：预热只是优化，失败时真实导出照常走原路径。
    - **默认关闭**：实测预热后子进程从 1191ms 只降到 ~1100ms（4 次中位 1098ms），
      因为瓶颈是 Python 模块初始化本身，不是磁盘读不到文件。
      收益 ~90ms 不值得在每次启动后都白起一个进程，故默认关。
      需要时 `BTPW_ENABLE_EXPORT_WARMUP=1` 打开（低配机械盘上可能收益更明显）。
    """
    if os.environ.get("BTPW_ENABLE_EXPORT_WARMUP", "0") != "1":
        return
    if os.environ.get("BTPW_DISABLE_EXPORT_WARMUP", "0") == "1":
        return

    try:
        delay_ms = int(os.environ.get("BTPW_EXPORT_WARMUP_DELAY_MS", "8000") or 8000)
    except (TypeError, ValueError):
        delay_ms = 8000

    def _spawn() -> None:
        def _run() -> None:
            try:
                import subprocess
                import sys
                from pathlib import Path

                if getattr(sys, "frozen", False):
                    cmd = [sys.executable, "--warmup-export"]
                    cwd = str(Path(sys.executable).parent)
                else:
                    repo_root = Path(__file__).resolve().parents[2]
                    cmd = [sys.executable, str(repo_root / "main.py"), "--warmup-export"]
                    cwd = str(repo_root)

                creationflags = 0
                if os.name == "nt":
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.run(
                    cmd,
                    cwd=cwd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                    timeout=60,
                    check=False,
                )
            except Exception:
                logger.debug("导出依赖预热失败，首次导出会走原有的冷启动路径", exc_info=True)

        threading.Thread(target=_run, name="export-warmup", daemon=True).start()

    from PySide6.QtCore import QTimer

    QTimer.singleShot(delay_ms, _spawn)


def main(app=None, on_ready=None) -> int:
    """启动 QML 工作台。

    `app` 参数用于复用调用方已创建的 QApplication —— 应用级基础设施
    （日志、崩溃会话、依赖检查、PIL 限制）全部在 `main.py` 的 bootstrap 里，
    那些步骤必须先于 QApplication 或紧随其后完成。若这里再新建一个
    QApplication，Qt 会直接抛「A QApplication instance already exists」。

    不传 `app` 时保持原有独立启动能力（测试与 `python -m app.qml.qml_main`
    仍可直接跑）。
    """
    args = parse_args()
    debug_enabled = os.environ.get("BTPW_QML_DEBUG") == "1"
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    def debug(message: str) -> None:
        if debug_enabled:
            output = f"[qml] {message}"
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            output = output.encode(encoding, errors="backslashreplace").decode(encoding)
            print(output, flush=True)

    def _emit(message: str, *, stderr: bool = False) -> None:
        """输出不因控制台编码而抛异常的文本。

        CI（英文 Windows runner）的控制台是 cp1252，直接 print 中文会抛
        UnicodeEncodeError。这种打印常出现在**错误处理路径**上（如截图保存失败），
        一旦它自己崩掉，真正的失败原因就被彻底吞掉，只看到一个莫名的 returncode。
        """
        stream = sys.stderr if stderr else sys.stdout
        encoding = getattr(stream, "encoding", None) or "utf-8"
        try:
            text = message.encode(encoding, errors="backslashreplace").decode(encoding)
        except (LookupError, UnicodeError):
            text = message.encode("ascii", errors="backslashreplace").decode("ascii")
        print(text, file=stream, flush=True)

    if args.screenshot:
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        os.environ.setdefault("QT_QPA_FONTDIR", str(windows_dir / "Fonts"))

    qml_dir = Path(__file__).resolve().parent
    repo_root = qml_dir.parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    debug("importing Qt modules")
    # Q_ARG / QMetaObject / QObject 已随调试入口迁到 qml_debug_entries，这里不再需要
    from PySide6.QtCore import QThreadPool, QTimer, QUrl
    from PySide6.QtGui import QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtWidgets import QApplication
    from app.qml.legacy_feature_bridge import LegacyFeatureBridge
    from app.qml.preview_image_provider import PreviewImageProvider
    from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
    from app.qml.viewmodels.binding_manager_view_model import BindingManagerViewModel
    from app.qml.viewmodels.canvas_preset_view_model import CanvasPresetViewModel
    from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
    from app.qml.viewmodels.multi_tab_export_view_model import MultiTabExportViewModel
    from app.qml.viewmodels.size_match_view_model import SizeMatchViewModel
    from app.qml.viewmodels.update_view_model import UpdateViewModel
    from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
    from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

    debug("creating QApplication")
    # 复用外部传入的实例；只有独立运行时才自建。
    # 应用名/组织名统一用与 bootstrap 相同的值：不同名字会让 QSettings
    # 落到不同目录，用户的窗口尺寸、主题选择会「看起来没保存」。
    if app is None:
        app = QApplication(sys.argv)
        app.setApplicationName("批图王")
        app.setOrganizationName("批图王")
        try:
            from app.version import APP_VERSION

            app.setApplicationVersion(str(APP_VERSION))
        except Exception:
            pass

    _migrate_legacy_qml_settings()

    def cleanup_runtime() -> None:
        QThreadPool.globalInstance().waitForDone(5000)
        try:
            from app.utils.intelligent_thread_pool_manager import shutdown_thread_pools

            shutdown_thread_pools(wait=True)
        except Exception as error:
            debug(f"thread pool cleanup failed: {error}")
        try:
            from app.utils.advanced_task_queue import shutdown_task_queue

            shutdown_task_queue()
        except Exception as error:
            debug(f"task queue cleanup failed: {error}")
        # 清理全局缓存（图片缓存 / 智能渲染缓存 / 预览渲染缓存）
        try:
            from app.utils.memory_manager import cleanup_memory

            cleanup_memory()
        except Exception as error:
            debug(f"memory cleanup failed: {error}")
        try:
            from app.utils.intelligent_render_cache import clear_global_cache

            clear_global_cache()
        except Exception as error:
            debug(f"intelligent render cache cleanup failed: {error}")
        try:
            from app.services.preview_render_service import clear_preview_render_cache

            clear_preview_render_cache()
        except Exception as error:
            debug(f"preview render cache cleanup failed: {error}")

    app.aboutToQuit.connect(cleanup_runtime)
    icon_path = repo_root / "app" / "resources" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    debug("creating QML engine")
    engine = QQmlApplicationEngine()
    if debug_enabled:
        engine.warnings.connect(lambda warnings: [debug(str(warning)) for warning in warnings])
    preview_provider = PreviewImageProvider()
    auto_render = os.environ.get("BTPW_QML_DISABLE_AUTO_RENDER") != "1"
    workspace = WorkspaceViewModel(
        preview_provider=preview_provider,
        # 文档尚未完成初始化时不启动默认空文档预览，避免首屏重复渲染。
        auto_render=False,
        defer_font_catalog_preload=True,
        parent=engine,
    )
    batch_export = BatchExportViewModel(workspace=workspace, parent=engine)
    canvas_presets = CanvasPresetViewModel(workspace=workspace, parent=engine)
    binding_manager = BindingManagerViewModel(workspace=workspace, parent=engine)
    size_match = SizeMatchViewModel(workspace=workspace, parent=engine)
    update_manager = UpdateViewModel(parent=engine)
    engine.addImageProvider("documentPreview", preview_provider)

    if wants_initial_document(args):
        prepare_initial_document(args, workspace, qml_dir)

    workspace_sessions = WorkspaceSessionViewModel(
        workspace=workspace,
        parent=engine,
        include_initial_document=wants_initial_document(args),
    )
    project_presets = PresetManagerViewModel(
        workspace=workspace,
        sessions=workspace_sessions,
        parent=engine,
    )
    multi_tab_export = MultiTabExportViewModel(
        workspace=workspace,
        sessions=workspace_sessions,
        parent=engine,
    )
    legacy_tools = LegacyFeatureBridge(
        workspace=workspace,
        sessions=workspace_sessions,
        preset_view_model=project_presets,
        parent=engine,
    )
    if args.demo_tabs:
        workspace_sessions.newDocument(1080, 1080)
        workspace_sessions.newDocument(1920, 1080)
        workspace_sessions.activateDocument(0)

    # 完成启动参数对应的文档/标签初始化后，只提交一次首屏预览。
    workspace.setAutoRender(auto_render)
    if auto_render:
        workspace.renderInitialPreview()

    engine.rootContext().setContextProperty("workspace", workspace)
    engine.rootContext().setContextProperty("workspaceSessions", workspace_sessions)
    engine.rootContext().setContextProperty("layerModel", workspace.layerModel)
    engine.rootContext().setContextProperty("batchExport", batch_export)
    engine.rootContext().setContextProperty("canvasPresets", canvas_presets)
    engine.rootContext().setContextProperty("projectPresets", project_presets)
    engine.rootContext().setContextProperty("bindingManager", binding_manager)
    engine.rootContext().setContextProperty("sizeMatch", size_match)
    engine.rootContext().setContextProperty("multiTabExport", multi_tab_export)
    engine.rootContext().setContextProperty("legacyTools", legacy_tools)
    engine.rootContext().setContextProperty("updateManager", update_manager)

    qml_path = qml_dir / "Main.qml"
    debug(f"loading {qml_path}")
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    debug("QML load returned")
    if not engine.rootObjects():
        print(f"QML 工作台加载失败：{qml_path}", file=sys.stderr)
        return 2

    # 字体目录扫描放到首屏空闲后，避免与 QML 组件创建争用 CPU/磁盘。
    try:
        font_preload_delay_ms = max(
            500,
            int(os.environ.get("BTPW_QML_FONT_PRELOAD_DELAY_MS", "2000")),
        )
    except (TypeError, ValueError):
        font_preload_delay_ms = 2000
    QTimer.singleShot(font_preload_delay_ms, workspace.enableDeferredFontCatalogPreload)

    window = engine.rootObjects()[0]
    debug(
        f"root window created: type={type(window).__name__}, "
        f"visible={window.property('visible')}"
    )
    # 首屏对象树已就绪：调用方（main.py 的 bootstrap）用这个时机收掉启动画面。
    # 不传则什么都不做，保持独立启动路径零行为变化。
    if on_ready is not None:
        try:
            on_ready(window)
        except Exception as ready_error:  # 启动画面失败不能挡住启动
            debug(f"on_ready failed: {ready_error}")
    # 字体索引预热：把首次 390ms 的字体扫描挪到空闲时段（截图模式跳过，避免扰动验收时序）
    if not args.screenshot:
        try:
            _schedule_font_warmup()
        except Exception:
            logger.debug("字体预热调度失败", exc_info=True)
        try:
            _schedule_export_warmup()
        except Exception:
            logger.debug("导出依赖预热调度失败", exc_info=True)
    # 截图/验收模式：固定用参数尺寸，且不读写窗口几何（否则验收图会被上次尺寸顶掉）
    apply_window_geometry(window, args, debug)
    open_debug_overlays(args, window, workspace, workspace_sessions, debug)

    if args.screenshot:
        output_path = args.screenshot.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            debug("capturing root window")
            try:
                # 这些面板是独立浮层，captureRoot 抓不到，必须整窗抓图
                if panels_need_window_grab(args):
                    image = window.grabWindow()
                    saved = not image.isNull() and image.save(str(output_path), "PNG")
                    if saved:
                        _emit(f"截图已保存：{output_path}")
                        app.exit(0)
                    else:
                        _emit(f"截图保存失败：{output_path}", stderr=True)
                        app.exit(3)
                    return
                # 工作台是 captureRoot 的兄弟节点（浮层），grabToImage 抓不到它。
                # 它可见时必须走整窗抓取，否则截图丢失整个工作台。
                if bool(window.property("presetWorkbenchVisible")):
                    image = window.grabWindow()
                    saved = not image.isNull() and image.save(str(output_path), "PNG")
                    if saved:
                        _emit(f"截图已保存：{output_path}")
                        app.exit(0)
                    else:
                        _emit(f"截图保存失败：{output_path}", stderr=True)
                        app.exit(3)
                    return

                capture_item = window.findChild(QQuickItem, "captureRoot")
                if capture_item is None:
                    raise RuntimeError("未找到 QML 截图根节点")
                grab_value = capture_item.grabToImage()
                grab_result = grab_value[0] if isinstance(grab_value, tuple) else grab_value
                window._qml_grab_result = grab_result

                def save_capture() -> None:
                    image = grab_result.image()
                    saved = not image.isNull() and image.save(str(output_path), "PNG")
                    if saved:
                        _emit(f"截图已保存：{output_path}")
                        app.exit(0)
                    else:
                        _emit(f"截图保存失败：{output_path}", stderr=True)
                        app.exit(3)

                grab_result.ready.connect(save_capture)
            except Exception as error:
                _emit(f"截图保存失败：{error}", stderr=True)
                app.exit(3)

        QTimer.singleShot(1800, capture)

    # 启动后延迟静默检查更新；发现新版本时由 QML 横幅提示
    QTimer.singleShot(4000, update_manager.checkForUpdatesSilent)

    exit_code = app.exec()
    debug(f"event loop exited with code {exit_code}")

    # 事件循环已退出，QML 对象随时可能被销毁。必须先把缩略图后台线程停掉并
    # 断开 VM 订阅，否则工作线程会在 VM 析构后回调，抛
    # "libshiboken: Internal C++ object (PresetManagerViewModel) already deleted"。
    try:
        project_presets.shutdown()
    except Exception as error:
        debug(f"preset view model shutdown failed: {error}")
    try:
        from app.utils.preset_thumbnail import shutdown_thumbnail_services

        shutdown_thumbnail_services()
    except Exception as error:
        debug(f"thumbnail services shutdown failed: {error}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
