"""
智能线程池管理器
根据系统资源动态调整线程池配置，统一管理全局线程池资源
"""

import os
import psutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Callable, Any, List, Union, Tuple
from queue import PriorityQueue, Queue
import logging
import weakref


class TaskPriority(Enum):
    """任务优先级"""
    CRITICAL = 0    # 关键任务（UI响应等）
    HIGH = 1        # 高优先级（用户操作等）
    NORMAL = 2      # 普通任务（后台处理等）
    LOW = 3         # 低优先级（清理、统计等）


class TaskType(Enum):
    """任务类型"""
    IO_INTENSIVE = "io_intensive"      # I/O密集型（文件读写、网络等）
    CPU_INTENSIVE = "cpu_intensive"    # CPU密集型（图像处理、计算等）
    MIXED = "mixed"                    # 混合型任务
    UI_RESPONSIVE = "ui_responsive"    # UI响应任务


@dataclass
class PoolConfig:
    """线程池配置"""
    max_workers: int
    min_workers: int = 1
    idle_timeout: float = 60.0  # 空闲超时时间（秒）
    queue_size: int = 100       # 队列大小
    auto_scale: bool = True     # 是否自动扩缩容


@dataclass
class SystemResources:
    """系统资源信息"""
    cpu_count: int
    memory_total: int  # MB
    memory_available: int  # MB
    cpu_usage: float  # 百分比
    memory_usage: float  # 百分比
    load_average: float  # 系统负载


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    priority: TaskPriority
    task_type: TaskType
    func: Callable
    args: tuple
    kwargs: dict
    callback: Optional[Callable] = None
    error_callback: Optional[Callable] = None
    timeout: Optional[float] = None
    created_time: Optional[float] = None
    start_time: Optional[float] = None  # 添加开始时间字段
    
    def __post_init__(self):
        if self.created_time is None:
            self.created_time = time.time()
    
    def __lt__(self, other):
        """比较函数，用于优先级队列排序"""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return (self.created_time or 0) < (other.created_time or 0)


class IntelligentThreadPoolManager:
    """智能线程池管理器 - 集成高级任务队列"""
    
    def __init__(self):
        self._pools: Dict[TaskType, ThreadPoolExecutor] = {}
        self._pool_configs: Dict[TaskType, PoolConfig] = {}
        self._task_queues: Dict[TaskType, PriorityQueue] = {}
        self._active_tasks: Dict[str, TaskInfo] = {}
        self._task_counters: Dict[TaskType, int] = {}
        
        # 集成高级任务队列管理器
        from .advanced_task_queue import get_task_queue, QueuePolicy
        self._advanced_queue = get_task_queue(
            queue_policy=QueuePolicy.ADAPTIVE,
            max_size=2000
        )
        
        # 性能监控
        self._performance_stats = {
            'tasks_completed': 0,
            'tasks_failed': 0,
            'average_execution_time': 0.0,
            'peak_concurrent_tasks': 0,
            'pool_utilization': {},
            'queue_stats': {}
        }
        
        # 控制标志
        self._shutdown_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._scheduler_threads: Dict[TaskType, threading.Thread] = {}
        
        # 回调管理
        self._task_callbacks = weakref.WeakValueDictionary()
        
        # 初始化
        self._setup_default_configs()
        self._initialize_pools()
        self._start_monitoring()
        
        self.logger = logging.getLogger(__name__)
        
        print("[智能线程池] 已集成高级任务队列管理器")
    
    def _setup_default_configs(self):
        """设置默认配置"""
        system_resources = self._get_system_resources()
        
        # CPU密集型任务：使用CPU核心数
        self._pool_configs[TaskType.CPU_INTENSIVE] = PoolConfig(
            max_workers=max(1, system_resources.cpu_count),
            min_workers=1,
            idle_timeout=30.0,
            queue_size=50
        )
        
        # I/O密集型任务：使用更多线程
        self._pool_configs[TaskType.IO_INTENSIVE] = PoolConfig(
            max_workers=max(4, system_resources.cpu_count * 2),
            min_workers=2,
            idle_timeout=60.0,
            queue_size=200
        )
        
        # 混合型任务：介于两者之间
        self._pool_configs[TaskType.MIXED] = PoolConfig(
            max_workers=max(2, int(system_resources.cpu_count * 1.5)),
            min_workers=1,
            idle_timeout=45.0,
            queue_size=100
        )
        
        # UI响应任务：少量快速线程
        self._pool_configs[TaskType.UI_RESPONSIVE] = PoolConfig(
            max_workers=2,
            min_workers=1,
            idle_timeout=10.0,
            queue_size=20
        )
    
    def _get_system_resources(self) -> SystemResources:
        """获取系统资源信息"""
        try:
            cpu_count = os.cpu_count() or 4
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # 获取系统负载（仅在Unix系统上可用）
            try:
                load_avg = os.getloadavg()[0] if hasattr(os, 'getloadavg') else cpu_percent / 100
            except (AttributeError, OSError):
                load_avg = cpu_percent / 100
            
            return SystemResources(
                cpu_count=cpu_count,
                memory_total=memory.total // (1024 * 1024),  # 转换为MB
                memory_available=memory.available // (1024 * 1024),
                cpu_usage=cpu_percent,
                memory_usage=memory.percent,
                load_average=load_avg
            )
        except Exception as e:
            self.logger.warning(f"获取系统资源信息失败: {e}，使用默认值")
            return SystemResources(
                cpu_count=4,
                memory_total=8192,
                memory_available=4096,
                cpu_usage=50.0,
                memory_usage=50.0,
                load_average=0.5
            )
    
    def _initialize_pools(self):
        """初始化线程池"""
        for task_type, config in self._pool_configs.items():
            self._pools[task_type] = ThreadPoolExecutor(
                max_workers=config.max_workers,
                thread_name_prefix=f"ThreadPool-{task_type.value}"
            )
            self._task_queues[task_type] = PriorityQueue(maxsize=config.queue_size)
            self._task_counters[task_type] = 0
            
            # 🔧 关键修夏：不再使用daemon=True，避免程序退出时的锁竞争问题
            scheduler = threading.Thread(
                target=self._task_scheduler,
                args=(task_type,),
                name=f"Scheduler-{task_type.value}",
                daemon=True  # 恢复daemon=True以防止进程残留
            )
            scheduler.start()
            self._scheduler_threads[task_type] = scheduler
    
    def _start_monitoring(self):
        """启动监控线程"""
        # 🔧 关键修夏：不再使用daemon=True，避免程序退出时的锁竞争问题
        self._monitor_thread = threading.Thread(
            target=self._resource_monitor,
            name="ResourceMonitor",
            daemon=True  # 恢复daemon=True以防止进程残留
        )
        self._monitor_thread.start()
    
    def _resource_monitor(self):
        """资源监控循环"""
        while not self._shutdown_event.is_set():
            try:
                # 每30秒检查一次资源使用情况
                time.sleep(30)
                
                if self._shutdown_event.is_set():
                    break
                
                system_resources = self._get_system_resources()
                self._adjust_pool_sizes(system_resources)
                
            except Exception as e:
                self.logger.error(f"资源监控出错: {e}")
    
    def _adjust_pool_sizes(self, resources: SystemResources):
        """根据系统资源调整线程池大小"""
        try:
            # 如果系统负载过高，减少线程数
            if resources.cpu_usage > 80 or resources.memory_usage > 85:
                scale_factor = 0.7
            elif resources.cpu_usage > 60 or resources.memory_usage > 70:
                scale_factor = 0.85
            elif resources.cpu_usage < 30 and resources.memory_usage < 50:
                scale_factor = 1.2
            else:
                scale_factor = 1.0
            
            for task_type, config in self._pool_configs.items():
                current_pool = self._pools[task_type]
                new_max_workers = max(
                    config.min_workers,
                    min(
                        config.max_workers,
                        int(current_pool._max_workers * scale_factor)
                    )
                )
                
                if new_max_workers != current_pool._max_workers:
                    self.logger.info(f"调整{task_type.value}线程池大小: {current_pool._max_workers} -> {new_max_workers}")
                    current_pool._max_workers = new_max_workers
                    
        except Exception as e:
            self.logger.error(f"调整线程池大小失败: {e}")
    
    def _task_scheduler(self, task_type: TaskType):
        """任务调度器"""
        queue = self._task_queues[task_type]
        pool = self._pools[task_type]
        
        while not self._shutdown_event.is_set():
            try:
                # 从队列获取任务（阻塞等待）
                try:
                    task_info = queue.get(timeout=1.0)
                except:
                    continue  # 超时继续循环
                
                if task_info is None:  # 停止信号
                    break
                
                # 提交任务到线程池
                future = pool.submit(self._execute_task, task_info)
                
                # 将future与任务关联
                self._active_tasks[task_info.task_id] = task_info
                
                queue.task_done()
                
            except Exception as e:
                self.logger.error(f"任务调度出错: {e}")
    
    def _execute_task(self, task_info: TaskInfo) -> Any:
        """执行任务"""
        start_time = time.time()
        
        try:
            # 执行任务
            if task_info.timeout:
                # TODO: 实现超时控制
                result = task_info.func(*task_info.args, **task_info.kwargs)
            else:
                result = task_info.func(*task_info.args, **task_info.kwargs)
            
            # 执行成功回调
            if task_info.callback:
                try:
                    task_info.callback(result)
                except Exception as e:
                    self.logger.error(f"任务回调执行失败: {e}")
            
            # 更新统计
            execution_time = time.time() - start_time
            self._update_performance_stats(True, execution_time)
            
            return result
            
        except Exception as e:
            # 执行错误回调
            if task_info.error_callback:
                try:
                    task_info.error_callback(e)
                except Exception as callback_error:
                    self.logger.error(f"错误回调执行失败: {callback_error}")
            
            # 更新统计
            self._update_performance_stats(False, time.time() - start_time)
            
            self.logger.error(f"任务执行失败: {e}")
            raise
            
        finally:
            # 清理任务记录
            self._active_tasks.pop(task_info.task_id, None)
    
    def _update_performance_stats(self, success: bool, execution_time: float):
        """更新性能统计"""
        if success:
            self._performance_stats['tasks_completed'] += 1
        else:
            self._performance_stats['tasks_failed'] += 1
        
        # 更新平均执行时间
        total_tasks = self._performance_stats['tasks_completed'] + self._performance_stats['tasks_failed']
        current_avg = self._performance_stats['average_execution_time']
        self._performance_stats['average_execution_time'] = (
            (current_avg * (total_tasks - 1) + execution_time) / total_tasks
        )
        
        # 更新峰值并发任务数
        current_active = len(self._active_tasks)
        if current_active > self._performance_stats['peak_concurrent_tasks']:
            self._performance_stats['peak_concurrent_tasks'] = current_active
    
    def submit_task(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        task_type: TaskType = TaskType.MIXED,
        priority: TaskPriority = TaskPriority.NORMAL,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
        timeout: Optional[float] = None,
        task_id: Optional[str] = None,
        deadline: Optional[float] = None,
        weight: float = 1.0,
        use_advanced_queue: bool = True
    ) -> str:
        """
        提交任务到线程池 - 支持高级队列功能
        
        Args:
            func: 要执行的函数
            args: 函数参数
            kwargs: 函数关键字参数
            task_type: 任务类型
            priority: 任务优先级
            callback: 成功回调函数
            error_callback: 错误回调函数
            timeout: 任务超时时间（秒）
            task_id: 自定义任务ID
            deadline: 截止时间（时间戳）
            weight: 任务权重
            use_advanced_queue: 是否使用高级队列
        
        Returns:
            str: 任务ID
        """
        if kwargs is None:
            kwargs = {}
        
        if task_id is None:
            self._task_counters[task_type] += 1
            task_id = f"{task_type.value}_{self._task_counters[task_type]}_{int(time.time()*1000)}"
        
        task_info = TaskInfo(
            task_id=task_id,
            priority=priority,
            task_type=task_type,
            func=func,
            args=args,
            kwargs=kwargs,
            callback=callback,
            error_callback=error_callback,
            timeout=timeout
        )
        
        try:
            if use_advanced_queue and hasattr(self, '_advanced_queue'):
                # 使用高级队列管理器
                return self._advanced_queue.submit_task(
                    task_info=task_info,
                    deadline=deadline,
                    weight=weight
                )
            else:
                # 使用原有的简单队列
                queue = self._task_queues[task_type]
                queue.put(task_info, block=False)
                
                self.logger.debug(f"任务已提交: {task_id}")
                return task_id
                
        except Exception as e:
            self.logger.error(f"提交任务失败: {e}")
            raise
    
    def submit_batch_tasks(
        self,
        tasks: List[Tuple[Callable, tuple, dict]],
        task_type: TaskType = TaskType.MIXED,
        priority: TaskPriority = TaskPriority.NORMAL,
        completion_callback: Optional[Callable] = None,
        failure_callback: Optional[Callable] = None
    ) -> str:
        """
        提交批量任务
        
        Args:
            tasks: 任务列表，每个元素为 (func, args, kwargs)
            task_type: 任务类型
            priority: 任务优先级
            completion_callback: 完成回调
            failure_callback: 失败回调
        
        Returns:
            str: 批次ID
        """
        if not hasattr(self, '_advanced_queue') or not tasks:
            raise ValueError("高级队列不可用或任务列表为空")
        
        # 转换为TaskInfo列表
        task_infos = []
        for i, (func, args, kwargs) in enumerate(tasks):
            task_id = f"batch_task_{i}_{int(time.time()*1000)}"
            task_info = TaskInfo(
                task_id=task_id,
                priority=priority,
                task_type=task_type,
                func=func,
                args=args,
                kwargs=kwargs or {}
            )
            task_infos.append(task_info)
        
        # 提交批次
        return self._advanced_queue.submit_batch(
            tasks=task_infos,
            batch_type=task_type,
            priority=priority,
            completion_callback=completion_callback,
            failure_callback=failure_callback
        )
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务 - 增强版
        
        Args:
            task_id: 任务ID
        
        Returns:
            bool: 是否成功取消
        """
        if hasattr(self, '_advanced_queue'):
            return self._advanced_queue.cancel_task(task_id)
        else:
            # 原有的简单实现
            if task_id in self._active_tasks:
                self.logger.warning(f"任务 {task_id} 正在执行，无法取消")
                return False
            
            self.logger.info(f"任务 {task_id} 已取消")
            return True
    
    def cancel_batch(self, batch_id: str) -> int:
        """
        取消整个批次
        
        Args:
            batch_id: 批次ID
        
        Returns:
            int: 成功取消的任务数
        """
        if hasattr(self, '_advanced_queue'):
            return self._advanced_queue.cancel_batch(batch_id)
        else:
            self.logger.warning("高级队列不可用，无法取消批次")
            return 0
    
    def get_pool_status(self) -> Dict[str, Any]:
        """获取线程池状态 - 增强版"""
        status = {}
        
        for task_type, pool in self._pools.items():
            queue = self._task_queues[task_type]
            status[task_type.value] = {
                'max_workers': pool._max_workers,
                'active_threads': len(pool._threads),
                'queue_size': queue.qsize(),
                'queue_maxsize': queue.maxsize
            }
        
        # 获取高级队列状态
        advanced_queue_status = {}
        if hasattr(self, '_advanced_queue'):
            try:
                advanced_queue_status = self._advanced_queue.get_queue_status()
                self._performance_stats['queue_stats'] = advanced_queue_status
            except Exception as e:
                self.logger.warning(f"获取高级队列状态失败: {e}")
        
        return {
            'pools': status,
            'active_tasks': len(self._active_tasks),
            'performance_stats': self._performance_stats.copy(),
            'system_resources': self._get_system_resources().__dict__,
            'advanced_queue': advanced_queue_status
        }
    
    def optimize_for_workload(self, workload_type: str):
        """
        针对特定工作负载优化
        
        Args:
            workload_type: 工作负载类型 ('image_processing', 'file_io', 'mixed', 'ui_responsive')
        """
        system_resources = self._get_system_resources()
        
        if workload_type == 'image_processing':
            # 图像处理：CPU密集型
            self._pool_configs[TaskType.CPU_INTENSIVE].max_workers = system_resources.cpu_count
            self._pool_configs[TaskType.IO_INTENSIVE].max_workers = max(2, system_resources.cpu_count // 2)
            
        elif workload_type == 'file_io':
            # 文件I/O：I/O密集型
            self._pool_configs[TaskType.IO_INTENSIVE].max_workers = system_resources.cpu_count * 3
            self._pool_configs[TaskType.CPU_INTENSIVE].max_workers = max(1, system_resources.cpu_count // 2)
            
        elif workload_type == 'ui_responsive':
            # UI响应：低延迟
            self._pool_configs[TaskType.UI_RESPONSIVE].max_workers = 3
            for task_type in [TaskType.CPU_INTENSIVE, TaskType.IO_INTENSIVE]:
                config = self._pool_configs[task_type]
                config.max_workers = max(config.min_workers, config.max_workers // 2)
        
        # 重新初始化线程池
        self._reinitialize_pools()
        
        self.logger.info(f"已针对 {workload_type} 工作负载进行优化")
    
    def _reinitialize_pools(self):
        """重新初始化线程池"""
        # 关闭现有线程池
        for pool in self._pools.values():
            pool.shutdown(wait=False)
        
        # 重新创建线程池
        self._initialize_pools()
    
    def shutdown(self, wait: bool = True):
        """关闭线程池管理器 - 增强版，处理非daemon线程"""
        self.logger.info("正在关闭线程池管理器...")
        
        # 设置停止标志
        self._shutdown_event.set()
        
        try:
            # 向所有队列发送停止信号
            for queue in self._task_queues.values():
                try:
                    queue.put(None, block=False)
                except:
                    pass
            
            # 等待调度线程结束
            for task_type, scheduler in self._scheduler_threads.items():
                if scheduler.is_alive():
                    self.logger.info(f"等待调度线程 {task_type.value} 结束...")
                    scheduler.join(timeout=8.0)  # 增加超时时间
                    if scheduler.is_alive():
                        self.logger.warning(f"调度线程 {task_type.value} 未能在限定时间内结束")
            
            # 关闭所有线程池
            for task_type, pool in self._pools.items():
                self.logger.info(f"关闭线程池 {task_type.value}...")
                pool.shutdown(wait=wait)
            
            # 等待监控线程结束
            if self._monitor_thread and self._monitor_thread.is_alive():
                self.logger.info("等待监控线程结束...")
                self._monitor_thread.join(timeout=8.0)  # 增加超时时间
                if self._monitor_thread.is_alive():
                    self.logger.warning("监控线程未能在限定时间内结束")
            
            self.logger.info("线程池管理器已关闭")
            
        except Exception as e:
            self.logger.error(f"关闭线程池管理器时出现异常: {e}")


# 全局单例实例
_thread_pool_manager = None
_manager_lock = threading.Lock()


def get_thread_pool_manager() -> IntelligentThreadPoolManager:
    """获取全局线程池管理器实例"""
    global _thread_pool_manager
    
    if _thread_pool_manager is None:
        with _manager_lock:
            if _thread_pool_manager is None:
                _thread_pool_manager = IntelligentThreadPoolManager()
    
    return _thread_pool_manager


def submit_task(
    func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    task_type: TaskType = TaskType.MIXED,
    priority: TaskPriority = TaskPriority.NORMAL,
    **submit_kwargs
) -> str:
    """便捷的任务提交函数"""
    manager = get_thread_pool_manager()
    return manager.submit_task(
        func=func,
        args=args,
        kwargs=kwargs,
        task_type=task_type,
        priority=priority,
        **submit_kwargs
    )


def shutdown_thread_pools(wait: bool = True):
    """关闭全局线程池管理器"""
    global _thread_pool_manager
    
    if _thread_pool_manager is not None:
        _thread_pool_manager.shutdown(wait=wait)
        _thread_pool_manager = None