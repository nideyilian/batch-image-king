"""
高级任务队列管理器
支持优先级调度、任务取消、批量处理和智能负载均衡
"""

import time
import threading
import uuid
import heapq
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from queue import Queue, Empty, Full
from concurrent.futures import Future, ThreadPoolExecutor
import weakref
import logging

from .intelligent_thread_pool_manager import TaskType, TaskPriority, TaskInfo


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"         # 等待中
    QUEUED = "queued"          # 已排队
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消
    TIMEOUT = "timeout"        # 超时


class QueuePolicy(Enum):
    """队列策略"""
    FIFO = "fifo"                    # 先进先出
    PRIORITY = "priority"            # 优先级队列
    FAIR_SHARE = "fair_share"        # 公平共享
    DEADLINE = "deadline"            # 截止时间优先
    ADAPTIVE = "adaptive"            # 自适应调度


@dataclass(order=True)
class PrioritizedTask:
    """优先级任务包装器"""
    priority: int = field(compare=True)
    created_time: float = field(compare=True)
    task_info: TaskInfo = field(compare=False)
    deadline: Optional[float] = field(default=None, compare=False)
    weight: float = field(default=1.0, compare=False)
    
    def __post_init__(self):
        # 确保优先级数值越小优先级越高
        self.sort_key = (self.priority, self.created_time)


@dataclass
class TaskBatch:
    """任务批次"""
    batch_id: str
    tasks: List[TaskInfo]
    batch_type: TaskType
    priority: TaskPriority
    submit_time: float
    dependency_tasks: Set[str] = field(default_factory=set)
    completion_callback: Optional[Callable] = None
    failure_callback: Optional[Callable] = None
    
    def __post_init__(self):
        if not self.batch_id:
            self.batch_id = str(uuid.uuid4())


class AdvancedTaskQueue:
    """高级任务队列"""
    
    def __init__(self, 
                 max_size: int = 1000,
                 queue_policy: QueuePolicy = QueuePolicy.PRIORITY,
                 enable_batching: bool = True,
                 batch_timeout: float = 1.0):
        
        self.max_size = max_size
        self.queue_policy = queue_policy
        self.enable_batching = enable_batching
        self.batch_timeout = batch_timeout
        
        # 不同策略的队列
        self._priority_queue: List[PrioritizedTask] = []
        self._fifo_queue: Queue = Queue(maxsize=max_size)
        self._fair_share_queues: Dict[TaskType, Queue] = {}
        
        # 任务管理
        self._pending_tasks: Dict[str, TaskInfo] = {}
        self._running_tasks: Dict[str, TaskInfo] = {}
        self._completed_tasks: Dict[str, TaskInfo] = {}
        self._completed_task_order = deque()
        self._max_completed_tasks = max(200, min(max_size, 2000))
        self._cancelled_tasks: Set[str] = set()
        
        # 批次管理
        self._pending_batches: Dict[str, TaskBatch] = {}
        self._batch_buffer: Dict[TaskType, List[TaskInfo]] = {}
        
        # 统计信息
        self._stats = {
            'tasks_submitted': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'tasks_cancelled': 0,
            'avg_wait_time': 0.0,
            'avg_execution_time': 0.0,
            'queue_length': 0,
            'peak_queue_length': 0
        }
        
        # 线程安全
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        
        # 后台线程
        self._batch_processor_thread: Optional[threading.Thread] = None
        self._queue_monitor_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # 回调管理
        self._task_callbacks = weakref.WeakValueDictionary()
        
        # 启动后台处理
        self._start_background_threads()
        
        self.logger = logging.getLogger(__name__)
    
    def _start_background_threads(self):
        """启动后台处理线程"""
        if self.enable_batching:
            self._batch_processor_thread = threading.Thread(
                target=self._batch_processor,
                name="BatchProcessor",
                daemon=True
            )
            self._batch_processor_thread.start()
        
        self._queue_monitor_thread = threading.Thread(
            target=self._queue_monitor,
            name="QueueMonitor",
            daemon=True
        )
        self._queue_monitor_thread.start()
    
    def submit_task(self, task_info: TaskInfo, 
                   deadline: Optional[float] = None,
                   weight: float = 1.0,
                   batch_id: Optional[str] = None) -> str:
        """
        提交任务到队列
        
        Args:
            task_info: 任务信息
            deadline: 截止时间（时间戳）
            weight: 任务权重
            batch_id: 批次ID（可选）
        
        Returns:
            str: 任务ID
        """
        with self._lock:
            if len(self._pending_tasks) >= self.max_size:
                raise Full("任务队列已满")
            
            task_id = task_info.task_id
            self._pending_tasks[task_id] = task_info
            self._stats['tasks_submitted'] += 1
            
            # 根据队列策略处理
            if self.queue_policy == QueuePolicy.PRIORITY:
                self._submit_to_priority_queue(task_info, deadline, weight)
            elif self.queue_policy == QueuePolicy.FIFO:
                self._submit_to_fifo_queue(task_info)
            elif self.queue_policy == QueuePolicy.FAIR_SHARE:
                self._submit_to_fair_share_queue(task_info)
            elif self.queue_policy == QueuePolicy.ADAPTIVE:
                self._submit_to_adaptive_queue(task_info, deadline, weight)
            
            # 批次处理
            if batch_id and self.enable_batching:
                self._add_to_batch(task_info, batch_id)
            elif self.enable_batching and not batch_id:
                self._add_to_buffer(task_info)
            
            # 更新统计
            current_queue_length = len(self._pending_tasks)
            self._stats['queue_length'] = current_queue_length
            if current_queue_length > self._stats['peak_queue_length']:
                self._stats['peak_queue_length'] = current_queue_length
            
            # 通知等待的线程
            self._condition.notify_all()
            
            self.logger.debug(f"任务已提交: {task_id}")
            return task_id
    
    def submit_batch(self, tasks: List[TaskInfo],
                    batch_type: TaskType,
                    priority: TaskPriority = TaskPriority.NORMAL,
                    completion_callback: Optional[Callable] = None,
                    failure_callback: Optional[Callable] = None) -> str:
        """
        提交批量任务
        
        Args:
            tasks: 任务列表
            batch_type: 批次类型
            priority: 批次优先级
            completion_callback: 完成回调
            failure_callback: 失败回调
        
        Returns:
            str: 批次ID
        """
        batch = TaskBatch(
            batch_id=str(uuid.uuid4()),
            tasks=tasks,
            batch_type=batch_type,
            priority=priority,
            submit_time=time.time(),
            completion_callback=completion_callback,
            failure_callback=failure_callback
        )
        
        with self._lock:
            self._pending_batches[batch.batch_id] = batch
            
            # 为批次中的每个任务提交到队列
            for task_info in tasks:
                task_info.task_id = f"{batch.batch_id}_{task_info.task_id}"
                self.submit_task(task_info, batch_id=batch.batch_id)
        
        self.logger.info(f"批次已提交: {batch.batch_id}, 任务数: {len(tasks)}")
        return batch.batch_id
    
    def get_next_task(self, task_types: Optional[List[TaskType]] = None,
                     timeout: Optional[float] = None) -> Optional[TaskInfo]:
        """
        获取下一个要执行的任务
        
        Args:
            task_types: 支持的任务类型列表
            timeout: 超时时间
        
        Returns:
            Optional[TaskInfo]: 下一个任务，如果没有则返回None
        """
        start_time = time.time()
        
        with self._condition:
            while True:
                # 检查是否有可执行的任务
                task_info = self._get_next_task_internal(task_types)
                if task_info:
                    # 移动到执行队列
                    task_id = task_info.task_id
                    if task_id in self._pending_tasks:
                        del self._pending_tasks[task_id]
                        self._running_tasks[task_id] = task_info
                        self._stats['queue_length'] = len(self._pending_tasks)
                    
                    self.logger.debug(f"获取任务: {task_id}")
                    return task_info
                
                # 检查超时
                if timeout is not None:
                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        return None
                    wait_time = timeout - elapsed
                else:
                    wait_time = None
                
                # 等待新任务
                self._condition.wait(timeout=wait_time)
                
                # 检查关闭事件
                if self._shutdown_event.is_set():
                    return None
    
    def _get_next_task_internal(self, task_types: Optional[List[TaskType]]) -> Optional[TaskInfo]:
        """内部获取下一个任务的实现"""
        if self.queue_policy == QueuePolicy.PRIORITY:
            return self._get_from_priority_queue(task_types)
        elif self.queue_policy == QueuePolicy.FIFO:
            return self._get_from_fifo_queue(task_types)
        elif self.queue_policy == QueuePolicy.FAIR_SHARE:
            return self._get_from_fair_share_queue(task_types)
        elif self.queue_policy == QueuePolicy.ADAPTIVE:
            return self._get_from_adaptive_queue(task_types)
        else:
            return self._get_from_priority_queue(task_types)
    
    def complete_task(self, task_id: str, result: Any = None, error: Optional[Exception] = None):
        """
        标记任务完成
        
        Args:
            task_id: 任务ID
            result: 任务结果
            error: 错误信息（如果任务失败）
        """
        with self._lock:
            if task_id in self._running_tasks:
                task_info = self._running_tasks.pop(task_id)
                self._completed_tasks[task_id] = task_info
                self._completed_task_order.append(task_id)
                
                if error:
                    self._stats['tasks_failed'] += 1
                    self.logger.warning(f"任务失败: {task_id}, 错误: {error}")
                else:
                    self._stats['tasks_completed'] += 1
                    self.logger.debug(f"任务完成: {task_id}")
                
                # 更新平均执行时间
                if hasattr(task_info, 'start_time') and task_info.start_time:
                    execution_time = time.time() - task_info.start_time
                    self._update_avg_execution_time(execution_time)
                
                # 检查批次完成状态
                self._check_batch_completion(task_id)
                self._prune_completed_tasks_locked()
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            bool: 是否成功取消
        """
        with self._lock:
            if task_id in self._pending_tasks:
                # 从待处理队列中移除
                del self._pending_tasks[task_id]
                self._cancelled_tasks.add(task_id)
                self._stats['tasks_cancelled'] += 1
                self._stats['queue_length'] = len(self._pending_tasks)
                
                # 从各种队列中移除
                self._remove_from_queues(task_id)
                
                self.logger.info(f"任务已取消: {task_id}")
                return True
            
            elif task_id in self._running_tasks:
                # 正在执行的任务无法直接取消，只能标记
                self._cancelled_tasks.add(task_id)
                self.logger.warning(f"任务正在执行，仅标记为取消: {task_id}")
                return False
            
            return False
    
    def cancel_batch(self, batch_id: str) -> int:
        """
        取消整个批次
        
        Args:
            batch_id: 批次ID
        
        Returns:
            int: 成功取消的任务数
        """
        cancelled_count = 0
        
        with self._lock:
            if batch_id in self._pending_batches:
                batch = self._pending_batches[batch_id]
                
                for task_info in batch.tasks:
                    task_id = f"{batch_id}_{task_info.task_id}"
                    if self.cancel_task(task_id):
                        cancelled_count += 1
                
                # 移除批次
                del self._pending_batches[batch_id]
                
                self.logger.info(f"批次已取消: {batch_id}, 取消任务数: {cancelled_count}")
        
        return cancelled_count
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        with self._lock:
            return {
                'pending_tasks': len(self._pending_tasks),
                'running_tasks': len(self._running_tasks),
                'completed_tasks': len(self._completed_tasks),
                'cancelled_tasks': len(self._cancelled_tasks),
                'pending_batches': len(self._pending_batches),
                'queue_policy': self.queue_policy.value,
                'max_size': self.max_size,
                'stats': self._stats.copy()
            }
    
    def _submit_to_priority_queue(self, task_info: TaskInfo, 
                                deadline: Optional[float], weight: float):
        """提交到优先级队列"""
        priority_value = task_info.priority.value
        if deadline:
            # 截止时间越近优先级越高
            time_factor = max(0, deadline - time.time())
            priority_value -= time_factor * 0.01
        
        prioritized_task = PrioritizedTask(
            priority=int(priority_value * 1000),  # 转为整数便于比较
            created_time=task_info.created_time,
            task_info=task_info,
            deadline=deadline,
            weight=weight
        )
        
        heapq.heappush(self._priority_queue, prioritized_task)
    
    def _get_from_priority_queue(self, task_types: Optional[List[TaskType]]) -> Optional[TaskInfo]:
        """从优先级队列获取任务"""
        temp_tasks = []
        result = None
        
        try:
            while self._priority_queue:
                prioritized_task = heapq.heappop(self._priority_queue)
                task_info = prioritized_task.task_info
                
                # 检查任务类型
                if task_types is None or task_info.task_type in task_types:
                    # 检查是否已取消
                    if task_info.task_id not in self._cancelled_tasks:
                        result = task_info
                        break
                else:
                    temp_tasks.append(prioritized_task)
            
        finally:
            # 将不匹配的任务放回队列
            for task in temp_tasks:
                heapq.heappush(self._priority_queue, task)
        
        return result
    
    def _submit_to_fifo_queue(self, task_info: TaskInfo):
        """提交到FIFO队列"""
        try:
            self._fifo_queue.put_nowait(task_info)
        except Full:
            raise Full("FIFO队列已满")
    
    def _get_from_fifo_queue(self, task_types: Optional[List[TaskType]]) -> Optional[TaskInfo]:
        """从FIFO队列获取任务"""
        temp_tasks = []
        result = None
        
        try:
            while not self._fifo_queue.empty():
                try:
                    task_info = self._fifo_queue.get_nowait()
                    
                    # 检查任务类型和取消状态
                    if ((task_types is None or task_info.task_type in task_types) and
                        task_info.task_id not in self._cancelled_tasks):
                        result = task_info
                        break
                    else:
                        temp_tasks.append(task_info)
                        
                except Empty:
                    break
        finally:
            # 将不匹配的任务放回队列
            for task in reversed(temp_tasks):
                try:
                    self._fifo_queue.put_nowait(task)
                except Full:
                    break
        
        return result
    
    def _submit_to_fair_share_queue(self, task_info: TaskInfo):
        """提交到公平共享队列"""
        task_type = task_info.task_type
        
        if task_type not in self._fair_share_queues:
            self._fair_share_queues[task_type] = Queue()
        
        try:
            self._fair_share_queues[task_type].put_nowait(task_info)
        except Full:
            raise Full(f"公平共享队列({task_type.value})已满")
    
    def _get_from_fair_share_queue(self, task_types: Optional[List[TaskType]]) -> Optional[TaskInfo]:
        """从公平共享队列获取任务（轮询）"""
        if not self._fair_share_queues:
            return None
        
        # 简单的轮询策略
        available_types = (task_types if task_types 
                          else list(self._fair_share_queues.keys()))
        
        for task_type in available_types:
            if task_type in self._fair_share_queues:
                queue = self._fair_share_queues[task_type]
                try:
                    task_info = queue.get_nowait()
                    if task_info.task_id not in self._cancelled_tasks:
                        return task_info
                except Empty:
                    continue
        
        return None
    
    def _submit_to_adaptive_queue(self, task_info: TaskInfo,
                                deadline: Optional[float], weight: float):
        """提交到自适应队列（混合策略）"""
        # 根据系统负载和任务特性选择最佳策略
        if deadline and (deadline - time.time()) < 5.0:
            # 紧急任务使用优先级队列
            self._submit_to_priority_queue(task_info, deadline, weight)
        elif len(self._pending_tasks) > self.max_size * 0.8:
            # 队列接近满时使用FIFO避免饥饿
            self._submit_to_fifo_queue(task_info)
        else:
            # 正常情况使用公平共享
            self._submit_to_fair_share_queue(task_info)
    
    def _get_from_adaptive_queue(self, task_types: Optional[List[TaskType]]) -> Optional[TaskInfo]:
        """从自适应队列获取任务"""
        # 优先处理紧急任务
        urgent_task = self._get_from_priority_queue(task_types)
        if urgent_task:
            return urgent_task
        
        # 然后处理公平共享
        fair_task = self._get_from_fair_share_queue(task_types)
        if fair_task:
            return fair_task
        
        # 最后处理FIFO
        return self._get_from_fifo_queue(task_types)
    
    def _remove_from_queues(self, task_id: str):
        """从所有队列中移除指定任务"""
        # 从优先级队列移除
        self._priority_queue = [pt for pt in self._priority_queue 
                              if pt.task_info.task_id != task_id]
        heapq.heapify(self._priority_queue)
        
        # 从FIFO队列移除
        temp_tasks = []
        while not self._fifo_queue.empty():
            try:
                task = self._fifo_queue.get_nowait()
                if task.task_id != task_id:
                    temp_tasks.append(task)
            except Empty:
                break
        
        for task in temp_tasks:
            try:
                self._fifo_queue.put_nowait(task)
            except Full:
                break
        
        # 从公平共享队列移除
        for task_type, queue in self._fair_share_queues.items():
            temp_tasks = []
            while not queue.empty():
                try:
                    task = queue.get_nowait()
                    if task.task_id != task_id:
                        temp_tasks.append(task)
                except Empty:
                    break
            
            for task in temp_tasks:
                try:
                    queue.put_nowait(task)
                except Full:
                    break
    
    def _add_to_batch(self, task_info: TaskInfo, batch_id: str):
        """将任务添加到批次"""
        if batch_id in self._pending_batches:
            batch = self._pending_batches[batch_id]
            if task_info not in batch.tasks:
                batch.tasks.append(task_info)
    
    def _add_to_buffer(self, task_info: TaskInfo):
        """将任务添加到批次缓冲区"""
        task_type = task_info.task_type
        if task_type not in self._batch_buffer:
            self._batch_buffer[task_type] = []
        
        self._batch_buffer[task_type].append(task_info)
    
    def _batch_processor(self):
        """批次处理器后台线程"""
        while not self._shutdown_event.is_set():
            try:
                with self._lock:
                    # 检查缓冲区中的任务
                    for task_type, tasks in list(self._batch_buffer.items()):
                        if (len(tasks) >= 5 or  # 任务数达到阈值
                            (tasks and time.time() - tasks[0].created_time > self.batch_timeout)):
                            
                            # 创建批次
                            batch_tasks = tasks[:10]  # 限制批次大小
                            self._batch_buffer[task_type] = tasks[10:]
                            
                            if batch_tasks:
                                batch = TaskBatch(
                                    batch_id=str(uuid.uuid4()),
                                    tasks=batch_tasks,
                                    batch_type=task_type,
                                    priority=TaskPriority.NORMAL,
                                    submit_time=time.time()
                                )
                                self._pending_batches[batch.batch_id] = batch
                                
                                self.logger.info(f"自动创建批次: {batch.batch_id}, 任务数: {len(batch_tasks)}")
                
                self._shutdown_event.wait(timeout=0.5)  # 避免过于频繁的检查
                
            except Exception as e:
                self.logger.error(f"批次处理器错误: {e}")
                self._shutdown_event.wait(timeout=1.0)
    
    def _queue_monitor(self):
        """队列监控后台线程"""
        while not self._shutdown_event.is_set():
            try:
                with self._lock:
                    # 更新统计信息
                    self._update_queue_statistics()
                    
                    # 检查超时任务
                    self._check_timeout_tasks()
                    
                    # 队列健康检查
                    self._health_check()
                
                self._shutdown_event.wait(timeout=5.0)  # 每5秒检查一次
                
            except Exception as e:
                self.logger.error(f"队列监控错误: {e}")
                self._shutdown_event.wait(timeout=1.0)
    
    def _check_batch_completion(self, completed_task_id: str):
        """检查批次完成状态"""
        for batch_id, batch in list(self._pending_batches.items()):
            batch_task_ids = {f"{batch_id}_{task.task_id}" for task in batch.tasks}
            completed_batch_tasks = batch_task_ids.intersection(set(self._completed_tasks.keys()))
            
            if len(completed_batch_tasks) == len(batch.tasks):
                # 批次完成
                del self._pending_batches[batch_id]
                
                if batch.completion_callback:
                    try:
                        batch.completion_callback(batch_id, batch.tasks)
                    except Exception as e:
                        self.logger.error(f"批次完成回调错误: {e}")

                # 批次已完成，及时释放完成任务记录，避免长期堆积占用内存
                for done_task_id in completed_batch_tasks:
                    self._completed_tasks.pop(done_task_id, None)
                
                self.logger.info(f"批次完成: {batch_id}")

    def _prune_completed_tasks_locked(self):
        """控制已完成任务历史大小，避免内存持续增长（调用方需持有锁）。"""
        while len(self._completed_task_order) > self._max_completed_tasks:
            old_task_id = self._completed_task_order.popleft()
            self._completed_tasks.pop(old_task_id, None)
    
    def _update_avg_execution_time(self, execution_time: float):
        """更新平均执行时间"""
        completed = self._stats['tasks_completed']
        if completed > 1:
            current_avg = self._stats['avg_execution_time']
            self._stats['avg_execution_time'] = (
                (current_avg * (completed - 1) + execution_time) / completed
            )
        else:
            self._stats['avg_execution_time'] = execution_time
    
    def _update_queue_statistics(self):
        """更新队列统计信息"""
        # 这里可以添加更多的统计信息更新逻辑
        pass
    
    def _check_timeout_tasks(self):
        """检查超时任务"""
        current_time = time.time()
        timeout_tasks = []
        
        for task_id, task_info in self._running_tasks.items():
            if (hasattr(task_info, 'timeout') and task_info.timeout and
                hasattr(task_info, 'start_time') and task_info.start_time and
                current_time - task_info.start_time > task_info.timeout):
                timeout_tasks.append(task_id)
        
        for task_id in timeout_tasks:
            self.logger.warning(f"任务超时: {task_id}")
            # 这里可以实现超时处理逻辑
    
    def _health_check(self):
        """队列健康检查"""
        # 检查队列是否过满
        if len(self._pending_tasks) > self.max_size * 0.9:
            self.logger.warning("队列接近满载")
        
        # 检查是否有长时间未处理的任务
        current_time = time.time()
        old_tasks = [
            task_id for task_id, task_info in self._pending_tasks.items()
            if current_time - task_info.created_time > 300  # 5分钟
        ]
        
        if old_tasks:
            self.logger.warning(f"发现长时间未处理的任务: {len(old_tasks)}个")
    
    def shutdown(self):
        """关闭队列管理器"""
        self.logger.info("正在关闭任务队列管理器...")
        
        self._shutdown_event.set()
        
        # 等待后台线程结束
        if self._batch_processor_thread and self._batch_processor_thread.is_alive():
            self._batch_processor_thread.join(timeout=5.0)
        
        if self._queue_monitor_thread and self._queue_monitor_thread.is_alive():
            self._queue_monitor_thread.join(timeout=5.0)
        
        self.logger.info("任务队列管理器已关闭")


# 全局队列管理器实例
_global_task_queue = None
_queue_lock = threading.Lock()


def get_task_queue(queue_policy: QueuePolicy = QueuePolicy.PRIORITY,
                  max_size: int = 1000) -> AdvancedTaskQueue:
    """获取全局任务队列管理器实例"""
    global _global_task_queue
    
    if _global_task_queue is None:
        with _queue_lock:
            if _global_task_queue is None:
                _global_task_queue = AdvancedTaskQueue(
                    max_size=max_size,
                    queue_policy=queue_policy,
                    enable_batching=True
                )
    
    return _global_task_queue


def shutdown_task_queue():
    """关闭全局任务队列管理器"""
    global _global_task_queue
    
    if _global_task_queue is not None:
        _global_task_queue.shutdown()
        _global_task_queue = None