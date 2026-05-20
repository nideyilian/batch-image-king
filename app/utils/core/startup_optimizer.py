"""
启动优化器
优化程序启动流程，减少启动时间
"""

import time
import threading
import sys
import os
from typing import List, Callable, Dict, Any
from PySide6.QtCore import QTimer, QObject, Signal
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")



class StartupTask:
    """启动任务"""
    
    def __init__(self, name: str, func: Callable, priority: int = 0, 
                 can_defer: bool = False, timeout: float = 10.0):
        self.name = name
        self.func = func
        self.priority = priority  # 优先级，数字越小优先级越高
        self.can_defer = can_defer  # 是否可以延迟执行
        self.timeout = timeout
        self.completed = False
        self.error = None
        self.execution_time = 0
    
    def execute(self) -> bool:
        """执行任务"""
        start_time = time.time()
        try:
            self.func()
            self.completed = True
            return True
        except Exception as e:
            self.error = e
            safe_print(f"启动任务 '{self.name}' 执行失败: {e}")
            return False
        finally:
            self.execution_time = time.time() - start_time


class StartupOptimizer(QObject):
    """启动优化器"""
    
    progress_updated = Signal(str, int)  # 任务名称, 进度百分比
    task_completed = Signal(str, bool)   # 任务名称, 是否成功
    
    def __init__(self):
        super().__init__()
        self._tasks = []
        self._deferred_tasks = []
        self._completed_tasks = []
        self._failed_tasks = []
        self._start_time = None
        
    def add_task(self, name: str, func: Callable, priority: int = 0, 
                 can_defer: bool = False, timeout: float = 10.0):
        """添加启动任务"""
        task = StartupTask(name, func, priority, can_defer, timeout)
        self._tasks.append(task)
    
    def execute_startup(self, show_splash: bool = True, app: QApplication = None) -> Dict[str, Any]:
        """执行启动流程"""
        self._start_time = time.time()

        # 按优先级排序任务
        self._tasks.sort(key=lambda t: t.priority)

        # 分离立即执行和延迟执行的任务
        immediate_tasks = [t for t in self._tasks if not t.can_defer]
        self._deferred_tasks = [t for t in self._tasks if t.can_defer]

        splash = None
        if show_splash and app:  # 只有在有QApplication实例时才创建启动画面
            splash = self._create_splash_screen()

        # 执行立即任务
        total_tasks = len(immediate_tasks)
        for i, task in enumerate(immediate_tasks):
            if splash:
                self._update_splash(splash, task.name, int((i / total_tasks) * 100))

            self.progress_updated.emit(task.name, int((i / total_tasks) * 100))

            success = task.execute()
            self.task_completed.emit(task.name, success)

            if success:
                self._completed_tasks.append(task)
            else:
                self._failed_tasks.append(task)

        if splash:
            splash.finish(None)  # 关闭启动画面

        # 安排延迟任务
        self._schedule_deferred_tasks()

        startup_time = time.time() - self._start_time

        return {
            'startup_time': startup_time,
            'completed_tasks': len(self._completed_tasks),
            'failed_tasks': len(self._failed_tasks),
            'deferred_tasks': len(self._deferred_tasks),
            'total_tasks': len(self._tasks)
        }
    
    def _create_splash_screen(self) -> QSplashScreen:
        """创建启动画面"""
        # 创建一个简单的启动画面
        pixmap = QPixmap(400, 300)
        pixmap.fill(QColor(45, 45, 45))  # 深灰色背景
        
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))
        
        # 绘制标题
        title_font = QFont("Arial", 24, QFont.Bold)
        painter.setFont(title_font)
        painter.drawText(pixmap.rect(), 0x84, "批图王")  # 居中对齐
        
        # 绘制版本信息
        version_font = QFont("Arial", 12)
        painter.setFont(version_font)
        painter.drawText(20, pixmap.height() - 40, "版本 1.0.0")
        
        painter.end()
        
        splash = QSplashScreen(pixmap)
        splash.show()
        
        # 处理事件以确保启动画面显示
        QApplication.processEvents()
        
        return splash
    
    def _update_splash(self, splash: QSplashScreen, message: str, progress: int):
        """更新启动画面"""
        splash.showMessage(f"正在加载: {message} ({progress}%)", 
                          color=QColor(255, 255, 255))
        QApplication.processEvents()
    
    def _schedule_deferred_tasks(self):
        """安排延迟任务执行"""
        if not self._deferred_tasks:
            return
        
        def execute_deferred():
            for task in self._deferred_tasks:
                success = task.execute()
                self.task_completed.emit(task.name, success)
                
                if success:
                    self._completed_tasks.append(task)
                else:
                    self._failed_tasks.append(task)
        
        # 延迟2秒后执行
        QTimer.singleShot(2000, execute_deferred)
    
    def get_startup_report(self) -> str:
        """获取启动报告"""
        if not self._start_time:
            return "启动尚未开始"
        
        total_time = time.time() - self._start_time
        
        report = []
        report.append("=== 启动性能报告 ===")
        report.append(f"总启动时间: {total_time:.2f} 秒")
        report.append(f"完成任务: {len(self._completed_tasks)}")
        report.append(f"失败任务: {len(self._failed_tasks)}")
        report.append(f"延迟任务: {len(self._deferred_tasks)}")
        report.append("")
        
        if self._completed_tasks:
            report.append("已完成任务:")
            for task in self._completed_tasks:
                report.append(f"  ✓ {task.name}: {task.execution_time:.3f}s")
        
        if self._failed_tasks:
            report.append("\n失败任务:")
            for task in self._failed_tasks:
                report.append(f"  ✗ {task.name}: {task.error}")
        
        return "\n".join(report)


def create_optimized_startup() -> StartupOptimizer:
    """创建优化的启动流程"""
    optimizer = StartupOptimizer()
    
    # 添加启动任务（按优先级排序）
    
    # 优先级 0: 最关键的任务
    optimizer.add_task("初始化日志系统", lambda: None, priority=0)
    optimizer.add_task("检查关键依赖", lambda: None, priority=0)
    
    # 优先级 1: 重要但不阻塞的任务
    optimizer.add_task("设置PIL配置", lambda: setattr(__import__('PIL.Image', fromlist=['Image']), 'MAX_IMAGE_PIXELS', None), priority=1)
    optimizer.add_task("初始化主题", lambda: None, priority=1)
    
    # 优先级 2: 可以延迟的任务
    optimizer.add_task("完整依赖检查", lambda: None, priority=2, can_defer=True)
    optimizer.add_task("预加载预设", lambda: None, priority=2, can_defer=True)
    optimizer.add_task("初始化性能监控", lambda: None, priority=2, can_defer=True)
    optimizer.add_task("清理临时文件", lambda: None, priority=2, can_defer=True)
    
    return optimizer


def optimize_imports():
    """优化导入，减少启动时间"""
    # 预导入关键模块
    critical_modules = [
        'PySide6.QtCore',
        'PySide6.QtWidgets', 
        'PySide6.QtGui',
        'PIL.Image',
        'numpy'
    ]
    
    start_time = time.time()
    imported_count = 0
    
    for module_name in critical_modules:
        try:
            __import__(module_name)
            imported_count += 1
        except ImportError as e:
            safe_print(f"警告: 无法预导入 {module_name}: {e}")
    
    import_time = time.time() - start_time
    safe_print(f"预导入完成: {imported_count}/{len(critical_modules)} 模块, 耗时 {import_time:.3f}s")


def measure_startup_time(func: Callable) -> Callable:
    """测量启动时间的装饰器"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        startup_time = time.time() - start_time
        safe_print(f"启动完成，总耗时: {startup_time:.2f} 秒")
        return result
    return wrapper


# 全局启动优化器实例
_startup_optimizer = None

def get_startup_optimizer() -> StartupOptimizer:
    """获取全局启动优化器"""
    global _startup_optimizer
    if _startup_optimizer is None:
        _startup_optimizer = create_optimized_startup()
    return _startup_optimizer
