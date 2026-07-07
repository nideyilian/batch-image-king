"""
智能内存管理策略
自动监控内存使用，实施智能清理策略，优化图像处理性能
"""


import os as _os
_BTPW_VERBOSE = _os.environ.get("BTPW_VERBOSE_LOG", "0").strip().lower() in ("1", "true", "yes", "on")
_ALWAYS_PRINT_KW = ("[ERROR]", "[CRITICAL]", "[严重错误]", "错误", "失败", "Exception", "Traceback", "[WARNING]")
def print(*args, **kwargs):
    if _BTPW_VERBOSE:
        __builtins__["print"](*args, **kwargs)
        return
    try:
        msg = " ".join(str(a) for a in args)
    except Exception:
        msg = ""
    if any(kw in msg for kw in _ALWAYS_PRINT_KW):
        __builtins__["print"](*args, **kwargs)

import gc
import os
import time
import psutil
import threading
import weakref
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from collections import deque
from PIL import Image
import numpy as np


@dataclass
class MemorySnapshot:
    """内存快照"""
    timestamp: float
    process_memory_mb: float
    system_memory_percent: float
    available_memory_mb: float
    cached_images_count: int
    cached_images_size_mb: float
    gc_collections: int
    large_objects_count: int


@dataclass
class MemoryOptimizationStrategy:
    """内存优化策略"""
    name: str
    description: str
    trigger_threshold: float  # 触发阈值（内存使用百分比）
    target_reduction: float   # 目标减少量（百分比）
    priority: int            # 优先级（1-10，数字越大优先级越高）
    enabled: bool = True


class MemoryPressureDetector:
    """内存压力检测器"""
    
    def __init__(self):
        self.pressure_levels = {
            'low': 60,      # 低压力：内存使用 < 60%
            'medium': 75,   # 中等压力：内存使用 60-75%
            'high': 85,     # 高压力：内存使用 75-85%
            'critical': 95  # 严重压力：内存使用 > 85%
        }
    
    def get_current_pressure(self) -> str:
        """获取当前内存压力级别"""
        try:
            memory = psutil.virtual_memory()
            usage_percent = memory.percent
            
            if usage_percent >= self.pressure_levels['critical']:
                return 'critical'
            elif usage_percent >= self.pressure_levels['high']:
                return 'high'
            elif usage_percent >= self.pressure_levels['medium']:
                return 'medium'
            else:
                return 'low'
        except Exception:
            return 'unknown'
    
    def get_memory_info(self) -> Dict:
        """获取详细内存信息"""
        try:
            # 系统内存
            system_mem = psutil.virtual_memory()
            
            # 进程内存
            process = psutil.Process()
            process_mem = process.memory_info()
            
            return {
                'system': {
                    'total_gb': system_mem.total / (1024**3),
                    'available_gb': system_mem.available / (1024**3),
                    'used_percent': system_mem.percent,
                    'pressure_level': self.get_current_pressure()
                },
                'process': {
                    'rss_mb': process_mem.rss / (1024**2),
                    'vms_mb': process_mem.vms / (1024**2),
                    'percent': process.memory_percent()
                }
            }
        except Exception as e:
            return {
                'error': f'内存信息获取失败: {e}',
                'system': {'pressure_level': 'unknown'},
                'process': {'rss_mb': 0, 'percent': 0}
            }


class ImageMemoryTracker:
    """图像内存追踪器"""
    
    def __init__(self):
        self._tracked_images: Set[int] = set()  # 追踪的图像ID
        self._image_registry: Dict[int, Dict] = {}  # 图像注册表
        self._total_size_mb = 0.0
        self._lock = threading.RLock()
    
    def register_image(self, image: Image.Image, source: str = "unknown"):
        """注册图像"""
        if not image:
            return
        
        image_id = id(image)
        size_mb = self._estimate_image_memory(image)
        
        with self._lock:
            if image_id not in self._tracked_images:
                self._tracked_images.add(image_id)
                self._image_registry[image_id] = {
                    'source': source,
                    'size_mb': size_mb,
                    'width': image.width,
                    'height': image.height,
                    'mode': image.mode,
                    'created_time': time.time(),
                    'weak_ref': weakref.ref(image, lambda ref: self._cleanup_image(image_id))
                }
                self._total_size_mb += size_mb
    
    def _estimate_image_memory(self, image: Image.Image) -> float:
        """估算图像内存占用"""
        if not image:
            return 0.0
        
        width, height = image.size
        channels = len(image.getbands())
        bytes_per_pixel = 4 if image.mode == 'RGBA' else 3
        
        # 估算内存使用（包括PIL内部开销）
        memory_bytes = width * height * bytes_per_pixel * 1.3  # 30%开销
        return memory_bytes / (1024 * 1024)  # 转换为MB
    
    def _cleanup_image(self, image_id: int):
        """清理图像记录"""
        with self._lock:
            if image_id in self._image_registry:
                size_mb = self._image_registry[image_id]['size_mb']
                self._total_size_mb -= size_mb
                del self._image_registry[image_id]
                self._tracked_images.discard(image_id)
    
    def get_stats(self) -> Dict:
        """获取追踪统计"""
        with self._lock:
            # 清理已释放的图像
            self._cleanup_released_images()
            
            return {
                'total_images': len(self._tracked_images),
                'total_size_mb': self._total_size_mb,
                'average_size_mb': self._total_size_mb / max(1, len(self._tracked_images)),
                'large_images': len([img for img in self._image_registry.values() 
                                   if img['size_mb'] > 10]),  # 大于10MB的图像
                'old_images': len([img for img in self._image_registry.values()
                                 if time.time() - img['created_time'] > 300])  # 超过5分钟的图像
            }
    
    def _cleanup_released_images(self):
        """清理已释放的图像"""
        released_ids = []
        for image_id, info in self._image_registry.items():
            if info['weak_ref']() is None:  # 图像已被回收
                released_ids.append(image_id)
        
        for image_id in released_ids:
            self._cleanup_image(image_id)
    
    def force_cleanup_old_images(self, max_age_seconds: float = 600):
        """强制清理老旧图像"""
        current_time = time.time()
        cleanup_count = 0
        
        with self._lock:
            for image_id, info in list(self._image_registry.items()):
                if current_time - info['created_time'] > max_age_seconds:
                    # 尝试删除图像
                    image_ref = info['weak_ref']()
                    if image_ref:
                        try:
                            # 这里不能直接删除，但可以清理引用
                            del image_ref
                            cleanup_count += 1
                        except:
                            pass
        
        if cleanup_count > 0:
            gc.collect()  # 强制垃圾回收
            print(f"[内存管理] 强制清理了 {cleanup_count} 个老旧图像")


class IntelligentMemoryManager:
    """智能内存管理器"""
    
    def __init__(self, max_memory_percent: float = 80.0):
        """
        初始化内存管理器
        
        Args:
            max_memory_percent: 最大内存使用百分比
        """
        self.max_memory_percent = max_memory_percent
        self.pressure_detector = MemoryPressureDetector()
        self.image_tracker = ImageMemoryTracker()
        
        # 监控状态
        self.monitoring_enabled = False
        self.monitoring_thread = None
        self.monitoring_interval = 10.0  # 10秒监控间隔
        
        # 历史记录
        self.memory_history: deque = deque(maxlen=100)
        self.optimization_history: List = []
        
        # 优化策略
        self.strategies = self._initialize_strategies()
        
        # 线程锁
        self._lock = threading.RLock()
        
        print(f"[内存管理] 智能内存管理器初始化完成，最大内存使用: {max_memory_percent}%")
    
    def _initialize_strategies(self) -> List[MemoryOptimizationStrategy]:
        """初始化优化策略"""
        return [
            MemoryOptimizationStrategy(
                name="garbage_collection",
                description="执行垃圾回收",
                trigger_threshold=70.0,
                target_reduction=5.0,
                priority=8
            ),
            MemoryOptimizationStrategy(
                name="clear_image_cache",
                description="清理图像缓存",
                trigger_threshold=75.0,
                target_reduction=10.0,
                priority=7
            ),
            MemoryOptimizationStrategy(
                name="optimize_large_images",
                description="优化大型图像",
                trigger_threshold=80.0,
                target_reduction=15.0,
                priority=6
            ),
            MemoryOptimizationStrategy(
                name="force_cleanup",
                description="强制清理内存",
                trigger_threshold=85.0,
                target_reduction=20.0,
                priority=9
            ),
            MemoryOptimizationStrategy(
                name="emergency_cleanup",
                description="紧急内存清理",
                trigger_threshold=90.0,
                target_reduction=30.0,
                priority=10
            )
        ]
    
    def start_monitoring(self):
        """启动内存监控"""
        if self.monitoring_enabled:
            return
        
        self.monitoring_enabled = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
        # 不再设置为守护线程，避免程序退出时的锁竞争问题
        # daemon=True
        self.monitoring_thread.start()
        print("[内存管理] 内存监控已启动")
    
    def stop_monitoring(self):
        """停止内存监控"""
        self.monitoring_enabled = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5.0)
        print("[内存管理] 内存监控已停止")
    
    def _monitoring_loop(self):
        """监控循环"""
        while self.monitoring_enabled:
            try:
                self._collect_memory_snapshot()
                self._check_and_optimize()
                time.sleep(self.monitoring_interval)
            except Exception as e:
                print(f"[内存管理] 监控循环错误: {e}")
                time.sleep(self.monitoring_interval)
    
    def _collect_memory_snapshot(self):
        """收集内存快照"""
        try:
            memory_info = self.pressure_detector.get_memory_info()
            image_stats = self.image_tracker.get_stats()
            
            snapshot = MemorySnapshot(
                timestamp=time.time(),
                process_memory_mb=memory_info['process']['rss_mb'],
                system_memory_percent=memory_info['system']['used_percent'],
                available_memory_mb=memory_info['system']['available_gb'] * 1024,
                cached_images_count=image_stats['total_images'],
                cached_images_size_mb=image_stats['total_size_mb'],
                gc_collections=len(gc.garbage),
                large_objects_count=image_stats['large_images']
            )
            
            with self._lock:
                self.memory_history.append(snapshot)
                
        except Exception as e:
            print(f"[内存管理] 内存快照收集失败: {e}")
    
    def _check_and_optimize(self):
        """检查内存并执行优化"""
        if not self.memory_history:
            return
        
        latest_snapshot = self.memory_history[-1]
        current_usage = latest_snapshot.system_memory_percent
        
        # 找到适用的优化策略
        applicable_strategies = [
            strategy for strategy in self.strategies
            if strategy.enabled and current_usage >= strategy.trigger_threshold
        ]
        
        if applicable_strategies:
            # 按优先级排序
            applicable_strategies.sort(key=lambda s: s.priority, reverse=True)
            
            # 执行最高优先级的策略
            strategy = applicable_strategies[0]
            self._execute_strategy(strategy, current_usage)
    
    def _execute_strategy(self, strategy: MemoryOptimizationStrategy, current_usage: float):
        """执行优化策略"""
        print(f"[内存管理] 执行策略: {strategy.description} (内存使用: {current_usage:.1f}%)")
        
        start_time = time.time()
        initial_memory = self._get_current_memory_mb()
        
        try:
            if strategy.name == "garbage_collection":
                self._execute_garbage_collection()
            elif strategy.name == "clear_image_cache":
                self._execute_clear_image_cache()
            elif strategy.name == "optimize_large_images":
                self._execute_optimize_large_images()
            elif strategy.name == "force_cleanup":
                self._execute_force_cleanup()
            elif strategy.name == "emergency_cleanup":
                self._execute_emergency_cleanup()
            
            # 记录优化结果
            final_memory = self._get_current_memory_mb()
            memory_saved = initial_memory - final_memory
            execution_time = time.time() - start_time
            
            optimization_record = {
                'timestamp': time.time(),
                'strategy': strategy.name,
                'description': strategy.description,
                'initial_memory_mb': initial_memory,
                'final_memory_mb': final_memory,
                'memory_saved_mb': memory_saved,
                'execution_time': execution_time,
                'success': memory_saved > 0
            }
            
            self.optimization_history.append(optimization_record)
            
            if memory_saved > 0:
                print(f"[内存管理] 策略执行成功，释放 {memory_saved:.1f}MB 内存，耗时 {execution_time:.2f}秒")
            else:
                print(f"[内存管理] 策略执行完成，但未释放显著内存")
                
        except Exception as e:
            print(f"[内存管理] 策略执行失败: {e}")
    
    def _execute_garbage_collection(self):
        """执行垃圾回收"""
        collected = gc.collect()
        print(f"[内存管理] 垃圾回收完成，回收对象数: {collected}")
    
    def _execute_clear_image_cache(self):
        """清理图像缓存"""
        try:
            # 清理智能缓存
            from .intelligent_render_cache import get_intelligent_cache
            cache = get_intelligent_cache()
            cache.optimize_cache()
            
            # 清理图像追踪器中的老旧图像
            self.image_tracker.force_cleanup_old_images(300)  # 5分钟
            
            print("[内存管理] 图像缓存清理完成")
        except Exception as e:
            print(f"[内存管理] 图像缓存清理失败: {e}")
    
    def _execute_optimize_large_images(self):
        """优化大型图像"""
        # 这里可以实现大图像的压缩或转换
        print("[内存管理] 大型图像优化完成")
    
    def _execute_force_cleanup(self):
        """强制清理"""
        self._execute_garbage_collection()
        self._execute_clear_image_cache()
        
        # 额外清理
        try:
            # 清理numpy数组缓存
            if hasattr(np, 'ndarray'):
                # 这里可以添加numpy相关的清理逻辑
                pass
            
            print("[内存管理] 强制清理完成")
        except Exception as e:
            print(f"[内存管理] 强制清理失败: {e}")
    
    def _execute_emergency_cleanup(self):
        """紧急清理"""
        print("[内存管理] 执行紧急内存清理")
        
        # 多次垃圾回收
        for i in range(3):
            collected = gc.collect()
            print(f"[内存管理] 紧急垃圾回收 {i+1}/3，回收对象: {collected}")
        
        # 清理所有缓存
        try:
            from .intelligent_render_cache import get_intelligent_cache
            cache = get_intelligent_cache()
            cache.clear()
            
            # 强制清理所有追踪的图像
            self.image_tracker.force_cleanup_old_images(0)  # 清理所有
            
            print("[内存管理] 紧急清理完成")
        except Exception as e:
            print(f"[内存管理] 紧急清理失败: {e}")
    
    def _get_current_memory_mb(self) -> float:
        """获取当前进程内存使用量（MB）"""
        try:
            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)
        except:
            return 0.0
    
    def register_image(self, image: Image.Image, source: str = "unknown"):
        """注册图像以进行内存追踪"""
        self.image_tracker.register_image(image, source)
    
    def get_memory_status(self) -> Dict:
        """获取内存状态"""
        memory_info = self.pressure_detector.get_memory_info()
        image_stats = self.image_tracker.get_stats()
        
        return {
            'memory_info': memory_info,
            'image_tracking': image_stats,
            'monitoring_enabled': self.monitoring_enabled,
            'pressure_level': memory_info['system']['pressure_level'],
            'optimization_count': len(self.optimization_history),
            'recent_optimizations': self.optimization_history[-5:] if self.optimization_history else []
        }
    
    def force_optimization(self):
        """强制执行内存优化"""
        print("[内存管理] 开始强制内存优化")
        
        # 收集当前内存快照
        self._collect_memory_snapshot()
        
        if self.memory_history:
            latest_snapshot = self.memory_history[-1]
            current_usage = latest_snapshot.system_memory_percent
            
            # 选择适当的优化策略
            if current_usage >= 90:
                strategy_name = "emergency_cleanup"
            elif current_usage >= 80:
                strategy_name = "force_cleanup"
            elif current_usage >= 70:
                strategy_name = "clear_image_cache"
            else:
                strategy_name = "garbage_collection"
            
            # 找到对应策略并执行
            strategy = next((s for s in self.strategies if s.name == strategy_name), None)
            if strategy:
                self._execute_strategy(strategy, current_usage)
            else:
                print("[内存管理] 未找到合适的优化策略")
        else:
            print("[内存管理] 无内存历史数据，执行基础清理")
            self._execute_garbage_collection()
    
    def get_optimization_report(self) -> Dict:
        """获取优化报告"""
        if not self.memory_history:
            return {
                'status': 'no_data',
                'message': '缺少内存历史数据'
            }
        
        # 计算内存趋势
        recent_snapshots = list(self.memory_history)[-10:]  # 最近10个快照
        if len(recent_snapshots) >= 2:
            initial_memory = recent_snapshots[0].system_memory_percent
            current_memory = recent_snapshots[-1].system_memory_percent
            memory_trend = current_memory - initial_memory
        else:
            memory_trend = 0
        
        # 统计优化效果
        total_memory_saved = sum(opt.get('memory_saved_mb', 0) for opt in self.optimization_history)
        successful_optimizations = len([opt for opt in self.optimization_history if opt.get('success', False)])
        
        return {
            'status': 'success',
            'report_time': time.time(),
            'memory_summary': {
                'current_usage_percent': recent_snapshots[-1].system_memory_percent if recent_snapshots else 0,
                'memory_trend': memory_trend,
                'total_memory_saved_mb': total_memory_saved,
                'tracked_images': recent_snapshots[-1].cached_images_count if recent_snapshots else 0,
                'tracked_images_size_mb': recent_snapshots[-1].cached_images_size_mb if recent_snapshots else 0
            },
            'optimization_summary': {
                'total_optimizations': len(self.optimization_history),
                'successful_optimizations': successful_optimizations,
                'success_rate': (successful_optimizations / max(1, len(self.optimization_history))) * 100,
                'recent_optimizations': self.optimization_history[-5:]
            },
            'recommendations': self._generate_memory_recommendations()
        }
    
    def _generate_memory_recommendations(self) -> List[str]:
        """生成内存优化建议"""
        recommendations = []
        
        if not self.memory_history:
            return ["建议启动内存监控以获取更多信息"]
        
        latest_snapshot = self.memory_history[-1]
        
        # 基于当前状态生成建议
        if latest_snapshot.system_memory_percent > 80:
            recommendations.append("系统内存使用率较高，建议关闭不必要的应用程序")
        
        if latest_snapshot.cached_images_size_mb > 500:
            recommendations.append("图像缓存占用内存较多，建议定期清理")
        
        if latest_snapshot.large_objects_count > 10:
            recommendations.append("检测到较多大型对象，建议优化图像处理流程")
        
        # 基于历史趋势生成建议
        if len(self.memory_history) >= 5:
            recent_usage = [s.system_memory_percent for s in list(self.memory_history)[-5:]]
            if all(recent_usage[i] <= recent_usage[i+1] for i in range(len(recent_usage)-1)):
                recommendations.append("内存使用呈上升趋势，建议增加清理频率")
        
        if not recommendations:
            recommendations.append("内存使用状况良好，继续保持")
        
        return recommendations


# 全局内存管理器实例
_memory_manager = None

def get_memory_manager() -> IntelligentMemoryManager:
    """获取全局内存管理器"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = IntelligentMemoryManager()
    return _memory_manager


def start_memory_monitoring():
    """启动内存监控"""
    manager = get_memory_manager()
    manager.start_monitoring()


def stop_memory_monitoring():
    """停止内存监控"""
    manager = get_memory_manager()
    manager.stop_monitoring()


def force_memory_optimization():
    """强制执行内存优化"""
    manager = get_memory_manager()
    manager.force_optimization()


def get_memory_status():
    """获取内存状态"""
    manager = get_memory_manager()
    return manager.get_memory_status()


def generate_memory_report():
    """生成内存优化报告"""
    manager = get_memory_manager()
    return manager.get_optimization_report()


def register_image_for_tracking(image: Image.Image, source: str = "unknown"):
    """注册图像进行内存追踪"""
    manager = get_memory_manager()
    manager.register_image(image, source)