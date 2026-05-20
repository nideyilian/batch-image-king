"""
批量导出协调器

负责协调批量导出流程，但不包含具体的导出逻辑
"""

from typing import Callable, Optional, Dict, Any, List, Tuple
import os
from PySide6.QtCore import QObject, Signal


class BatchExportCoordinator(QObject):
    """
    批量导出协调器
    
    负责协调批量导出的流程，具体的导出逻辑委托给其他类。
    这个类主要负责：
    1. 参数验证
    2. 流程协调
    3. 进度报告
    4. 错误处理
    
    具体的导出逻辑仍在Document类或工具类中实现。
    """
    
    # 信号
    export_started = Signal()  # 导出开始
    export_progress = Signal(int, int)  # 导出进度（当前, 总数）
    file_exported = Signal(str)  # 单个文件导出完成
    export_finished = Signal(bool, str)  # 导出完成（成功, 消息）
    export_cancelled = Signal()  # 导出取消
    
    def __init__(self, parent: QObject = None):
        """
        初始化批量导出协调器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        self._is_cancelled = False
    
    def validate_export_params(self,
                               directory: str,
                               count: int,
                               filename_template: str,
                               file_format: str) -> Tuple[bool, str]:
        """
        验证导出参数
        
        Args:
            directory: 输出目录
            count: 导出数量
            filename_template: 文件名模板
            file_format: 文件格式
            
        Returns:
            (是否有效, 错误消息)
        """
        
        # 验证目录
        if not directory:
            return False, "输出目录不能为空"
        
        # 验证目录是否存在或可创建
        try:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
        except Exception as e:
            return False, f"无法创建输出目录: {e}"
        
        # 验证导出数量
        if count <= 0:
            return False, "导出数量必须大于0"
        
        if count > 10000:
            return False, "导出数量不能超过10000（性能考虑）"
        
        # 验证文件名模板
        if not filename_template:
            return False, "文件名模板不能为空"
        
        # 验证文件格式
        supported_formats = ['png', 'jpg', 'jpeg', 'bmp', 'tiff', 'webp']
        if file_format.lower() not in supported_formats:
            return False, f"不支持的文件格式: {file_format}"
        
        return True, ""
    
    def prepare_export_params(self,
                             directory: str,
                             count: int,
                             filename_template: Optional[str] = None,
                             file_format: str = "png",
                             start_index: int = 1,
                             **kwargs) -> Dict[str, Any]:
        """
        准备导出参数
        
        Args:
            directory: 输出目录
            count: 导出数量
            filename_template: 文件名模板
            file_format: 文件格式
            start_index: 起始序号
            **kwargs: 其他参数
            
        Returns:
            标准化的导出参数字典
        """
        # 标准化文件名模板
        if not filename_template:
            filename_template = "output_{number}"
        
        # 确保文件名模板包含序号占位符
        if '{number}' not in filename_template and '{index}' not in filename_template:
            filename_template = f"{filename_template}_{{number}}"
        
        # 构建参数字典
        export_params = {
            'directory': directory,
            'count': count,
            'filename_template': filename_template,
            'file_format': file_format.lower(),
            'start_index': start_index,
            'use_high_performance': kwargs.get('use_high_performance', True),
            'traverse_mode': kwargs.get('traverse_mode', False),
            'use_smart_sampling': kwargs.get('use_smart_sampling', True),
            'force_opaque': kwargs.get('force_opaque', file_format.lower() in ['jpg', 'jpeg']),
        }
        
        return export_params
    
    def cancel_export(self):
        """取消当前导出"""
        self._is_cancelled = True
        self.export_cancelled.emit()
    
    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._is_cancelled
    
    def reset_cancel_flag(self):
        """重置取消标志"""
        self._is_cancelled = False
    
    def report_progress(self, current: int, total: int):
        """
        报告进度
        
        Args:
            current: 当前进度
            total: 总数
        """
        self.export_progress.emit(current, total)
    
    def report_file_exported(self, file_path: str):
        """
        报告文件导出完成
        
        Args:
            file_path: 文件路径
        """
        self.file_exported.emit(file_path)
    
    def estimate_export_time(self, 
                            count: int,
                            layers_count: int,
                            canvas_size: tuple) -> float:
        """
        估算导出时间
        
        Args:
            count: 导出数量
            layers_count: 图层数量
            canvas_size: 画布尺寸（宽, 高）
            
        Returns:
            估算时间（秒）
        """
        # 基础时间（每张图）
        base_time_per_image = 0.1  # 秒
        
        # 图层复杂度因子
        layer_factor = 0.05 * layers_count
        
        # 尺寸复杂度因子
        width, height = canvas_size
        size_factor = (width * height) / (1920 * 1080) * 0.1
        
        # 总时间
        time_per_image = base_time_per_image + layer_factor + size_factor
        total_time = time_per_image * count
        
        return total_time
    
    def format_time_estimate(self, seconds: float) -> str:
        """
        格式化时间估算
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化的时间字符串
        """
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}小时{minutes}分"


if __name__ == "__main__":
    # 测试代码
    coordinator = BatchExportCoordinator()
    
    # 测试参数验证
    valid, msg = coordinator.validate_export_params(
        directory="./output",
        count=10,
        filename_template="test_{number}",
        file_format="png"
    )
    print(f"参数验证: {valid}, {msg}")
    
    # 测试时间估算
    estimated_time = coordinator.estimate_export_time(
        count=100,
        layers_count=5,
        canvas_size=(1920, 1080)
    )
    print(f"估算时间: {coordinator.format_time_estimate(estimated_time)}")

