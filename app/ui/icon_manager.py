# -*- coding: utf-8 -*-
"""
图标管理器 - 统一管理应用程序中的所有图标
提供一致的图标系统，避免混用emoji和字符符号
"""

from PySide6.QtWidgets import QPushButton, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap, QColor, QPen


class IconManager:
    """统一图标管理器"""

    # 图标字体设置
    ICON_FONT_FAMILY = "Segoe UI Symbol"  # Windows通用符号字体
    ICON_FONT_SIZE = 12

    # 图标颜色主题
    COLORS = {
        'primary': '#2196F3',      # 主要蓝色
        'secondary': '#757575',    # 次要灰色
        'success': '#4CAF50',      # 成功绿色
        'warning': '#FF9800',      # 警告橙色
        'danger': '#F44336',       # 危险红色
        'disabled': '#BDBDBD',     # 禁用灰色
        'text': '#212121',         # 文本黑色
        'background': '#FAFAFA'    # 背景灰色
    }

    # 图标映射表 - 使用跨平台兼容的Unicode符号
    ICONS = {
        # 基础操作图标
        'random': '⚀',           # 骰子 -> 随机
        'link': '∞',             # 链接 -> 绑定 (使用无穷符号)
        'unlink': '⧄',           # 断开链接
        'lock': '🔒',            # 锁定 (保留emoji，兼容性好)
        'unlock': '🔓',          # 解锁 (保留emoji，兼容性好)
        'visible': '●',          # 可见 (实心圆)
        'hidden': '○',           # 隐藏 (空心圆)
        'warning': '⚠',          # 警告
        'info': 'ℹ',             # 信息
        'success': '✓',          # 成功
        'error': '✗',            # 错误

        # 编辑操作图标
        'add': '+',              # 添加
        'remove': '−',           # 删除
        'edit': '✎',             # 编辑
        'copy': '⧉',             # 复制
        'paste': '⧈',            # 粘贴
        'cut': '✂',              # 剪切
        'undo': '↶',             # 撤销
        'redo': '↷',             # 重做

        # 导航和视图图标
        'up': '▲',               # 向上
        'down': '▼',             # 向下
        'left': '◀',             # 向左
        'right': '▶',            # 向右
        'expand': '⊞',           # 展开
        'collapse': '⊟',         # 折叠
        'zoom_in': '⊕',          # 放大
        'zoom_out': '⊖',         # 缩小
        'fit': '⊡',              # 适应

        # 文件操作图标
        'folder': '📁',          # 文件夹 (保留emoji，识别度高)
        'file': '📄',            # 文件 (保留emoji，识别度高)
        'save': '💾',            # 保存 (保留emoji，识别度高)
        'open': '📂',            # 打开 (保留emoji，识别度高)
        'new': '📄',             # 新建
        'import': '⬇',           # 导入 (下载符号)
        'export': '⬆',           # 导出 (上传符号)

        # 设置和工具图标
        'settings': '⚙',         # 设置
        'tools': '🔧',           # 工具 (保留emoji，识别度高)
        'filter': '⧩',           # 筛选
        'sort': '⇅',             # 排序
        'refresh': '↻',          # 刷新
        'help': '❓',            # 帮助 (保留emoji，识别度高)
        'about': 'ℹ',            # 关于
    }

    @classmethod
    def get_icon_text(cls, icon_name):
        """获取图标文本"""
        return cls.ICONS.get(icon_name, '?')

    @classmethod
    def get_color(cls, color_name):
        """获取颜色值"""
        return cls.COLORS.get(color_name, cls.COLORS['text'])

    @classmethod
    def create_icon_button(cls, icon_name, size=18, color='primary', tooltip=None):
        """
        创建图标按钮

        Args:
            icon_name: 图标名称
            size: 按钮尺寸
            color: 图标颜色主题
            tooltip: 工具提示

        Returns:
            QPushButton: 配置好的图标按钮
        """
        button = QPushButton()
        button.setFixedSize(size, size)

        # 设置图标文本
        icon_text = cls.get_icon_text(icon_name)
        button.setText(icon_text)

        # 设置字体
        font = QFont(cls.ICON_FONT_FAMILY, cls.ICON_FONT_SIZE)
        button.setFont(font)

        # 设置样式
        color_value = cls.get_color(color)
        button.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {color_value};
                font-family: '{cls.ICON_FONT_FAMILY}';
                font-size: {cls.ICON_FONT_SIZE}px;
                font-weight: normal;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background: rgba(33, 150, 243, 0.1);
                border-radius: {size//4}px;
            }}
            QPushButton:pressed {{
                background: rgba(33, 150, 243, 0.2);
            }}
            QPushButton:disabled {{
                color: {cls.get_color('disabled')};
            }}
        """)

        # 设置工具提示
        if tooltip:
            button.setToolTip(tooltip)

        return button

    @classmethod
    def create_checkable_icon_button(cls, icon_name_checked, icon_name_unchecked=None,
                                   size=18, color='primary', tooltip_checked=None, tooltip_unchecked=None):
        """
        创建可切换的图标按钮

        Args:
            icon_name_checked: 选中状态的图标名称
            icon_name_unchecked: 未选中状态的图标名称
            size: 按钮尺寸
            color: 图标颜色主题
            tooltip_checked: 选中状态的工具提示
            tooltip_unchecked: 未选中状态的工具提示

        Returns:
            QPushButton: 配置好的可切换图标按钮
        """
        if icon_name_unchecked is None:
            icon_name_unchecked = icon_name_checked

        button = QPushButton()
        button.setFixedSize(size, size)
        button.setCheckable(True)

        # 设置字体
        font = QFont(cls.ICON_FONT_FAMILY, cls.ICON_FONT_SIZE)
        button.setFont(font)

        # 获取图标文本
        icon_checked = cls.get_icon_text(icon_name_checked)
        icon_unchecked = cls.get_icon_text(icon_name_unchecked)

        # 设置样式
        color_value = cls.get_color(color)
        button.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {cls.get_color('secondary')};
                font-family: '{cls.ICON_FONT_FAMILY}';
                font-size: {cls.ICON_FONT_SIZE}px;
                font-weight: normal;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                background: rgba(33, 150, 243, 0.1);
                border-radius: {size//4}px;
            }}
            QPushButton:pressed {{
                background: rgba(33, 150, 243, 0.2);
            }}
            QPushButton:checked {{
                color: {color_value};
            }}
            QPushButton:disabled {{
                color: {cls.get_color('disabled')};
            }}
        """)

        # 存储图标信息
        button.icon_checked = icon_checked
        button.icon_unchecked = icon_unchecked
        button.tooltip_checked = tooltip_checked
        button.tooltip_unchecked = tooltip_unchecked

        # 连接状态变化信号
        button.toggled.connect(lambda checked: cls._update_checkable_button(button, checked))

        # 初始化状态
        cls._update_checkable_button(button, button.isChecked())

        return button

    @classmethod
    def _update_checkable_button(cls, button, checked):
        """更新可切换按钮的状态"""
        if checked:
            button.setText(button.icon_checked)
            if button.tooltip_checked:
                button.setToolTip(button.tooltip_checked)
        else:
            button.setText(button.icon_unchecked)
            if button.tooltip_unchecked:
                button.setToolTip(button.tooltip_unchecked)

    @classmethod
    def create_icon_label(cls, icon_name, size=16, color='text'):
        """
        创建图标标签

        Args:
            icon_name: 图标名称
            size: 字体大小
            color: 图标颜色主题

        Returns:
            QLabel: 配置好的图标标签
        """
        label = QLabel()

        # 设置图标文本
        icon_text = cls.get_icon_text(icon_name)
        label.setText(icon_text)

        # 设置字体
        font = QFont(cls.ICON_FONT_FAMILY, size)
        label.setFont(font)

        # 设置样式
        color_value = cls.get_color(color)
        label.setStyleSheet(f"""
            QLabel {{
                color: {color_value};
                font-family: '{cls.ICON_FONT_FAMILY}';
                font-size: {size}px;
                font-weight: normal;
            }}
        """)

        return label

    @classmethod
    def apply_icon_to_button(cls, button, icon_name, color='primary'):
        """
        为现有按钮应用图标

        Args:
            button: QPushButton实例
            icon_name: 图标名称
            color: 图标颜色主题
        """
        icon_text = cls.get_icon_text(icon_name)
        button.setText(icon_text)

        # 设置字体
        font = QFont(cls.ICON_FONT_FAMILY, cls.ICON_FONT_SIZE)
        button.setFont(font)

        # 更新样式中的颜色
        color_value = cls.get_color(color)
        current_style = button.styleSheet()

        # 简单的颜色替换 - 如果需要更复杂的样式，可以重写整个样式表
        if 'color:' in current_style:
            import re
            new_style = re.sub(r'color:\s*[^;]+;', f'color: {color_value};', current_style)
            button.setStyleSheet(new_style)


# 便捷函数
def create_random_button(size=18):
    """创建随机按钮"""
    return IconManager.create_icon_button('random', size, 'primary', '随机化')

def create_link_button(size=18):
    """创建链接按钮"""
    return IconManager.create_checkable_icon_button('link', 'unlink', size, 'primary',
                                                   '已链接 - 点击解除', '未链接 - 点击链接')

def create_lock_button(size=18):
    """创建锁定按钮"""
    return IconManager.create_checkable_icon_button('lock', 'unlock', size, 'warning',
                                                   '已锁定 - 点击解锁', '未锁定 - 点击锁定')

def create_visibility_button(size=18):
    """创建可见性按钮"""
    return IconManager.create_checkable_icon_button('visible', 'hidden', size, 'primary',
                                                   '可见 - 点击隐藏', '隐藏 - 点击显示') 