"""
增强的性能监控系统
收集关键操作的性能指标，提供详细的性能分析
"""

import time
import threading
import functools
from typing import Dict, List, Any, Optional, Callable
from collections import defaultdict, deque
import statistics
import gc

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        safe_print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            safe_print(f"[DEBUG] {ascii_message}")
        except Exception:
            # 最后的备选方案
            safe_print("[DEBUG] Message encoding failed")



class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self, max_records: int = 1000):
        self._metrics = defaultdict(lambda: {
            'times': deque(maxlen=max_records),
            'count': 0,
            'total_time': 0,
            'min_time': float('inf'),
            'max_time': 0,
            'errors': 0
        })
        self._lock = threading.RLock()
        self._start_time = time.time()
        
    def record_execution(self, operation: str, execution_time: float, success: bool = True):
        """记录操作执行时间"""
        with self._lock:
            metric = self._metrics[operation]
            
            metric['times'].append(execution_time)
            metric['count'] += 1
            metric['total_time'] += execution_time
            metric['min_time'] = min(metric['min_time'], execution_time)
            metric['max_time'] = max(metric['max_time'], execution_time)
            
            if not success:
                metric['errors'] += 1
    
    def get_statistics(self, operation: str = None) -> Dict[str, Any]:
        """获取性能统计信息"""
        with self._lock:
            if operation:
                return self._get_operation_stats(operation)
            else:
                return self._get_all_stats()
    
    def _get_operation_stats(self, operation: str) -> Dict[str, Any]:
        """获取单个操作的统计信息"""
        if operation not in self._metrics:
            return {}
        
        metric = self._metrics[operation]
        times = list(metric['times'])
        
        if not times:
            return {'operation': operation, 'count': 0}
        
        return {
            'operation': operation,
            'count': metric['count'],
            'total_time': metric['total_time'],
            'average_time': metric['total_time'] / metric['count'],
            'min_time': metric['min_time'],
            'max_time': metric['max_time'],
            'median_time': statistics.median(times),
            'std_dev': statistics.stdev(times) if len(times) > 1 else 0,
            'error_rate': metric['errors'] / metric['count'] if metric['count'] > 0 else 0,
            'recent_times': times[-10:],  # 最近10次执行时间
        }
    
    def _get_all_stats(self) -> Dict[str, Any]:
        """获取所有操作的统计信息"""
        stats = {
            'uptime': time.time() - self._start_time,
            'operations': {}
        }
        
        for operation in self._metrics:
            stats['operations'][operation] = self._get_operation_stats(operation)
        
        return stats
    
    def get_slow_operations(self, threshold: float = 1.0) -> List[Dict[str, Any]]:
        """获取慢操作列表"""
        slow_ops = []
        
        with self._lock:
            for operation in self._metrics:
                stats = self._get_operation_stats(operation)
                if stats.get('average_time', 0) > threshold:
                    slow_ops.append(stats)
        
        # 按平均时间排序
        slow_ops.sort(key=lambda x: x.get('average_time', 0), reverse=True)
        return slow_ops
    
    def reset_metrics(self, operation: str = None):
        """重置性能指标"""
        with self._lock:
            if operation:
                if operation in self._metrics:
                    del self._metrics[operation]
            else:
                self._metrics.clear()
                self._start_time = time.time()


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self._metrics = PerformanceMetrics()
        self._enabled = True
        
    def monitor(self, operation_name: str = None):
        """性能监控装饰器"""
        def decorator(func: Callable) -> Callable:
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if not self._enabled:
                    return func(*args, **kwargs)
                
                start_time = time.time()
                success = True
                
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    raise
                finally:
                    execution_time = time.time() - start_time
                    self._metrics.record_execution(op_name, execution_time, success)
                    
                    # 如果执行时间超过阈值，打印警告
                    if execution_time > 2.0:  # 2秒阈值
                        safe_print(f"[性能警告] {op_name} 执行时间: {execution_time:.3f}s")
            
            return wrapper
        return decorator
    
    def time_operation(self, operation_name: str):
        """上下文管理器，用于测量代码块执行时间"""
        return OperationTimer(self._metrics, operation_name)
    
    def get_statistics(self, operation: str = None) -> Dict[str, Any]:
        """获取性能统计信息"""
        return self._metrics.get_statistics(operation)
    
    def get_slow_operations(self, threshold: float = 1.0) -> List[Dict[str, Any]]:
        """获取慢操作"""
        return self._metrics.get_slow_operations(threshold)
    
    def enable(self):
        """启用性能监控"""
        self._enabled = True
    
    def disable(self):
        """禁用性能监控"""
        self._enabled = False
    
    def reset(self, operation: str = None):
        """重置性能数据"""
        self._metrics.reset_metrics(operation)
    
    def generate_report(self) -> str:
        """生成性能报告"""
        stats = self.get_statistics()
        slow_ops = self.get_slow_operations(0.5)  # 0.5秒阈值
        
        report = []
        report.append("=== 性能监控报告 ===")
        report.append(f"运行时间: {stats['uptime']:.1f} 秒")
        report.append(f"监控操作数: {len(stats['operations'])}")
        report.append("")
        
        if slow_ops:
            report.append("慢操作 (>0.5秒):")
            for op in slow_ops[:10]:  # 显示前10个最慢的操作
                report.append(f"  {op['operation']}: 平均 {op['average_time']:.3f}s "
                            f"(执行 {op['count']} 次)")
        
        report.append("")
        report.append("所有操作统计:")
        for op_name, op_stats in stats['operations'].items():
            if op_stats['count'] > 0:
                report.append(f"  {op_name}: 平均 {op_stats['average_time']:.3f}s "
                            f"(执行 {op_stats['count']} 次, "
                            f"错误率 {op_stats['error_rate']:.1%})")
        
        return "\n".join(report)


class OperationTimer:
    """操作计时器上下文管理器"""
    
    def __init__(self, metrics: PerformanceMetrics, operation_name: str):
        self._metrics = metrics
        self._operation_name = operation_name
        self._start_time = None
    
    def __enter__(self):
        self._start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        execution_time = time.time() - self._start_time
        success = exc_type is None
        self._metrics.record_execution(self._operation_name, execution_time, success)


# 全局性能监控器实例
_performance_monitor = None

def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor

def monitor_performance(operation_name: str = None):
    """性能监控装饰器"""
    return get_performance_monitor().monitor(operation_name)

def time_operation(operation_name: str):
    """操作计时上下文管理器"""
    return get_performance_monitor().time_operation(operation_name)

def get_performance_stats(operation: str = None) -> Dict[str, Any]:
    """获取性能统计信息"""
    return get_performance_monitor().get_statistics(operation)

def generate_performance_report() -> str:
    """生成性能报告"""
    return get_performance_monitor().generate_report()

def reset_performance_data(operation: str = None):
    """重置性能数据"""
    get_performance_monitor().reset(operation)
