"""
统一性能优化器
在保持图像质量的前提下优化渲染性能
智能选择最佳的处理策略
整合了原有的performance.py和performance_monitor.py功能
增强版本：集成新的性能监控系统
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

import time
import threading
import functools
from typing import Tuple, Optional, Dict, Any, Callable
from PIL import Image
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc

# 导入智能线程池管理器
from .intelligent_thread_pool_manager import (
    get_thread_pool_manager, submit_task, TaskType, TaskPriority
)
from .thread_pool_config import get_config_manager

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    # 只在调试模式下显示详细警告
    import os
    if os.getenv('DEBUG_MODE') == '1':
        print("[WARNING] psutil不可用，部分性能监控功能将被禁用")

# 导入新的性能监控系统
try:
    from .performance.performance_monitor import get_performance_monitor, monitor_performance
    ENHANCED_MONITORING_AVAILABLE = True
except ImportError:
    ENHANCED_MONITORING_AVAILABLE = False


def time_it(func: Callable) -> Callable:
    """
    装饰器，用于测量函数执行时间
    增强版本：集成新的性能监控系统

    Args:
        func: 要测量的函数

    Returns:
        包装后的函数，会测量并记录执行时间
    """
    if ENHANCED_MONITORING_AVAILABLE:
        # 使用增强的性能监控系统
        return monitor_performance(f"time_it.{func.__name__}")(func)
    else:
        # 回退到原有实现
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()
            execution_time = end_time - start_time

            # 记录执行时间
            print(f"[性能] 函数 {func.__name__} 执行时间: {execution_time:.4f} 秒")

            return result

        return wrapper


class PerformanceOptimizer:
    """性能优化器 - 使用智能线程池管理器"""
    
    # 性能配置缓存
    _performance_cache = {}
    _system_info = None
    _thread_pool_manager = None
    _config_manager = None
    
    @classmethod
    def initialize(cls):
        """初始化性能优化器"""
        if cls._system_info is None:
            # 使用智能线程池管理器
            cls._thread_pool_manager = get_thread_pool_manager()
            cls._config_manager = get_config_manager()
            
            # 针对性能优化工作负载进行配置
            cls._thread_pool_manager.optimize_for_workload('mixed')
            
            cls._system_info = cls._get_system_info()
            
            # 获取实际的线程配置信息
            pool_status = cls._thread_pool_manager.get_pool_status()
            mixed_pool = pool_status['pools'].get('mixed', {})
            max_workers = mixed_pool.get('max_workers', 4)
            
            print(f"[性能优化] 智能线程池初始化完成，工作线程: {max_workers}")
            print(f"[性能优化] 系统信息: CPU核心={cls._system_info['cpu_count']}, 内存={cls._system_info['memory_gb']:.1f}GB")
    
    @classmethod
    def _get_system_info(cls) -> Dict[str, Any]:
        """获取系统信息"""
        try:
            if PSUTIL_AVAILABLE:
                memory_gb = psutil.virtual_memory().total / (1024**3)
                cpu_count = psutil.cpu_count()
            else:
                memory_gb = 8.0  # 默认假设8GB内存
                cpu_count = 4    # 默认假设4核CPU
            
            return {
                'memory_gb': memory_gb,
                'cpu_count': cpu_count,
                'performance_level': cls._determine_performance_level(memory_gb, cpu_count)
            }
        except:
            return {
                'memory_gb': 8.0,
                'cpu_count': 4,
                'performance_level': 'medium'
            }
    
    @classmethod
    def _determine_performance_level(cls, memory_gb: float, cpu_count: int) -> str:
        """确定系统性能级别"""
        if memory_gb >= 16 and cpu_count >= 8:
            return 'high'
        elif memory_gb >= 8 and cpu_count >= 4:
            return 'medium'
        else:
            return 'low'
    
    @classmethod
    def get_optimal_settings(cls, image_size: Tuple[int, int], 
                           layer_count: int, is_batch_mode: bool = False) -> Dict[str, Any]:
        """
        获取最优设置
        
        Args:
            image_size: 图像尺寸 (width, height)
            layer_count: 图层数量
            is_batch_mode: 是否批量模式
            
        Returns:
            优化设置字典
        """
        cls.initialize()
        
        # 🔧 关键修复：禁用性能优化器缓存，避免重复图片问题
        # 注释掉缓存检查，确保每次都重新计算
        cache_key = f"{image_size}_{layer_count}_{is_batch_mode}"  # 保留定义，但不使用缓存
        # if cache_key in cls._performance_cache:
        #     return cls._performance_cache[cache_key]
        
        width, height = image_size
        total_pixels = width * height
        
        # 基础设置
        settings = {
            'edge_enhancement': True,
            'subpixel_precision': True,
            'antialiasing_method': 'auto',
            'use_threading': False,
            'memory_optimization': False,
            'quality_level': 'high'
        }
        
        # 根据系统性能调整
        perf_level = cls._system_info['performance_level']
        
        if is_batch_mode:
            # 批量模式优化
            if perf_level == 'low' or total_pixels > 2000000:  # 2MP+
                settings.update({
                    'antialiasing_method': 'fxaa',
                    'subpixel_precision': False,
                    'quality_level': 'fast'
                })
            elif total_pixels > 1000000:  # 1MP+
                settings.update({
                    'antialiasing_method': 'smaa',
                    'quality_level': 'balanced'
                })
            
            # 批量模式启用线程优化
            if layer_count > 3:
                settings['use_threading'] = True
                
        else:
            # 实时模式优化
            if perf_level == 'low':
                if total_pixels > 1000000:
                    settings.update({
                        'antialiasing_method': 'fxaa',
                        'subpixel_precision': False
                    })
                elif total_pixels > 500000:
                    settings['antialiasing_method'] = 'smaa'
            elif perf_level == 'medium':
                if total_pixels > 2000000:
                    settings['antialiasing_method'] = 'smaa'
            # 高性能系统保持默认设置
        
        # 内存优化
        if total_pixels > 4000000 or layer_count > 10:  # 4MP+ 或 10+ 图层
            settings['memory_optimization'] = True
        
        # 🔧 关键修复：禁用性能优化器缓存存储，避免重复图片问题
        # cls._performance_cache[cache_key] = settings
        return settings
    
    @classmethod
    def optimize_composite_layer(cls, background: Image.Image, foreground: Image.Image,
                                position: Tuple[int, int], opacity: float,
                                blend_mode: str, settings: Dict[str, Any]) -> Image.Image:
        """
        优化的图层合成 - 修复版本，使用更稳定的合成方法
        """
        try:
            # 根据设置调整参数
            quality_level = settings.get('quality_level', 'high')

            # 修复：对于批量模式，使用更稳定的合成方法
            if quality_level == 'fast':
                # 快速模式：使用最简单的合成
                return cls._simple_composite(background, foreground, position, opacity)
            else:
                # 其他模式：尝试使用统一合成器，但有更好的错误处理
                try:
                    from app.utils.unified_alpha_compositor import unified_alpha_compositor

                    # 使用更保守的参数
                    return unified_alpha_compositor.composite_layer(
                        background=background,
                        foreground=foreground,
                        position=position,
                        opacity=opacity,
                        blend_mode=blend_mode,
                        use_srgb_blending=True  # 启用 Photoshop 风格混合
                    )

                except Exception as compositor_e:
                    print(f"[性能优化器] 统一合成器失败: {compositor_e}")
                    # 立即回退到简单合成
                    return cls._simple_composite(background, foreground, position, opacity)

        except Exception as e:
            print(f"[性能优化器] 优化合成失败: {e}")
            # 最终后备方案
            return cls._simple_composite(background, foreground, position, opacity)
    
    @classmethod
    def _simple_composite(cls, background: Image.Image, foreground: Image.Image,
                         position: Tuple[int, int], opacity: float) -> Image.Image:
        """简单稳定的合成方案"""
        try:
            result = background.copy()

            # 确保图像格式
            if foreground.mode != 'RGBA':
                foreground = foreground.convert('RGBA')

            if opacity < 1.0:
                # 调整不透明度
                alpha = foreground.split()[-1]
                alpha = alpha.point(lambda x: int(x * opacity))
                foreground = foreground.copy()
                foreground.putalpha(alpha)

            result.paste(foreground, position, foreground)
            return result

        except Exception as e:
            print(f"[性能优化器] 简单合成失败: {e}")
            return background

    @classmethod
    def _fallback_composite(cls, background: Image.Image, foreground: Image.Image,
                           position: Tuple[int, int], opacity: float) -> Image.Image:
        """后备合成方案（向后兼容）"""
        return cls._simple_composite(background, foreground, position, opacity)
    
    @classmethod
    def execute_parallel_task(cls, func: Callable, args_list: list, 
                            task_type=None, priority=None) -> list:
        """
        并行执行任务列表 - 使用智能线程池管理器
        
        Args:
            func: 要执行的函数
            args_list: 参数列表
            task_type: 任务类型（可选）
            priority: 任务优先级（可选）
            
        Returns:
            结果列表
        """
        cls.initialize()
        
        if not args_list:
            return []
        
        if len(args_list) == 1:
            # 单个任务直接执行
            return [func(*args_list[0])]
        
        try:
            # 尝试使用智能线程池管理器
            from .intelligent_thread_pool_manager import get_thread_pool_manager, TaskType, TaskPriority
            
            thread_pool_manager = get_thread_pool_manager()
            
            # 获取实际的线程配置信息
            pool_status = thread_pool_manager.get_pool_status()
            max_workers = pool_status['pools'].get('mixed', {}).get('max_workers', 4)
            
            # 使用配置的线程数执行任务
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(func, *args) for args in args_list]
                completed_results = [future.result() for future in futures]
            
            return completed_results
            
        except Exception as e:
            print(f"[性能优化] 并行执行失败，回退到串行: {e}")
            return [func(*args) for args in args_list]
    
    @classmethod
    def get_thread_pool_manager(cls):
        """获取智能线程池管理器实例"""
        try:
            from .intelligent_thread_pool_manager import get_thread_pool_manager
            return get_thread_pool_manager()
        except ImportError:
            print("[性能优化] 智能线程池管理器不可用")
            return None
    
    @classmethod
    def optimize_for_batch_processing(cls):
        """针对批量处理优化线程池配置"""
        try:
            thread_pool_manager = cls.get_thread_pool_manager()
            if thread_pool_manager:
                thread_pool_manager.optimize_for_workload('image_processing')
                print("[性能优化] 已切换为批量处理优化模式")
        except Exception as e:
            print(f"[性能优化] 批量处理优化失败: {e}")
    
    @classmethod
    def optimize_for_ui_responsiveness(cls):
        """针对UI响应性优化线程池配置"""
        try:
            thread_pool_manager = cls.get_thread_pool_manager()
            if thread_pool_manager:
                thread_pool_manager.optimize_for_workload('ui_responsive')
                print("[性能优化] 已切换为UI响应优化模式")
        except Exception as e:
            print(f"[性能优化] UI响应优化失败: {e}")
    
    @classmethod
    def batch_optimize_layers(cls, layers_data: list, background: Image.Image,
                             settings: Dict[str, Any]) -> Image.Image:
        """
        批量优化图层处理
        """
        if not settings.get('use_threading', False) or len(layers_data) < 3:
            # 单线程处理
            return cls._sequential_process_layers(layers_data, background, settings)
        else:
            # 多线程处理
            return cls._parallel_process_layers(layers_data, background, settings)
    
    @classmethod
    def _sequential_process_layers(cls, layers_data: list, background: Image.Image,
                                  settings: Dict[str, Any]) -> Image.Image:
        """顺序处理图层"""
        composition = background.copy()
        
        for layer_data in layers_data:
            composition = cls.optimize_composite_layer(
                background=composition,
                foreground=layer_data['image'],
                position=layer_data['position'],
                opacity=layer_data['opacity'],
                blend_mode=layer_data['blend_mode'],
                settings=settings
            )
            
            # 内存优化
            if settings.get('memory_optimization', False):
                gc.collect()
        
        return composition
    
    @classmethod
    def _parallel_process_layers(cls, layers_data: list, background: Image.Image,
                                settings: Dict[str, Any]) -> Image.Image:
        """并行处理图层（适用于独立图层）"""
        # 注意：这里简化实现，实际并行合成需要更复杂的算法
        # 当前实现仍然是顺序的，但预留了并行处理的框架
        return cls._sequential_process_layers(layers_data, background, settings)
    
    @classmethod
    def optimize_memory_usage(cls):
        """优化内存使用"""
        # 清理缓存
        cls._performance_cache.clear()
        
        # 强制垃圾回收
        gc.collect()
        
        print("[性能优化] 内存优化完成")
    
    @classmethod
    def get_performance_stats(cls) -> Dict[str, Any]:
        """获取性能统计"""
        try:
            if PSUTIL_AVAILABLE:
                memory = psutil.virtual_memory()
                cpu_percent = psutil.cpu_percent(interval=1)
            else:
                # 模拟内存和CPU信息
                class MockMemory:
                    percent = 50.0
                    available = 4 * 1024**3  # 4GB available
                memory = MockMemory()
                cpu_percent = 50.0
            
            return {
                'memory_used_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3),
                'cpu_percent': cpu_percent,
                'cache_size': len(cls._performance_cache),
                'system_performance_level': cls._system_info['performance_level'] if cls._system_info else 'unknown'
            }
        except:
            return {
                'memory_used_percent': 0,
                'memory_available_gb': 0,
                'cpu_percent': 0,
                'cache_size': len(cls._performance_cache),
                'system_performance_level': 'unknown'
            }
    
    @classmethod
    def should_use_fast_mode(cls, image_size: Tuple[int, int], 
                           layer_count: int, is_batch_mode: bool = False) -> bool:
        """
        判断是否应该使用快速模式
        """
        width, height = image_size
        total_pixels = width * height
        
        # 获取系统状态
        try:
            if PSUTIL_AVAILABLE:
                memory = psutil.virtual_memory()
                cpu_percent = psutil.cpu_percent()
                
                # 系统负载过高时使用快速模式
                if memory.percent > 85 or cpu_percent > 80:
                    return True
        except:
            pass
        
        # 大图像或多图层时在批量模式下使用快速模式
        if is_batch_mode:
            if total_pixels > 2000000 or layer_count > 8:
                return True
        
        return False

    @classmethod
    def get_enhanced_performance_stats(cls) -> Dict[str, Any]:
        """获取增强的性能统计信息"""
        basic_stats = cls.get_performance_stats()

        if ENHANCED_MONITORING_AVAILABLE:
            # 获取详细的性能监控数据
            monitor = get_performance_monitor()
            detailed_stats = monitor.get_statistics()
            slow_operations = monitor.get_slow_operations(0.5)

            basic_stats.update({
                'detailed_monitoring': detailed_stats,
                'slow_operations': slow_operations,
                'monitoring_enabled': True
            })
        else:
            basic_stats['monitoring_enabled'] = False

        return basic_stats

    @classmethod
    def generate_performance_report(cls) -> str:
        """生成详细的性能报告"""
        if ENHANCED_MONITORING_AVAILABLE:
            monitor = get_performance_monitor()
            return monitor.generate_report()
        else:
            stats = cls.get_performance_stats()
            report = []
            report.append("=== 基础性能报告 ===")
            report.append(f"内存使用: {stats['memory_used_percent']:.1f}%")
            report.append(f"可用内存: {stats['memory_available_gb']:.1f}GB")
            report.append(f"CPU使用: {stats['cpu_percent']:.1f}%")
            report.append(f"缓存大小: {stats['cache_size']}")
            report.append(f"性能级别: {stats['system_performance_level']}")
            return "\n".join(report)


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        
        if duration > 1.0:  # 超过1秒的操作记录
            print(f"[性能监控] {self.operation_name} 耗时: {duration:.2f}秒")
        
        return False


def test_performance_optimizer():
    """测试性能优化器"""
    print("=== 测试性能优化器 ===")
    
    # 初始化
    PerformanceOptimizer.initialize()
    
    # 测试不同场景的设置
    scenarios = [
        ((800, 600), 3, False, "小图像实时模式"),
        ((1920, 1080), 5, False, "中等图像实时模式"),
        ((4000, 3000), 8, False, "大图像实时模式"),
        ((800, 600), 10, True, "小图像批量模式"),
        ((1920, 1080), 15, True, "中等图像批量模式"),
        ((4000, 3000), 20, True, "大图像批量模式"),
    ]
    
    for image_size, layer_count, is_batch, description in scenarios:
        settings = PerformanceOptimizer.get_optimal_settings(
            image_size, layer_count, is_batch
        )
        
        print(f"\n{description}:")
        print(f"  图像尺寸: {image_size}")
        print(f"  图层数量: {layer_count}")
        print(f"  抗锯齿方法: {settings['antialiasing_method']}")
        print(f"  亚像素精度: {settings['subpixel_precision']}")
        print(f"  质量级别: {settings['quality_level']}")
        print(f"  使用线程: {settings['use_threading']}")
        print(f"  内存优化: {settings['memory_optimization']}")
    
    # 性能统计
    stats = PerformanceOptimizer.get_performance_stats()
    print(f"\n系统性能统计:")
    print(f"  内存使用: {stats['memory_used_percent']:.1f}%")
    print(f"  可用内存: {stats['memory_available_gb']:.1f}GB")
    print(f"  CPU使用: {stats['cpu_percent']:.1f}%")
    print(f"  性能级别: {stats['system_performance_level']}")
    
    print("✓ 性能优化器测试完成")
    return True


if __name__ == "__main__":
    test_performance_optimizer()
