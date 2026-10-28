from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QListWidget, QListWidgetItem, QCheckBox,
                           QAbstractItemView, QInputDialog, QMenu, QApplication,
                           QDialog, QDialogButtonBox, QTextEdit, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QTimer, QRect, QPoint
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QDropEvent, QPen, QBrush

from app.ui.tokens_v2 import Color
from app.ui.design_tokens import Tokens
import sys
import os
import builtins

_LAYER_PANEL_DEBUG = (
    os.environ.get("BTPW_LAYER_PANEL_DEBUG", "0") == "1"
    or os.environ.get("BTPW_UI_DEBUG", "0") == "1"
)
_LAYER_PANEL_ALWAYS_LOG_KEYWORDS = (
    "出错", "错误", "失败", "警告", "异常",
    "error", "failed", "warning", "exception", "Traceback",
)


def print(*args, **kwargs):
    if _LAYER_PANEL_DEBUG:
        builtins.print(*args, **kwargs)
        return
    try:
        message = " ".join(str(arg) for arg in args)
    except Exception:
        message = ""
    if any(keyword in message for keyword in _LAYER_PANEL_ALWAYS_LOG_KEYWORDS):
        builtins.print(*args, **kwargs)

# 注释掉冲突的导入，使用本文件中定义的类
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from app.views.layer_panel import LayerPanel, LayerItem
try:
    from app.models.shaped_layer_new import ShapedLayer
except ImportError:
    from app.models.shaped_layer_new import ShapedLayer

from app.ui.icon_manager import IconManager, create_random_button, create_lock_button, create_visibility_button
from app.ui.icon_library import icon_pixmap
from app.ui.design_spec import Scale as _Scale, IconSize as _IconSize
from app.ui.visual_hierarchy import VisualHierarchy
from app.ui.shaped_layer_panel import ShapedLayerPanel
from app.models.layer_group import LayerGroup
from app.utils.layer_tree import (
    display_entries,
    get_parent_group_id,
    is_effectively_locked,
    is_layer_group,
    set_parent_group_id,
)


class LayerItem(QWidget):
    """图层列表项组件"""

    def __init__(self, layer, index, panel=None, depth=0):
        super().__init__()
        self.layer = layer
        self.index = index
        self.depth = depth
        self.panel = panel  # 保存对LayerPanel的引用
        self.is_selected = False
        self.is_hovered = False

        # 设置初始样式
        self.setObjectName("layerItem")

        layout = QHBoxLayout(self)
        # 4px 栅格：原来 margins 5 / spacing 6 都是非栅格值。
        # 宽度上：24+24+16+label+… 加上 spacing 与边距后总宽 176 > 父宽 168，
        # 图层行会横向溢出（文字被切）。改成 4px 后省下 2(spacing×2) + 2(边距)，
        # 纵向也能容纳 24px 的图标按钮（原 18px，已提到 WCAG 的 24 下限）。
        layout.setContentsMargins(4 + depth * 16, 4, 4, 4)
        layout.setSpacing(4)

        # 可见性切换按钮 - 改为使用按钮显示眼睛图标
        self.visibility_btn = QPushButton()
        self.visibility_btn.setFixedSize(_Scale.PX[_Scale.SM], _Scale.PX[_Scale.SM])
        self.visibility_btn.setCheckable(True)
        self.visibility_btn.setChecked(bool(getattr(layer, 'visible', True)))
        self.visibility_btn.clicked.connect(self.toggle_visibility)
        self.visibility_btn.setObjectName("visibilityButton")
        self.update_visibility_icon()
        layout.addWidget(self.visibility_btn)

        # 锁定图标按钮
        self.lock_btn = QPushButton()
        self.lock_btn.setFixedSize(_Scale.PX[_Scale.SM], _Scale.PX[_Scale.SM])
        self.lock_btn.setCheckable(True)
        self.lock_btn.setChecked(bool(getattr(layer, 'locked', False)))
        self.lock_btn.setObjectName("lockButton")
        self.update_lock_icon()
        self.lock_btn.clicked.connect(self.toggle_lock)
        layout.addWidget(self.lock_btn)

        # 绑定状态图标
        self.bind_label = QLabel()
        self.bind_label.setFixedSize(_IconSize.SM, _IconSize.SM)
        self.bind_label.setObjectName("bindLabel")
        self.update_bind_icon()
        layout.addWidget(self.bind_label)

        # 图层名称
        layer_name = self._display_name()
        self.name_label = QLabel(layer_name)
        self.name_label.setObjectName("nameLabel")
        self.name_label.setMinimumHeight(16)
        # 名称用 Preferred 而不是 Expanding：
        # Expanding 会吃掉全部剩余空间，把右侧尺寸标签挤到边界，
        # 同时 stretch 又占住余量 —— 两者叠加后内层 label 只分到 65px，
        # 明明 99px 就够显示的「仅限3天 · 手慢无」被截成「仅限…慢无」。
        self.name_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.name_label.setWordWrap(False)
        self.name_label.setToolTip(layer_name)
        self.name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.name_label, 1)

        # 不再 addStretch()：名称本身就能撑开剩余空间，
        # 多加一个 stretch 只会跟名称抢宽度。

        # 图层尺寸信息
        size_text = "Group" if is_layer_group(layer) else f"{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}"
        self.size_label = QLabel(size_text)
        self.size_label.setObjectName("sizeLabel")
        self.size_label.setMinimumHeight(16)
        self.size_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # 尺寸是次要信息（281x50），窄面板下应让位给图层名。
        # 设成 Ignored：布局不会按它的 sizeHint 预留宽度，优先把空间给名称。
        self.size_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.size_label.setMinimumWidth(0)
        layout.addWidget(self.size_label, 0)

        # 应用样式并更新显示
        self.apply_style()
        self.update_labels()

        # 减少调试输出 - 只在调试模式下输出
        # print(f"创建UI图层项: 名称='{layer_name}', 尺寸='{size_text}'")

    def update_labels(self):
        """更新标签内容和样式 - 优化版本"""
        # 确保标签已创建
        if not (hasattr(self, 'name_label') and self.name_label and
                hasattr(self, 'size_label') and self.size_label):
            return

        # 获取当前显示的内容
        current_name = self.name_label.text()
        current_size = self.size_label.text()

        # 计算新的内容
        layer_name = self._display_name()
        size_text = "Group" if is_layer_group(self.layer) else f"{getattr(self.layer, 'width', 0)}x{getattr(self.layer, 'height', 0)}"

        # 只有内容实际发生变化时才更新
        content_changed = False

        if current_name != layer_name:
            self.name_label.setToolTip(layer_name)
            fm = self.name_label.fontMetrics()
            # 用标签真实可用宽度做省略，不再 `max(80, width)`。
            # 原来强制下限 80px：当面板很窄（图层面板默认 180px，扣掉图标/锁/
            # 尺寸标签后名称区只剩 ~60px）时，仍按 80px 排版，
            # 结果「仅限3天·手慢无」被截成「仅限3...手慢无」——明明还有空间。
            avail = max(24, self.name_label.width() - 2)
            elided = fm.elidedText(layer_name, Qt.ElideMiddle, avail)
            self.name_label.setText(elided)
            content_changed = True

        if current_size != size_text:
            self.size_label.setText(size_text)
            content_changed = True

        # 更新图标状态（这些通常不需要频繁更新）
        self.update_visibility_icon()
        self.update_lock_icon()
        self.update_bind_icon()

        # 只有在内容发生变化或样式需要更新时才重新应用样式
        if content_changed or self.is_selected:
            self.apply_style()

        # 减少不必要的强制重绘
        if content_changed:
            self.name_label.update()
            self.size_label.update()
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'name_label') and self.name_label:
            text = self._display_name()
            fm = self.name_label.fontMetrics()
            # 与上面保持一致：按真实可用宽度省略（下限 24px 防止宽度为 0 时出错）
            avail = max(24, self.name_label.width() - 2)
            elided = fm.elidedText(text, Qt.ElideMiddle, avail)
            self.name_label.setText(elided)

        # 减少调试输出 - 只在内容实际变化时输出
        # if content_changed:
        #     print(f"更新UI标签: 名称='{layer_name}', 尺寸='{size_text}', 选中={self.is_selected}")

    def _display_name(self):
        name = getattr(self.layer, 'name', f'图层 {self.index}')
        if is_layer_group(self.layer):
            marker = "[-]" if getattr(self.layer, 'expanded', True) else "[+]"
            return f"{marker} {name}"
        return name

    def apply_style(self):
        """应用现代化样式，使用视觉层级管理器"""
        # 获取统一的颜色和样式
        vh = VisualHierarchy

        # 基础组件样式
        style = f"""
        QWidget#layerItem {{
            background: {Color.surface_selected if self.is_selected else Color.surface_3};
            border: 1px solid {Color.accent if self.is_selected else Color.border_strong};
            border-radius: 5px;
            padding: 0px;
        }}

        /* 可见 / 锁定 两个小图标按钮。

           **不加描边**：原来每个按钮都有 1px 描边 + 圆角，一行图层里两个框
           贴在文字左边，视觉上像两个小方块占着半行位置，又乱又重。
           改成默认完全透明、只在 hover / checked 时给底色。

           也**不写 min-width/min-height**：全局 QSS 的 QPushButton 有
           `padding: 0 14px`，min 尺寸 + padding 叠加会把 setFixedSize(_IconSize.MD, _IconSize.MD)
           的按钮撑成 18x38（实测 min>max 的矛盾态），一行列表里出现竖长条。 */
        QPushButton#visibilityButton, QPushButton#lockButton {{
            background: transparent;
            border: none;
            border-radius: {vh.get_radius('sm')}px;
            color: {vh.get_color('text', 'hint')};
            font-size: 12px;
            padding: 0px;
        }}

        QPushButton#visibilityButton:hover, QPushButton#lockButton:hover {{
            background: {vh.get_color('interactive', 'hover')};
            color: {vh.get_color('text', 'primary')};
        }}

        QPushButton#visibilityButton:pressed, QPushButton#lockButton:pressed {{
            background: {vh.get_color('interactive', 'active')};
        }}

        QPushButton#visibilityButton:checked {{
            background: {vh.get_color('interactive', 'selected')};
            color: {vh.get_color('text', 'primary')};
        }}

        QLabel#bindLabel {{
            background: transparent;
            color: {vh.get_color('primary', 'light')};
            /* 图层面板里"绑定"角标。原来 10px 不在字号档位上（最小档 11），
               小到中文已经糊了（10px 中文笔画会粘连）。取 CAPTION(11)。 */
            font-size: {Tokens.FONT_SIZE_SMALL}px;
        }}
        """

        # 根据选中状态设置文字样式
        if self.is_selected:
            name_color = vh.get_color('text', 'primary')
            size_color = vh.get_color('primary', 'light')
            name_weight = 'bold'
        else:
            name_color = vh.get_color('text', 'secondary')
            size_color = vh.get_color('text', 'hint')
            name_weight = 'normal'

        style += f"""
        QLabel#nameLabel {{
            background: transparent;
            color: {name_color};
            font-family: "Microsoft YaHei UI";
            font-size: {vh.FONTS['body']['size']}px;
            font-weight: {name_weight};
            border: none;
            padding: 0px;
        }}

        QLabel#sizeLabel {{
            background: transparent;
            color: {size_color};
            font-family: "Microsoft YaHei UI";
            font-size: {vh.FONTS['small']['size']}px;
            font-weight: normal;
            border: none;
            padding: 0px;
        }}

        """

        # 应用字体（仅在标签存在时）
        if hasattr(self, 'name_label') and self.name_label:
            self.name_label.setFont(vh.get_font('body'))
        if hasattr(self, 'size_label') and self.size_label:
            self.size_label.setFont(vh.get_font('small'))

        self.setStyleSheet(style)

    def set_selected(self, selected):
        """设置选中状态"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.update_appearance()
            # 减少调试输出 - 只在状态实际变化时输出
            # print(f"UI图层 {getattr(self.layer, 'name', '未知')} 选中状态变更: {selected}")

    def update_appearance(self):
        """更新外观状态"""
        # 重新应用样式（包含文字颜色的更新）
        self.apply_style()
        # 强制更新标签显示（仅在标签存在时）
        if hasattr(self, 'name_label') and self.name_label:
            self.name_label.update()
        if hasattr(self, 'size_label') and self.size_label:
            self.size_label.update()
        # 触发重绘以更新背景
        self.update()

    def enterEvent(self, event):
        """鼠标进入事件"""
        self.is_hovered = True
        # 触发重绘以显示悬浮效果
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开事件"""
        self.is_hovered = False
        # 触发重绘以移除悬浮效果
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        """重写绘制事件，手动绘制选中和悬浮背景"""
        # 获取组件矩形
        rect = self.rect()

        # 如果有背景需要绘制，先绘制背景
        if self.is_selected or self.is_hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            vh = VisualHierarchy

            if self.is_selected:
                # 选中状态：使用视觉层级的选中色
                background_color = QColor(vh.get_color('interactive', 'selected'))
                border_color = QColor(vh.get_color('border', 'focus'))
            else:  # is_hovered
                # 悬浮状态：使用视觉层级的悬浮色
                background_color = QColor(vh.get_color('interactive', 'hover'))
                border_color = QColor(vh.get_color('border', 'primary'))

            # 绘制圆角背景
            painter.setBrush(QBrush(background_color))
            painter.setPen(QPen(border_color, 1))
            painter.drawRoundedRect(
                rect.adjusted(vh.get_spacing('xs'), vh.get_spacing('xs'),
                             -vh.get_spacing('xs'), -vh.get_spacing('xs')),
                vh.get_radius('sm'), vh.get_radius('sm')
            )

            painter.end()

        # 调用基类的paintEvent以正常绘制所有子控件
        super().paintEvent(event)

    def toggle_visibility(self, checked):
        """切换图层可见性"""
        # 打印调试信息
        print(f"【调试】切换图层可见性: {self.layer.name}, 从 {self.layer.visible} 到 {checked}")

        # 保存当前状态
        if self.panel and hasattr(self.panel, 'document'):
            self.panel.document.save_state("切换图层可见性前")

            # 更新图层可见性
            self.layer.visible = checked

            # 更新可见性图标
            self.update_visibility_icon()

            # 直接通知文档已更改，确保画布重绘
            self.panel.document.document_changed.emit()
            print(f"【调试】已发送document_changed信号")

            # 如果有主窗口的画布引用，强制更新
            from app.main_window import MainWindow
            for widget in self.window().findChildren(QWidget):
                if isinstance(widget, MainWindow):
                    print(f"【调试】找到主窗口，尝试强制更新画布")
                    if hasattr(widget, 'canvas'):
                        widget.canvas.update()
                        print(f"【调试】已强制更新画布")

            # 保存更改后的状态
            self.panel.document.save_state("切换图层可见性")

    def toggle_lock(self):
        """切换图层锁定状态"""
        # 保存当前状态
        if self.panel and self.panel.document:
            self.panel.document.save_state("切换图层锁定状态前")

        # 更新图层锁定状态
        self.layer.locked = not self.layer.locked

        # 立即更新图标显示
        self.update_lock_icon()

        # 发送文档更改信号
        if self.panel and self.panel.document:
            self.panel.document.document_changed.emit()
            # 保存更改后的状态
            self.panel.document.save_state("切换图层锁定状态")

    def update_lock_icon(self):
        """更新锁定图标"""
        if self.layer.locked:
            # 锁定状态：使用图标管理器
            IconManager.apply_icon_to_button(self.lock_btn, 'lock', 'warning')
            self.lock_btn.setToolTip("图层已锁定 - 点击解锁")
        else:
            # 未锁定状态：使用图标管理器
            IconManager.apply_icon_to_button(self.lock_btn, 'unlock', 'secondary')
            self.lock_btn.setToolTip("图层未锁定 - 点击锁定")

        # 重新应用样式并触发重绘
        self.apply_style()
        self.update()

    def update_visibility_icon(self):
        """更新可见性图标"""
        if self.layer.visible:
            # 可见状态：使用图标管理器
            IconManager.apply_icon_to_button(self.visibility_btn, 'visible', 'primary')
            self.visibility_btn.setToolTip("图层可见 - 点击隐藏")
        else:
            # 隐藏状态：使用图标管理器
            IconManager.apply_icon_to_button(self.visibility_btn, 'hidden', 'secondary')
            self.visibility_btn.setToolTip("图层隐藏 - 点击显示")

        # 重新应用样式并触发重绘
        self.apply_style()
        self.update()

    def update_bind_icon(self):
        """更新绑定状态图标"""
        # 直接使用panel的document引用，避免遍历父组件
        document = self.panel.document if self.panel else None

        if not document or not hasattr(document, 'binding_manager'):
            # 隐藏绑定图标
            self.bind_label.setText("")
            self.bind_label.setStyleSheet("")
            self.bind_label.setToolTip("")
            return

        try:
            binding_info = document.binding_manager.get_layer_binding_info(self.layer)
            if binding_info:
                group_id, group_name = binding_info
                # 显示绑定图标（真实 Lucide SVG 位图，不再用字符 ∞）
                self.bind_label.setPixmap(icon_pixmap('link', 11, Color.accent))
                self.bind_label.setAlignment(Qt.AlignCenter)
                self.bind_label.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Color.accent_subtle};
                        border: 1px solid {Color.accent};
                        border-radius: 2px;
                    }}
                """)
                tooltip = f"图层已绑定\\n绑定组: {group_name}"
                self.bind_label.setToolTip(tooltip)
            else:
                # 隐藏绑定图标
                self.bind_label.clear()
                self.bind_label.setStyleSheet("")
                self.bind_label.setToolTip("")
        except Exception as e:
            print(f"更新绑定图标时出错: {e}")
            # 出错时隐藏图标
            self.bind_label.clear()
            self.bind_label.setStyleSheet("")
            self.bind_label.setToolTip("")


