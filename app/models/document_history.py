"""
文档历史记录管理模块

负责文档的撤销/重做功能
"""

from typing import Any, List, Optional
from PySide6.QtCore import QObject, Signal
import copy


class DocumentHistory(QObject):
    """
    文档历史记录管理器
    
    负责管理文档的撤销/重做历史记录，遵循单一职责原则。
    """
    
    # 信号
    history_changed = Signal()  # 历史记录变化信号
    
    def __init__(self, max_history: int = 20, parent: QObject = None):
        """
        初始化历史记录管理器
        
        Args:
            max_history: 最大历史记录数量
            parent: 父对象
        """
        super().__init__(parent)
        
        self._history: List[dict] = []  # 历史记录列表
        self._history_index: int = -1  # 当前历史记录索引
        self._max_history: int = max_history  # 最大历史记录数
        self._enabled: bool = True  # 是否启用历史记录
    
    @property
    def max_history(self) -> int:
        """获取最大历史记录数"""
        return self._max_history
    
    @max_history.setter
    def max_history(self, value: int):
        """设置最大历史记录数"""
        self._max_history = max(1, value)
        # 如果历史记录超过最大值，裁剪
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
            self._history_index = min(self._history_index, len(self._history) - 1)
            self.history_changed.emit()
    
    @property
    def enabled(self) -> bool:
        """是否启用历史记录"""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        """设置是否启用历史记录"""
        self._enabled = value
    
    def save_state(self, action_name: str, state_data: dict) -> None:
        """
        保存当前状态到历史记录
        
        Args:
            action_name: 操作名称（用于显示）
            state_data: 状态数据（需要包含所有需要恢复的信息）
        """
        if not self._enabled:
            return
        
        # 如果当前不在历史记录末尾，删除后面的记录
        if self._history_index < len(self._history) - 1:
            self._history = self._history[:self._history_index + 1]
        
        # 添加新的历史记录
        history_entry = {
            'action': action_name,
            'state': copy.deepcopy(state_data),  # 深拷贝状态
        }
        self._history.append(history_entry)
        
        # 如果超过最大历史记录数，删除最旧的记录
        if len(self._history) > self._max_history:
            self._history.pop(0)
        else:
            self._history_index += 1
        
        # 确保索引在有效范围内
        self._history_index = len(self._history) - 1
        
        # 发送历史记录变化信号
        self.history_changed.emit()
    
    def can_undo(self) -> bool:
        """
        是否可以撤销
        
        Returns:
            如果可以撤销返回True，否则返回False
        """
        return self._history_index > 0
    
    def can_redo(self) -> bool:
        """
        是否可以重做
        
        Returns:
            如果可以重做返回True，否则返回False
        """
        return 0 <= self._history_index < len(self._history) - 1
    
    def undo(self) -> Optional[dict]:
        """
        撤销到上一个状态
        
        Returns:
            上一个状态的数据，如果无法撤销返回None
        """
        if not self.can_undo():
            return None
        
        self._history_index -= 1
        self.history_changed.emit()
        
        return copy.deepcopy(self._history[self._history_index]['state'])
    
    def redo(self) -> Optional[dict]:
        """
        重做到下一个状态
        
        Returns:
            下一个状态的数据，如果无法重做返回None
        """
        if not self.can_redo():
            return None
        
        self._history_index += 1
        self.history_changed.emit()
        
        return copy.deepcopy(self._history[self._history_index]['state'])
    
    def get_current_state(self) -> Optional[dict]:
        """
        获取当前状态
        
        Returns:
            当前状态的数据，如果没有历史记录返回None
        """
        if 0 <= self._history_index < len(self._history):
            return copy.deepcopy(self._history[self._history_index]['state'])
        return None
    
    def clear(self) -> None:
        """清空所有历史记录"""
        self._history.clear()
        self._history_index = -1
        self.history_changed.emit()
    
    def get_history_info(self) -> List[str]:
        """
        获取历史记录信息列表
        
        Returns:
            操作名称列表
        """
        return [entry['action'] for entry in self._history]
    
    def get_current_action(self) -> Optional[str]:
        """
        获取当前操作名称
        
        Returns:
            当前操作名称，如果没有历史记录返回None
        """
        if 0 <= self._history_index < len(self._history):
            return self._history[self._history_index]['action']
        return None
    
    def get_history_count(self) -> int:
        """
        获取历史记录数量
        
        Returns:
            历史记录数量
        """
        return len(self._history)
    
    def get_current_index(self) -> int:
        """
        获取当前历史记录索引
        
        Returns:
            当前索引
        """
        return self._history_index


if __name__ == "__main__":
    # 测试代码
    history = DocumentHistory(max_history=5)
    
    # 保存一些状态
    for i in range(10):
        state = {'value': i, 'name': f'State {i}'}
        history.save_state(f"Action {i}", state)
    
    print(f"历史记录数量: {history.get_history_count()}")
    print(f"当前索引: {history.get_current_index()}")
    print(f"可以撤销: {history.can_undo()}")
    print(f"可以重做: {history.can_redo()}")
    
    # 撤销几次
    for i in range(3):
        state = history.undo()
        if state:
            print(f"撤销后状态: {state}")
    
    print(f"撤销后可以重做: {history.can_redo()}")
    
    # 重做一次
    state = history.redo()
    if state:
        print(f"重做后状态: {state}")

