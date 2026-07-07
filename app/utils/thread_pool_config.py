"""
线程池配置管理器
提供灵活的配置选项和环境变量支持
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

import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

from .intelligent_thread_pool_manager import TaskType, TaskPriority, PoolConfig


@dataclass
class ThreadPoolSettings:
    """线程池全局设置"""
    enable_auto_scaling: bool = True
    enable_resource_monitoring: bool = True
    monitoring_interval: float = 30.0  # 秒
    max_queue_wait_time: float = 5.0   # 秒
    enable_performance_logging: bool = False
    config_auto_save: bool = True
    
    # 性能调优参数
    cpu_threshold_high: float = 80.0      # CPU使用率高阈值
    cpu_threshold_low: float = 30.0       # CPU使用率低阈值
    memory_threshold_high: float = 85.0   # 内存使用率高阈值
    memory_threshold_low: float = 50.0    # 内存使用率低阈值
    
    # 扩缩容参数
    scale_up_factor: float = 1.2
    scale_down_factor: float = 0.7
    scale_conservative_factor: float = 0.85


class ThreadPoolConfigManager:
    """线程池配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self._get_default_config_path()
        self.settings = ThreadPoolSettings()
        self.custom_pool_configs: Dict[TaskType, PoolConfig] = {}
        
        # 加载配置
        self.load_config()
        self._apply_environment_overrides()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        # 尝试从环境变量获取
        env_path = os.environ.get('THREAD_POOL_CONFIG_PATH')
        if env_path and os.path.exists(env_path):
            return env_path
        
        # 默认路径
        app_root = Path(__file__).parent.parent.parent
        config_dir = app_root / 'config'
        config_dir.mkdir(exist_ok=True)
        
        return str(config_dir / 'thread_pool_config.json')
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # 加载全局设置
                if 'settings' in config_data:
                    settings_data = config_data['settings']
                    for key, value in settings_data.items():
                        if hasattr(self.settings, key):
                            setattr(self.settings, key, value)
                
                # 加载自定义池配置
                if 'pool_configs' in config_data:
                    for task_type_str, pool_config_data in config_data['pool_configs'].items():
                        try:
                            task_type = TaskType(task_type_str)
                            pool_config = PoolConfig(
                                max_workers=pool_config_data.get('max_workers', 4),
                                min_workers=pool_config_data.get('min_workers', 1),
                                idle_timeout=pool_config_data.get('idle_timeout', 60.0),
                                queue_size=pool_config_data.get('queue_size', 100),
                                auto_scale=pool_config_data.get('auto_scale', True)
                            )
                            self.custom_pool_configs[task_type] = pool_config
                        except (ValueError, KeyError) as e:
                            print(f"加载池配置失败 {task_type_str}: {e}")
                
                print(f"配置已从 {self.config_file} 加载")
            else:
                print(f"配置文件不存在，使用默认配置: {self.config_file}")
                
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
    
    def save_config(self):
        """保存配置文件"""
        try:
            config_data = {
                'settings': asdict(self.settings),
                'pool_configs': {}
            }
            
            # 保存自定义池配置
            for task_type, pool_config in self.custom_pool_configs.items():
                config_data['pool_configs'][task_type.value] = asdict(pool_config)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            print(f"配置已保存到 {self.config_file}")
            
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def _apply_environment_overrides(self):
        """应用环境变量覆盖"""
        # 全局设置环境变量覆盖
        env_mappings = {
            'THREAD_POOL_AUTO_SCALING': ('enable_auto_scaling', bool),
            'THREAD_POOL_RESOURCE_MONITORING': ('enable_resource_monitoring', bool),
            'THREAD_POOL_MONITORING_INTERVAL': ('monitoring_interval', float),
            'THREAD_POOL_MAX_QUEUE_WAIT': ('max_queue_wait_time', float),
            'THREAD_POOL_PERFORMANCE_LOGGING': ('enable_performance_logging', bool),
            'THREAD_POOL_CONFIG_AUTO_SAVE': ('config_auto_save', bool),
            
            'THREAD_POOL_CPU_HIGH_THRESHOLD': ('cpu_threshold_high', float),
            'THREAD_POOL_CPU_LOW_THRESHOLD': ('cpu_threshold_low', float),
            'THREAD_POOL_MEMORY_HIGH_THRESHOLD': ('memory_threshold_high', float),
            'THREAD_POOL_MEMORY_LOW_THRESHOLD': ('memory_threshold_low', float),
            
            'THREAD_POOL_SCALE_UP_FACTOR': ('scale_up_factor', float),
            'THREAD_POOL_SCALE_DOWN_FACTOR': ('scale_down_factor', float),
            'THREAD_POOL_SCALE_CONSERVATIVE_FACTOR': ('scale_conservative_factor', float),
        }
        
        for env_key, (attr_name, type_converter) in env_mappings.items():
            env_value = os.environ.get(env_key)
            if env_value is not None:
                try:
                    if type_converter == bool:
                        value = env_value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        value = type_converter(env_value)
                    
                    setattr(self.settings, attr_name, value)
                    print(f"环境变量覆盖: {attr_name} = {value}")
                    
                except (ValueError, TypeError) as e:
                    print(f"环境变量 {env_key} 值无效: {env_value}, 错误: {e}")
        
        # 特定任务类型的池配置环境变量
        for task_type in TaskType:
            prefix = f"THREAD_POOL_{task_type.value.upper()}"
            
            pool_config = self.custom_pool_configs.get(task_type, PoolConfig(max_workers=4))
            updated = False
            
            # 最大工作线程数
            max_workers_env = os.environ.get(f"{prefix}_MAX_WORKERS")
            if max_workers_env:
                try:
                    pool_config.max_workers = int(max_workers_env)
                    updated = True
                except ValueError:
                    print(f"无效的环境变量值: {prefix}_MAX_WORKERS = {max_workers_env}")
            
            # 最小工作线程数
            min_workers_env = os.environ.get(f"{prefix}_MIN_WORKERS")
            if min_workers_env:
                try:
                    pool_config.min_workers = int(min_workers_env)
                    updated = True
                except ValueError:
                    print(f"无效的环境变量值: {prefix}_MIN_WORKERS = {min_workers_env}")
            
            # 空闲超时
            idle_timeout_env = os.environ.get(f"{prefix}_IDLE_TIMEOUT")
            if idle_timeout_env:
                try:
                    pool_config.idle_timeout = float(idle_timeout_env)
                    updated = True
                except ValueError:
                    print(f"无效的环境变量值: {prefix}_IDLE_TIMEOUT = {idle_timeout_env}")
            
            # 队列大小
            queue_size_env = os.environ.get(f"{prefix}_QUEUE_SIZE")
            if queue_size_env:
                try:
                    pool_config.queue_size = int(queue_size_env)
                    updated = True
                except ValueError:
                    print(f"无效的环境变量值: {prefix}_QUEUE_SIZE = {queue_size_env}")
            
            # 自动扩缩容
            auto_scale_env = os.environ.get(f"{prefix}_AUTO_SCALE")
            if auto_scale_env:
                pool_config.auto_scale = auto_scale_env.lower() in ('true', '1', 'yes', 'on')
                updated = True
            
            if updated:
                self.custom_pool_configs[task_type] = pool_config
                print(f"环境变量更新了 {task_type.value} 池配置")
    
    def get_pool_config(self, task_type: TaskType) -> Optional[PoolConfig]:
        """获取指定任务类型的池配置"""
        return self.custom_pool_configs.get(task_type)
    
    def set_pool_config(self, task_type: TaskType, pool_config: PoolConfig):
        """设置指定任务类型的池配置"""
        self.custom_pool_configs[task_type] = pool_config
        
        if self.settings.config_auto_save:
            self.save_config()
    
    def get_workload_preset(self, workload_type: str) -> Dict[TaskType, PoolConfig]:
        """获取预设的工作负载配置"""
        cpu_count = os.cpu_count() or 4
        
        presets = {
            'image_processing': {
                TaskType.CPU_INTENSIVE: PoolConfig(
                    max_workers=cpu_count,
                    min_workers=1,
                    idle_timeout=30.0,
                    queue_size=50,
                    auto_scale=True
                ),
                TaskType.IO_INTENSIVE: PoolConfig(
                    max_workers=max(2, cpu_count // 2),
                    min_workers=1,
                    idle_timeout=60.0,
                    queue_size=100,
                    auto_scale=True
                ),
                TaskType.MIXED: PoolConfig(
                    max_workers=max(2, int(cpu_count * 0.75)),
                    min_workers=1,
                    idle_timeout=45.0,
                    queue_size=75,
                    auto_scale=True
                ),
                TaskType.UI_RESPONSIVE: PoolConfig(
                    max_workers=2,
                    min_workers=1,
                    idle_timeout=10.0,
                    queue_size=20,
                    auto_scale=False
                )
            },
            
            'file_operations': {
                TaskType.IO_INTENSIVE: PoolConfig(
                    max_workers=cpu_count * 3,
                    min_workers=2,
                    idle_timeout=60.0,
                    queue_size=200,
                    auto_scale=True
                ),
                TaskType.CPU_INTENSIVE: PoolConfig(
                    max_workers=max(1, cpu_count // 2),
                    min_workers=1,
                    idle_timeout=30.0,
                    queue_size=25,
                    auto_scale=True
                ),
                TaskType.MIXED: PoolConfig(
                    max_workers=cpu_count * 2,
                    min_workers=1,
                    idle_timeout=45.0,
                    queue_size=150,
                    auto_scale=True
                ),
                TaskType.UI_RESPONSIVE: PoolConfig(
                    max_workers=1,
                    min_workers=1,
                    idle_timeout=5.0,
                    queue_size=10,
                    auto_scale=False
                )
            },
            
            'ui_responsive': {
                TaskType.UI_RESPONSIVE: PoolConfig(
                    max_workers=3,
                    min_workers=2,
                    idle_timeout=5.0,
                    queue_size=30,
                    auto_scale=False
                ),
                TaskType.CPU_INTENSIVE: PoolConfig(
                    max_workers=max(1, cpu_count // 2),
                    min_workers=1,
                    idle_timeout=20.0,
                    queue_size=20,
                    auto_scale=True
                ),
                TaskType.IO_INTENSIVE: PoolConfig(
                    max_workers=max(2, cpu_count),
                    min_workers=1,
                    idle_timeout=30.0,
                    queue_size=50,
                    auto_scale=True
                ),
                TaskType.MIXED: PoolConfig(
                    max_workers=max(1, int(cpu_count * 0.75)),
                    min_workers=1,
                    idle_timeout=25.0,
                    queue_size=30,
                    auto_scale=True
                )
            },
            
            'balanced': {
                TaskType.CPU_INTENSIVE: PoolConfig(
                    max_workers=cpu_count,
                    min_workers=1,
                    idle_timeout=30.0,
                    queue_size=50,
                    auto_scale=True
                ),
                TaskType.IO_INTENSIVE: PoolConfig(
                    max_workers=cpu_count * 2,
                    min_workers=2,
                    idle_timeout=60.0,
                    queue_size=100,
                    auto_scale=True
                ),
                TaskType.MIXED: PoolConfig(
                    max_workers=int(cpu_count * 1.5),
                    min_workers=1,
                    idle_timeout=45.0,
                    queue_size=75,
                    auto_scale=True
                ),
                TaskType.UI_RESPONSIVE: PoolConfig(
                    max_workers=2,
                    min_workers=1,
                    idle_timeout=10.0,
                    queue_size=20,
                    auto_scale=False
                )
            }
        }
        
        return presets.get(workload_type, presets['balanced'])
    
    def apply_workload_preset(self, workload_type: str):
        """应用工作负载预设"""
        preset_configs = self.get_workload_preset(workload_type)
        
        for task_type, pool_config in preset_configs.items():
            self.custom_pool_configs[task_type] = pool_config
        
        if self.settings.config_auto_save:
            self.save_config()
        
        print(f"已应用 {workload_type} 工作负载预设")
    
    def reset_to_defaults(self):
        """重置为默认配置"""
        self.settings = ThreadPoolSettings()
        self.custom_pool_configs.clear()
        
        if self.settings.config_auto_save:
            self.save_config()
        
        print("已重置为默认配置")
    
    def get_environment_help(self) -> str:
        """获取环境变量帮助信息"""
        help_text = """
线程池配置环境变量:

全局设置:
  THREAD_POOL_AUTO_SCALING=true/false           - 启用自动扩缩容
  THREAD_POOL_RESOURCE_MONITORING=true/false    - 启用资源监控
  THREAD_POOL_MONITORING_INTERVAL=30.0          - 监控间隔(秒)
  THREAD_POOL_MAX_QUEUE_WAIT=5.0                - 最大队列等待时间(秒)
  THREAD_POOL_PERFORMANCE_LOGGING=true/false    - 启用性能日志
  THREAD_POOL_CONFIG_AUTO_SAVE=true/false       - 自动保存配置

阈值设置:
  THREAD_POOL_CPU_HIGH_THRESHOLD=80.0           - CPU高阈值(%)
  THREAD_POOL_CPU_LOW_THRESHOLD=30.0            - CPU低阈值(%)
  THREAD_POOL_MEMORY_HIGH_THRESHOLD=85.0        - 内存高阈值(%)
  THREAD_POOL_MEMORY_LOW_THRESHOLD=50.0         - 内存低阈值(%)

扩缩容因子:
  THREAD_POOL_SCALE_UP_FACTOR=1.2               - 扩容因子
  THREAD_POOL_SCALE_DOWN_FACTOR=0.7             - 缩容因子
  THREAD_POOL_SCALE_CONSERVATIVE_FACTOR=0.85    - 保守缩容因子

任务类型特定配置 (替换 [TYPE] 为 cpu_intensive, io_intensive, mixed, ui_responsive):
  THREAD_POOL_[TYPE]_MAX_WORKERS=4              - 最大工作线程数
  THREAD_POOL_[TYPE]_MIN_WORKERS=1              - 最小工作线程数
  THREAD_POOL_[TYPE]_IDLE_TIMEOUT=60.0          - 空闲超时(秒)
  THREAD_POOL_[TYPE]_QUEUE_SIZE=100             - 队列大小
  THREAD_POOL_[TYPE]_AUTO_SCALE=true/false      - 是否自动扩缩容

示例:
  THREAD_POOL_CPU_INTENSIVE_MAX_WORKERS=8
  THREAD_POOL_IO_INTENSIVE_QUEUE_SIZE=200
  THREAD_POOL_UI_RESPONSIVE_AUTO_SCALE=false

配置文件:
  THREAD_POOL_CONFIG_PATH=/path/to/config.json  - 自定义配置文件路径
        """
        return help_text.strip()


# 全局配置管理器实例
_config_manager = None


def get_config_manager() -> ThreadPoolConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ThreadPoolConfigManager()
    
    return _config_manager