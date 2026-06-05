import sys
import traceback
import logging
import os
import time
from typing import Optional

# 优先设置流重定向，防止任何后续导入触发 write 错误
from app.utils.stream_redirector import setup_streams
setup_streams()

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
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from app.main_window import MainWindow
from app.ui.dark_theme import CursorDarkTheme
from app.utils.image_quality import ImageQualityManager
from app.utils.logger import Logger
from PIL import Image

# 导入启动优化器
try:
    from app.utils.core.startup_optimizer import get_startup_optimizer, optimize_imports, measure_startup_time
    STARTUP_OPTIMIZER_AVAILABLE = True
except ImportError as e:
    print(f"[警告] 启动优化器导入失败: {e}")
    STARTUP_OPTIMIZER_AVAILABLE = False

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

    # 检查SciPy
    try:
        import scipy
        dependencies.append("科学计算")
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
    """设置固定的暗色主题，不跟随系统主题变化"""
    # 强制设置样式为Fusion，但使用自定义调色板覆盖
    app.setStyle('Fusion')
    
    # 禁用原生菜单栏，确保一致的样式
    app.setAttribute(Qt.AA_DontUseNativeMenuBar, True)
    
    # 应用固定的暗色主题（包含完整的调色板和样式表）
    CursorDarkTheme.apply_to_application(app)

def main() -> int:
    """程序主函数（优化版本）"""
    # 预优化导入
    if STARTUP_OPTIMIZER_AVAILABLE:
        optimize_imports()

    # 记录启动开始时间
    start_time = time.time()

    # 设置日志
    logger = setup_logging()
    logger.info("程序启动")
    try:
        from app.utils.crash_reporter import install_crash_reporter
        crash_log_path = install_crash_reporter(logger=logger)
        logger.info(f"Crash diagnostics enabled: {crash_log_path}")
    except Exception as crash_reporter_error:
        logger.warning(f"Crash diagnostics unavailable: {crash_reporter_error}")

    # 显示简洁的依赖检查信息
    show_dependency_status()

    # 设置全局异常处理
    sys.excepthook = handle_exception

    # 支持 multiprocessing
    import multiprocessing
    multiprocessing.freeze_support()
    
    try:
        if STARTUP_OPTIMIZER_AVAILABLE:
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

            # 执行优化启动（传入app实例）
            startup_stats = optimizer.execute_startup(show_splash=True, app=app)
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

        # 应用固定的暗色主题（不跟随系统主题）
        setup_fixed_theme(app)

        # 设置应用信息
        app.setApplicationName("批图王")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("批图王")

        # 创建并显示主窗口
        window = MainWindow()
        window.show()
        
        # 恢复程序退出策略（当最后一个窗口关闭时退出）
        app.setQuitOnLastWindowClosed(True)
        
        # 计算并打印实际启动时间
        startup_duration = time.time() - start_time
        logger.info(f"启动完成，UI已显示，总耗时: {startup_duration:.2f} 秒")
        print(f"启动完成，总耗时: {startup_duration:.2f} 秒")

        if os.environ.get('TEST_SHAPED_LAYER') == '1':
            from PySide6.QtCore import QTimer
            def run_shape_layer_tests():
                try:
                    from app.models.document import Document
                    from app.models.layer_properties import ShapeType
                    doc = Document(parent=window)
                    doc.create_new(800, 600)
                    window.create_new_tab(doc)
                    layer = doc.add_layer("异形图层测试", 100, 100, 200, 160)
                    layer.shape_type = ShapeType.RIGHT_TRAPEZOID
                    print("[测试] 已创建异形图层: 直角梯形")
                    layer.trapezoid_top_width = 140
                    layer.trapezoid_bottom_width = 200
                    layer.trapezoid_slope_side = "right"
                    active_tab = window.tab_widget.currentWidget()
                    if active_tab and hasattr(active_tab, 'canvas'):
                        active_tab.canvas.update()
                    print("[测试] 已编辑梯形参数: top=140, bottom=200, side=right")
                    for st in [ShapeType.CIRCLE, ShapeType.PENTAGON, ShapeType.HEXAGON, ShapeType.RECTANGLE]:
                        layer.shape_type = st
                        active_tab = window.tab_widget.currentWidget()
                        if active_tab and hasattr(active_tab, 'canvas'):
                            active_tab.canvas.update()
                        print(f"[测试] 切换形状: {st.value}")
                        if st in [ShapeType.PENTAGON, ShapeType.HEXAGON]:
                            layer.polygon_rotation = 15
                            layer.polygon_corner_radius = 4
                            active_tab = window.tab_widget.currentWidget()
                            if active_tab and hasattr(active_tab, 'canvas'):
                                active_tab.canvas.update()
                            print("[测试] 已编辑多边形参数: rotation=15, corner_radius=4")
                    layer.shape_type = ShapeType.CIRCLE
                    layer.rotation = 45  # 使用正确的属性名
                    layer.x += 50
                    layer.y += 30
                    layer.width += 40
                    layer.height += 20
                    active_tab = window.tab_widget.currentWidget()
                    if active_tab and hasattr(active_tab, 'canvas'):
                        active_tab.canvas.update()
                    print("[测试] 已应用变换: 旋转=45°, 位移=(50,30), 尺寸增加=(40,20)")
                    print("[测试] 异形图层功能测试完成")
                except Exception as e:
                    print(f"[测试] 异形图层测试发生错误: {e}")
            QTimer.singleShot(500, run_shape_layer_tests)

        # 延迟执行完整的系统检查（仅在非优化模式下）
        if not STARTUP_OPTIMIZER_AVAILABLE:
            from PySide6.QtCore import QTimer
            def delayed_full_check():
                logger.info("执行完整系统依赖检查...")
                check_system_dependencies_full()

            QTimer.singleShot(1000, delayed_full_check)
        
        # 运行应用
        exit_code = app.exec()
        
        # 🔧 关键修复：程序退出时优雅关闭所有线程池
        logger.info("程序退出，开始清理资源...")
        try:
            # 关闭智能线程池管理器
            from app.utils.intelligent_thread_pool_manager import shutdown_thread_pools
            shutdown_thread_pools(wait=True)
            logger.info("智能线程池管理器已关闭")
            
            # 关闭其他全局资源
            from app.utils.advanced_image_cache import shutdown_advanced_image_cache
            shutdown_advanced_image_cache()
            logger.info("高级图像缓存已关闭")
            
            from app.utils.advanced_task_queue import shutdown_task_queue
            shutdown_task_queue()
            logger.info("高级任务队列已关闭")
            
        except Exception as cleanup_error:
            logger.warning(f"资源清理时出现异常: {cleanup_error}")
        
        logger.info(f"程序正常退出，退出码: {exit_code}")
        return exit_code
        
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
        except:
            pass
        return 2
    except (OSError, PermissionError) as e:
        logger.error(f"程序初始化失败 - 系统权限或文件访问错误: {str(e)}", exc_info=True)
        return 3
    except Exception as e:
        logger.error(f"程序初始化失败 - 未知错误: {str(e)}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
