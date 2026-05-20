"""
UI响应性优化器
提供UI更新优化、事件处理优化和渲染性能提升
"""

import time
import threading
import builtins
from typing import Callable, Dict, Any, List
from PySide6.QtCore import QObject, QTimer, Signal, QThread, QMutex
from PySide6.QtWidgets import QApplication

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        builtins.print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            builtins.print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            builtins.print("[DEBUG] Message encoding failed")



class UIOptimizer(QObject):
    """UI响应性优化器"""
    
    def __init__(self):
        super().__init__()
        self._update_queue: List[Callable] = []
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._process_updates)
        self._update_timer.setSingleShot(True)
        self._mutex = QMutex()
        self._last_update_time = 0
        self._min_update_interval = 16  # 约60FPS
        
    def queue_update(self, update_func: Callable, delay_ms: int = 0):
        """队列化UI更新，避免频繁刷新"""
        current_time = time.time() * 1000
        
        self._mutex.lock()
        try:
            # 添加到更新队列
            if update_func not in self._update_queue:
                self._update_queue.append(update_func)
            
            # 如果距离上次更新时间足够长，立即处理
            if current_time - self._last_update_time > self._min_update_interval:
                if not self._update_timer.isActive():
                    self._update_timer.start(max(1, delay_ms))
            else:
                # 否则延迟处理
                if not self._update_timer.isActive():
                    remaining_time = self._min_update_interval - (current_time - self._last_update_time)
                    self._update_timer.start(max(1, int(remaining_time) + delay_ms))
        finally:
            self._mutex.unlock()
    
    def _process_updates(self):
        """处理队列中的更新"""
        self._mutex.lock()
        try:
            updates_to_process = self._update_queue.copy()
            self._update_queue.clear()
            self._last_update_time = time.time() * 1000
        finally:
            self._mutex.unlock()
        
        # 执行更新
        for update_func in updates_to_process:
            try:
                update_func()
            except Exception as e:
                safe_print(f"UI更新执行失败: {e}")
    
    def set_update_rate(self, fps: int):
        """设置UI更新频率"""
        self._min_update_interval = 1000 / max(1, min(120, fps))


class LazyLoader(QObject):
    """延迟加载器"""
    
    loaded = Signal(str, object)  # 加载完成信号
    
    def __init__(self):
        super().__init__()
        self._load_queue: Dict[str, Callable] = {}
        self._load_timer = QTimer()
        self._load_timer.timeout.connect(self._process_load_queue)
        self._load_timer.setSingleShot(True)
        self._loading_thread = None
        
    def queue_load(self, key: str, load_func: Callable, delay_ms: int = 100):
        """队列化延迟加载"""
        self._load_queue[key] = load_func
        
        if not self._load_timer.isActive():
            self._load_timer.start(delay_ms)
    
    def _process_load_queue(self):
        """处理加载队列"""
        if not self._load_queue:
            return
        
        # 在后台线程中加载
        if self._loading_thread is None or not self._loading_thread.isRunning():
            self._loading_thread = LoadingThread(self._load_queue.copy())
            self._loading_thread.item_loaded.connect(self.loaded.emit)
            self._loading_thread.start()
            self._load_queue.clear()


class LoadingThread(QThread):
    """后台加载线程"""
    
    item_loaded = Signal(str, object)
    
    def __init__(self, load_queue: Dict[str, Callable]):
        super().__init__()
        self.load_queue = load_queue
    
    def run(self):
        """执行加载任务"""
        for key, load_func in self.load_queue.items():
            try:
                result = load_func()
                self.item_loaded.emit(key, result)
            except Exception as e:
                safe_print(f"延迟加载失败 {key}: {e}")
                self.item_loaded.emit(key, None)


class PerformanceMonitor(QObject):
    """性能监控器"""
    
    performance_warning = Signal(str, float)  # 性能警告信号
    
    def __init__(self):
        super().__init__()
        self._frame_times: List[float] = []
        self._max_frame_history = 60
        self._warning_threshold = 100  # 100ms
        
    def record_frame_time(self, frame_time_ms: float):
        """记录帧时间"""
        self._frame_times.append(frame_time_ms)
        
        # 保持历史记录在限制范围内
        if len(self._frame_times) > self._max_frame_history:
            self._frame_times.pop(0)
        
        # 检查性能警告
        if frame_time_ms > self._warning_threshold:
            self.performance_warning.emit("frame_time", frame_time_ms)
    
    def get_average_frame_time(self) -> float:
        """获取平均帧时间"""
        if not self._frame_times:
            return 0.0
        return sum(self._frame_times) / len(self._frame_times)
    
    def get_fps(self) -> float:
        """获取FPS"""
        avg_frame_time = self.get_average_frame_time()
        if avg_frame_time <= 0:
            return 0.0
        return 1000.0 / avg_frame_time


class EventThrottler:
    """事件节流器"""
    
    def __init__(self, min_interval_ms: int = 100):
        self._min_interval = min_interval_ms
        self._last_call_time = 0
        self._pending_call = None
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._execute_pending)
    
    def throttle(self, func: Callable, *args, **kwargs):
        """节流执行函数"""
        current_time = time.time() * 1000
        
        if current_time - self._last_call_time >= self._min_interval:
            # 可以立即执行
            self._last_call_time = current_time
            func(*args, **kwargs)
        else:
            # 延迟执行
            self._pending_call = (func, args, kwargs)
            remaining_time = self._min_interval - (current_time - self._last_call_time)
            self._timer.start(int(remaining_time))
    
    def _execute_pending(self):
        """执行待处理的调用"""
        if self._pending_call:
            func, args, kwargs = self._pending_call
            self._pending_call = None
            self._last_call_time = time.time() * 1000
            func(*args, **kwargs)


class BatchUpdater:
    """批量更新器"""
    
    def __init__(self, batch_size: int = 10, delay_ms: int = 50):
        self._batch_size = batch_size
        self._delay_ms = delay_ms
        self._updates: List[Callable] = []
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._process_batch)
    
    def add_update(self, update_func: Callable):
        """添加更新到批次"""
        self._updates.append(update_func)
        
        if len(self._updates) >= self._batch_size:
            # 批次已满，立即处理
            self._process_batch()
        elif not self._timer.isActive():
            # 启动延迟处理
            self._timer.start(self._delay_ms)
    
    def _process_batch(self):
        """处理批次更新"""
        if self._timer.isActive():
            self._timer.stop()
        
        updates_to_process = self._updates.copy()
        self._updates.clear()
        
        # 执行所有更新
        for update_func in updates_to_process:
            try:
                update_func()
            except Exception as e:
                safe_print(f"批量更新执行失败: {e}")
    
    def flush(self):
        """立即处理所有待处理的更新"""
        if self._updates:
            self._process_batch()


# 全局实例
_ui_optimizer = None
_lazy_loader = None
_performance_monitor = None

def get_ui_optimizer() -> UIOptimizer:
    """获取UI优化器实例"""
    global _ui_optimizer
    if _ui_optimizer is None:
        _ui_optimizer = UIOptimizer()
    return _ui_optimizer

def get_lazy_loader() -> LazyLoader:
    """获取延迟加载器实例"""
    global _lazy_loader
    if _lazy_loader is None:
        _lazy_loader = LazyLoader()
    return _lazy_loader

def get_performance_monitor() -> PerformanceMonitor:
    """获取性能监控器实例"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor

def queue_ui_update(update_func: Callable, delay_ms: int = 0):
    """便捷的UI更新队列函数"""
    optimizer = get_ui_optimizer()
    optimizer.queue_update(update_func, delay_ms)

def throttle_event(func: Callable, interval_ms: int = 100):
    """便捷的事件节流装饰器"""
    throttler = EventThrottler(interval_ms)
    
    def wrapper(*args, **kwargs):
        throttler.throttle(func, *args, **kwargs)
    
    return wrapper
