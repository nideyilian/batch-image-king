from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
import sys
import traceback
import logging
import os
import time
from typing import Optional

# 优先设置流重定向，防止任何后续导入触发 write 错误
from app.utils.stream_redirector import setup_streams
setup_streams()

if len(sys.argv) >= 2 and sys.argv[1] == "--export-worker":
    from app.workers.export_worker import main as export_worker_main
    sys.exit(export_worker_main(sys.argv[2:]))

if len(sys.argv) >= 2 and sys.argv[1] == "--apply-update":
    from app.utils.updater import apply_update, parse_apply_update_args
    new_exe, wait_pid, relaunch = parse_apply_update_args(sys.argv[1:])
    sys.exit(apply_update(new_exe, wait_pid=wait_pid, relaunch=relaunch))

from app.utils.crash_session import begin_crash_session, mark_clean_exit

def _safe_print(message):
    """安全打印，避免在GBK控制台因emoji导致启动中断"""
    try:
        print(message)
    except UnicodeEncodeError:
        try:
            fallback = str(message).encode('ascii', 'ignore').decode('ascii')
            print(fallback)
        except Exception:
            print("[startup-log-encoding-fallback]")

# 🔍🔍🔍 验证新版本代码已加载 - 时间戳: 2024-11-07-16:50 🔍🔍🔍
print("="*80)
_safe_print("🔍 [代码版本验证] 新版本已加载！时间戳：2024-11-07-16:50")
print("="*80)
# 仅保留异常处理和测试所需的 Qt 类型。经典 UI、图像质量引擎和 PIL 均在
# ``main()`` 的经典启动路径中延迟导入，避免默认 QML 启动时加载整套旧 UI。
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QTimer
from app.utils.logger import Logger

# 保留该名称作为兼容标记，但不在模块导入阶段加载启动优化器。
STARTUP_OPTIMIZER_AVAILABLE = None

def check_system_dependencies_fast() -> bool:
    """快速检查关键系统依赖"""
    checks_passed = True
    errors = []

    # 只检查最关键的依赖，其他的延迟检查
    try:
        import PIL
        print(f"[OK] PIL/Pillow 版本: {PIL.__version__}")
    except ImportError:
        errors.append("PIL/Pillow 未安装，图像处理功能将无法使用")
        checks_passed = False

    try:
        import numpy as np
        print(f"[OK] NumPy 版本: {np.__version__}")
    except ImportError:
        errors.append("NumPy 未安装，图层混合模式功能将无法使用")
        checks_passed = False

    if not checks_passed:
        error_msg = "\n".join(errors)
        print(f"关键依赖检查失败:\n{error_msg}")

    return checks_passed

def check_system_dependencies_full() -> bool:
    """完整的系统依赖检查（延迟执行）"""
    try:
        from PIL import Image
        from app.utils.image_quality import ImageQualityManager
        # 检查混合模式模块是否可以导入
        from app.models.document_blend import BlendMode, Blender

        # 创建两个测试图像
        img1 = Image.new('RGBA', (100, 100), (255, 0, 0, 128))  # 半透明红色
        img2 = Image.new('RGBA', (100, 100), (0, 0, 255, 128))  # 半透明蓝色

        # 尝试应用一个混合模式
        result = Blender.apply_blend_mode(img1, img2, BlendMode.NORMAL)

        if result:
            print("[OK] 混合模式功能测试通过")
            
            # 测试新的图像质量管理功能
            print("[INFO] 测试图像质量管理功能...")
            test_text_detection = ImageQualityManager.detect_text_content(result)
            print(f"[OK] 文字检测功能: {'检测到文字' if test_text_detection else '未检测到文字'}")
            
            quality_settings = ImageQualityManager.get_recommended_quality_settings()
            print(f"[OK] 推荐质量设置: JPEG={quality_settings['jpeg_high_quality']}, PNG压缩={quality_settings['png_compress_level']}")
            
            return True
        else:
            print("[WARNING] 混合模式功能测试失败")
            return False
    except (ImportError, AttributeError, TypeError) as e:
        print(f"[WARNING] 混合模式功能测试时出错: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 混合模式功能测试时发生未预期错误: {e}")
        return False

def setup_logging() -> logging.Logger:
    """设置日志系统（使用统一的Logger类）"""
    # 创建日志目录
    log_dir = os.path.join(os.path.expanduser('~'), '.config', '批图王', 'logs')

    # 使用统一的Logger类初始化
    Logger.init(
        log_dir=log_dir,
        log_level=logging.INFO,
        console_output=True,
        logger_name='批图王'
    )

    return Logger.get_logger()


def logger_file_path(logger: logging.Logger) -> str:
    for handler in getattr(logger, "handlers", []):
        if isinstance(handler, logging.FileHandler):
            return str(getattr(handler, "baseFilename", "") or "")
    return ""


def show_previous_crash_notice(parent, notice) -> None:
    """显示上次异常退出的提示。

    `parent` 可能是 QQuickWindow（QML 工作台）或 QWidget（旧经典版），
    但 QMessageBox 只接受 QWidget 父窗口。直接传 QQuickWindow 会抛
    TypeError → 崩溃恢复提示**永远弹不出来**，用户只会在日志里看到一条
    「未捕获的异常」，等于崩溃恢复对用户隐形。
    这里统一降级为无父窗口的独立对话框：提示仍然显示，模态行为一致。
    """
    from PySide6.QtWidgets import QWidget

    widget_parent = parent if isinstance(parent, QWidget) else None
    dialog = QMessageBox(widget_parent)
    dialog.setIcon(QMessageBox.Warning)
    dialog.setWindowTitle("检测到上次异常退出")
    dialog.setText(str(notice.message))
    dialog.setDetailedText(str(notice.details))
    dialog.addButton("知道了", QMessageBox.AcceptRole)
    dialog.exec()


def finish_crash_session(session_id: str, exit_code: int, logger: logging.Logger) -> int:
    if session_id:
        try:
            mark_clean_exit(session_id)
        except Exception as exc:
            try:
                logger.warning(f"无法记录程序正常退出状态: {exc}")
            except Exception:
                pass
    return int(exit_code)


def show_dependency_status():
    """显示简洁的依赖状态信息"""
    dependencies = []

    # 检查psutil
    try:
        import psutil
        dependencies.append("性能监控")
    except ImportError:
        pass

    # 检查OpenCV
    try:
        import cv2
        dependencies.append("高级图像处理")
    except ImportError:
        pass

    if dependencies:
        print(f"[OK] 可选功能已启用: {', '.join(dependencies)}")
    else:
        print("[INFO] 使用基础功能模式（可选依赖未安装）")

def handle_exception(exc_type: type, exc_value: BaseException, exc_traceback: Optional[object]) -> None:
    """全局异常处理函数"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 对于键盘中断，使用默认处理
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
        
    logger = logging.getLogger('批图王')
    logger.error("未捕获的异常", exc_info=(exc_type, exc_value, exc_traceback))
    
    # 显示错误对话框
    error_msg = str(exc_value)
    tb_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    try:
        app = QApplication.instance()
        if app:
            error_dialog = QMessageBox()
            error_dialog.setIcon(QMessageBox.Critical)
            error_dialog.setWindowTitle("程序错误")
            error_dialog.setText("程序发生未处理的错误:")
            error_dialog.setInformativeText(error_msg)
            error_dialog.setDetailedText(tb_msg)
            error_dialog.addButton("确定", QMessageBox.AcceptRole)
            error_dialog.exec()
    except (RuntimeError, OSError) as e:
        # 如果显示错误对话框时出错，至少在控制台打印错误
        print(f"严重错误 - 无法显示错误对话框: {e}")
        print(f"原始错误: {error_msg}")
        print(tb_msg)

def setup_fixed_theme(app: QApplication) -> None:
    """设置固定主题（不跟随系统）。

    名字带「经典」，但 QML 版**仍然需要**：QML 里嵌了一批 QWidget 弹窗
    （颜色选择器、新建画布、批量导出等），它们靠这套 palette / QSS 上色。
    实测跳过之后颜色选择器标题栏变成纯白（255,255,255），与 QML 暗色界面
    割裂。QSS 只作用于 QWidget，不影响 QML 主界面。
    """
    from app.ui.dark_theme import CursorDarkTheme

    # 强制 Fusion，再用自定义调色板覆盖
    app.setStyle("Fusion")
    # 禁用原生菜单栏，确保一致的样式
    app.setAttribute(Qt.AA_DontUseNativeMenuBar, True)
    CursorDarkTheme.apply_to_application(app)


def main() -> int:
    """程序入口：应用级基础设施 + QML 工作台。

    2026-10-28 经典 Qt Widgets 界面下线，这里不再创建 MainWindow。
    但日志、崩溃会话、依赖检查、PIL 大图限制、退出清理**必须留在这里** ——
    它们与用哪套 UI 无关。上一轮把默认入口直接指向 qml_main 时，
    这整块基础设施被绕过了（没有日志、没有崩溃报告），属于隐藏退化。
    """
    from PIL import Image

    # 启动优化器自身依赖 Qt，但不应拖慢默认 QML 入口的模块导入。
    startup_optimizer_available = False
    try:
        from app.utils.core.startup_optimizer import get_startup_optimizer
        startup_optimizer_available = True
    except ImportError as e:
        print(f"[警告] 启动优化器导入失败: {e}")

    # 记录启动开始时间
    start_time = time.time()

    crash_session_id = ""
    previous_crash_notice = None

    # 设置日志
    logger = setup_logging()
    logger.info("程序启动")
    crash_log_path = ""
    try:
        from app.utils.crash_reporter import install_crash_reporter
        crash_log_path = install_crash_reporter(logger=logger)
        logger.info(f"Crash diagnostics enabled: {crash_log_path}")
    except Exception as crash_reporter_error:
        logger.warning(f"Crash diagnostics unavailable: {crash_reporter_error}")
    try:
        crash_session_id, previous_crash_notice = begin_crash_session(
            crash_log_path=crash_log_path,
            app_log_path=logger_file_path(logger),
        )
    except Exception as crash_session_error:
        logger.warning(f"Crash session unavailable: {crash_session_error}")

    # 显示简洁的依赖检查信息
    show_dependency_status()

    # 设置全局异常处理
    sys.excepthook = handle_exception

    # 支持 multiprocessing
    import multiprocessing
    multiprocessing.freeze_support()
    
    try:
        if startup_optimizer_available:
            # 使用启动优化器
            optimizer = get_startup_optimizer()

            # 先创建应用（启动画面需要）
            app = QApplication(sys.argv)
            
            # 防止启动画面关闭导致程序退出
            app.setQuitOnLastWindowClosed(False)

            # 添加具体的启动任务

            # 添加具体的启动任务
            optimizer.add_task("快速依赖检查",
                             lambda: check_system_dependencies_fast(),
                             priority=0)
            optimizer.add_task("PIL配置",
                             lambda: setattr(Image, 'MAX_IMAGE_PIXELS', None),
                             priority=1)
            optimizer.add_task("完整依赖检查",
                             lambda: check_system_dependencies_full(),
                             priority=2, can_defer=True)

            # 执行优化启动。
            #
            # show_splash=False：旧 StartupOptimizer 自带的启动画面会被
            # execute_startup() 在返回前就 finish() 掉 —— 也就是主窗口构造
            # （真正耗时 3.5~5 秒的那段）开始之前它就消失了，等于没显示。
            # 启动画面统一由下方 SplashScreen 负责，避免两个画面互相抢。
            startup_stats = optimizer.execute_startup(show_splash=False, app=app)
            logger.info(f"启动优化完成: {startup_stats}")
        else:
            # 回退到原有启动流程
            logger.info("开始执行系统依赖检查...")
            check_result = check_system_dependencies_fast()
            if not check_result:
                check_result = check_system_dependencies_full()
                if not check_result:
                    logger.warning("系统依赖检查发现问题，部分功能可能不可用")

            # 确保PIL可以处理大图像
            Image.MAX_IMAGE_PIXELS = None

            # 创建应用
            app = QApplication(sys.argv)

        # 应用固定主题。
        #
        # 名字带「经典」，但**不能省**：QML 里嵌了一批 QWidget 弹窗
        # （颜色选择器、新建画布对话框等），它们靠这套 palette/QSS 上色。
        # 跳过之后实测颜色选择器标题栏变成纯白（255,255,255），
        # 与 QML 暗色界面割裂。QSS 只作用于 QWidget，不影响 QML 主界面。
        setup_fixed_theme(app)

        # 设置应用信息
        app.setApplicationName("批图王")
        try:
            from app.version import APP_VERSION

            app_version = str(APP_VERSION)
        except Exception:
            app_version = "1.0.0"
        app.setApplicationVersion(app_version)
        app.setOrganizationName("批图王")

        # 启动画面：QML 加载期间同样有可感知的等待，保留。
        splash = None
        try:
            from app.splash_screen import SplashScreen

            splash = SplashScreen()
            splash.begin()
            splash.advance(0.06, "正在加载界面…")
        except Exception as splash_error:
            # 启动画面是锦上添花，失败绝不能挡住启动
            splash = None
            logger.warning(f"启动画面不可用，继续正常启动: {splash_error}")

        def _finish_splash(qml_window) -> None:
            """首屏对象树就绪后收掉启动画面。"""
            if splash is not None:
                splash.advance(1.0, "准备就绪")
                splash.finish_with(qml_window)

            if previous_crash_notice is not None:
                QTimer.singleShot(
                    300,
                    lambda notice=previous_crash_notice: show_previous_crash_notice(
                        qml_window, notice
                    ),
                )

            # 完整依赖检查必须挂在**事件循环内**的定时器上。
            # 原来它写在 app.exec() 之后 —— 那时循环已经结束，定时器永不触发，
            # 等于这段检查从来没跑过（只是看起来有）。
            if not startup_optimizer_available:

                def delayed_full_check() -> None:
                    logger.info("执行完整系统依赖检查...")
                    check_system_dependencies_full()

                QTimer.singleShot(1000, delayed_full_check)

        # QML 工作台接管窗口创建与事件循环，复用上面已建好的 QApplication
        from app.qml.qml_main import main as qml_main

        exit_code = qml_main(app=app, on_ready=_finish_splash)

        # 恢复程序退出策略（当最后一个窗口关闭时退出）
        app.setQuitOnLastWindowClosed(True)

        # 计算并打印实际启动时间
        startup_duration = time.time() - start_time
        logger.info(f"启动完成，总耗时: {startup_duration:.2f} 秒")
        print(f"启动完成，总耗时: {startup_duration:.2f} 秒")

        # 延迟执行完整的系统检查（仅在非优化模式下）
        # 事件循环已经由 qml_main 跑完并返回，这里**不能**再 exec 一次
        # （第二次 exec 会让进程永远不退出：实测 --screenshot 截图完成后
        # 进程挂住，靠 timeout 才被杀掉）。

        # 🔧 关键修复：程序退出时优雅关闭所有线程池
        logger.info("程序退出，开始清理资源...")
        try:
            # 关闭智能线程池管理器
            from app.utils.intelligent_thread_pool_manager import shutdown_thread_pools
            shutdown_thread_pools(wait=True)
            logger.info("智能线程池管理器已关闭")
            
            # 关闭其他全局资源
            from app.utils.advanced_task_queue import shutdown_task_queue
            shutdown_task_queue()
            logger.info("高级任务队列已关闭")
            
            # 清理全局缓存（图片缓存 / 智能渲染缓存 / 预览渲染缓存）
            try:
                from app.utils.memory_manager import cleanup_memory
                cleanup_memory()
                logger.info("图片缓存已清理")
            except Exception as cache_error:
                logger.warning(f"图片缓存清理异常: {cache_error}")
            try:
                from app.utils.intelligent_render_cache import clear_global_cache
                clear_global_cache()
                logger.info("智能渲染缓存已清理")
            except Exception as cache_error:
                logger.warning(f"智能渲染缓存清理异常: {cache_error}")
            try:
                from app.services.preview_render_service import clear_preview_render_cache
                clear_preview_render_cache()
                logger.info("预览渲染缓存已清理")
            except Exception as cache_error:
                logger.warning(f"预览渲染缓存清理异常: {cache_error}")
            
        except Exception as cleanup_error:
            logger.warning(f"资源清理时出现异常: {cleanup_error}")
        
        logger.info(f"程序正常退出，退出码: {exit_code}")
        return finish_crash_session(crash_session_id, exit_code, logger)
        
    except (ImportError, ModuleNotFoundError) as e:
        logger.error(f"程序初始化失败 - 缺少必要模块: {str(e)}", exc_info=True)
        # 显示缺少依赖的错误对话框
        try:
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("启动失败")
            msg.setText("程序缺少必要的依赖模块")
            msg.setDetailedText(f"错误信息: {str(e)}\n\n请确保已安装所有依赖包:\npip install -r requirements.txt")
            msg.exec()
        except Exception:
            pass
        return finish_crash_session(crash_session_id, 2, logger)
    except (OSError, PermissionError) as e:
        logger.error(f"程序初始化失败 - 系统权限或文件访问错误: {str(e)}", exc_info=True)
        return finish_crash_session(crash_session_id, 3, logger)
    except Exception as e:
        logger.error(f"程序初始化失败 - 未知错误: {str(e)}", exc_info=True)
        return finish_crash_session(crash_session_id, 1, logger)

if __name__ == "__main__":
    # 唯一界面：QML 工作台。
    #
    # 2026-10-28 决定下线经典 Qt Widgets 界面。理由不是"新的一定更好"，
    # 而是旧界面的属性面板在架构上允许每个面板文件自己造标签/定列宽
    # （同一块面板里标签列宽实测出现 58/84/640 三种，右边缘落在 70/84/96），
    # 靠契约测试兜底属于次优解；QML 用统一布局组件，列宽由布局系统管。
    #
    # --classic 不再提供界面，但保留参数识别：老快捷方式/脚本传进来时
    # 给一行明确提示，而不是静默行为不符或直接崩。
    if "--classic" in sys.argv:
        sys.argv.remove("--classic")
        _safe_print("提示：经典界面已下线，将以 QML 工作台启动。")

    # --qml 保留为兼容开关（与默认行为一致）
    if "--qml" in sys.argv:
        sys.argv.remove("--qml")

    sys.exit(main())
