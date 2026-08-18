"""批量导出预计算计划的数据模型。

从 ``batch_export_precomputer_v2``（当前最大单文件）抽离出来的纯数据定义，
便于在测试与未来的文件拆分中复用，而无需导入庞大的预计算类。

包含：
- ``LayerCombination``：一次完整导出所需的图层状态组合（含随机变换 / 参数），
  确保执行阶段不再有任何随机性。
- ``ExportTask``：单个导出任务（组合 + 输出文件名 / 路径 / 编号）。
- ``PrecomputedExportPlan``：批量导出的整体计划（任务列表、统计、诊断等）。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


@dataclass
class LayerCombination:
    """图层组合 - 完整预计算版本

    包含所有必要的参数，确保执行时不再有任何随机性
    """
    index: int
    layer_states: Dict[int, str]  # 图层索引 -> 图片文件路径
    layer_clone_settings: Dict[int, Dict]  # 图层索引 -> 分身设置
    combination_hash: str  # 组合的唯一哈希（基于完整参数）
    is_unique: bool

    # 🔧 强化预计算：添加完整的随机变换参数
    random_transforms: Dict[int, Dict] = None  # 图层索引 -> 随机变换参数
    # 随机变换参数包括：
    # - random_offset_x, random_offset_y: 随机位置偏移
    # - random_scale: 随机缩放比例
    # - random_rotation: 随机旋转角度

    # 添加图层的其他必要参数
    layer_parameters: Dict[int, Dict] = None  # 图层索引 -> 完整图层参数
    # 图层参数包括：
    # - opacity: 不透明度
    # - blend_mode: 混合模式
    # - x, y, width, height: 位置和尺寸
    # - fit_mode, crop_direction: 适配和裁剪
    # - corner_radius: 圆角
    # - stroke相关: 描边参数

    def __post_init__(self):
        """初始化时确保所有字典都存在"""
        if self.random_transforms is None:
            self.random_transforms = {}
        if self.layer_parameters is None:
            self.layer_parameters = {}


@dataclass
class ExportTask:
    """"""
    combination: LayerCombination
    filename: str
    file_path: str
    file_number: int


@dataclass
class PrecomputedExportPlan:
    """"""
    tasks: List[ExportTask]
    total_count: int
    unique_combinations: int
    estimated_time: float
    memory_requirement_mb: float
    optimization_suggestions: List[str]
    precompute_diagnostics: Optional[Dict[str, Any]] = None
