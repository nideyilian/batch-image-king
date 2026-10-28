"""批图王图标库 —— 统一图标真源（Lucide SVG）。

═══════════════════════════════════════════════════════════════════════════
真源约定（2026-10-28 定稿）
═══════════════════════════════════════════════════════════════════════════

**唯一真源 = `app/qml/icons/*.svg`**，来自 `lucide-static v1.28.0`（ISC 许可）。

- 全部 24×24 视图、`stroke-width="2"`、圆角端点，几何规范完全一致
- 98 个图标，覆盖本项目的全部语义需求
- QWidget 与 QML 共用同一批文件 —— 一个图标只有一份定义

渲染链路：

    SVG 文件 → 把 currentColor 替换成目标色 → QSvgRenderer → QPixmap → QIcon

为什么不直接用 `QIcon("xxx.svg")`：SVG 里写的是 `currentColor`，Qt 不知道
"current" 是什么颜色，会渲染成黑色（近黑背景上完全看不见）。必须先把
`currentColor` 物理替换成具体色值再交给渲染器。这是本模块存在的第一原因。

═══════════════════════════════════════════════════════════════════════════
被替换掉的旧方案
═══════════════════════════════════════════════════════════════════════════

2026-10-28 之前 `icon_manager.py` 里内嵌了 51 个手写 path + 42 个字符图标
（⚀ ∞ ⧄ ✎ 💾 📁），造成：

- `delete` 是实心垃圾桶、其余是线条 → 视觉重量不一致
- `refresh` / `undo` / `redo` / `random` 用字体字符，与 SVG 笔画完全不同
- 描边宽度在 1.5 ~ 2.5 之间跳
- 字符图标依赖系统字体，换台机器就可能变豆腐块

现在全部收敛到 Lucide：字符图标不再参与渲染，`icon_manager.py` 退化为
兼容层（保留旧 API 供 64 个既有调用点使用，内部转调本模块）。

═══════════════════════════════════════════════════════════════════════════
怎么用
═══════════════════════════════════════════════════════════════════════════

    from app.ui.icon_library import icon, icon_pixmap, icon_button, IconName
    from app.ui.design_spec import IconSize

    btn.setIcon(icon("delete"))                    # 业务名/语义常量，都认
    btn.setIcon(icon(IconName.DELETE, color=Color.accent))
    btn.setIconSize(QSize(IconSize.MD, IconSize.MD))

    ib = icon_button("zoom_in", size="md", tooltip="放大")   # tooltip 必填

命名原则：用**功能语义**（save / delete），不用形状（floppy / trash）。
换图标集时只改 `IconName` 这张表，业务代码不动 —— 别名表保证旧名继续可用。
"""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton

from app.ui.design_spec import IconSize, Scale
from app.ui.tokens_v2 import Color

logger = logging.getLogger(__name__)

# ── SVG 图标目录（唯一真源）───────────────────────────────────────────

#: SVG 目录。相对本文件定位，打包后也能找到。
#:
#: 打包路径推演（PyInstaller onefile）：
#:   `批图王.spec` 的 datas 里有 ('app/qml/icons', 'app/qml/icons')，
#:   运行时被解压到 _MEIPASS/app/qml/icons；而本模块的 __file__
#:   是 _MEIPASS/app/ui/icon_library.py，向上取 ../qml/icons 正好命中。
#: 万一以后 spec 改了导致对不上，_resolve_icon_dir() 还会回退到 exe 同级目录，
#: 并把实际用到的路径记进日志 —— 否则打包版会出现「所有图标消失」且无任何报错。
def _resolve_icon_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.normpath(os.path.join(here, "..", "qml", "icons"))]

    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            candidates.append(os.path.normpath(os.path.join(bundle, "app", "qml", "icons")))
        candidates.append(os.path.normpath(
            os.path.join(os.path.dirname(sys.executable), "app", "qml", "icons")
        ))

    for path in candidates:
        if os.path.isdir(path):
            return path

    logger.warning("图标目录均不存在，使用首个候选路径: %s", candidates[0])
    return candidates[0]


ICON_DIR = _resolve_icon_dir()

#: 兜底图标（图标名拼错或文件缺失时使用，保证界面不出现空白按钮）。
FALLBACK_ICON = "circle-help"


def _scan_available() -> set[str]:
    """扫描磁盘上真实存在的图标名。"""
    try:
        return {
            name[:-4]
            for name in os.listdir(ICON_DIR)
            if name.endswith(".svg")
        }
    except OSError:
        logger.warning("图标目录不可读: %s", ICON_DIR)
        return set()


#: 真实存在的图标名集合，导入时扫描一次。
AVAILABLE = _scan_available()


class IconName:
    """语义化图标名。值即 Lucide 的图标名（不含 .svg 后缀）。

    命名原则：用**功能语义**（save / delete），不用形状（floppy / trash）。
    换图标集时只需改这张表，业务代码不动。
    """

    # 图层与可见性
    LAYER = "layers-3"
    LAYER_GROUP = "group"
    VISIBLE = "eye"
    HIDDEN = "eye-off"
    LOCK = "lock-keyhole"
    UNLOCK = "unlock-keyhole"

    # 基础操作
    ADD = "plus"
    REMOVE = "minus"
    DELETE = "trash-2"
    EDIT = "pencil"
    COPY = "copy"
    PASTE = "clipboard-paste"
    CUT = "scissors"

    # 文件
    NEW = "file-plus-2"
    OPEN = "folder-open"
    SAVE = "save"
    IMPORT = "download"
    EXPORT = "upload"

    # 编辑历史
    UNDO = "undo-2"
    REDO = "redo-2"
    REFRESH = "refresh-cw"

    # 方向
    UP = "chevron-up"
    DOWN = "chevron-down"
    LEFT = "arrow-left"
    RIGHT = "arrow-right"
    EXPAND = "maximize-2"
    COLLAPSE = "minimize-2"

    # 视图
    ZOOM_IN = "zoom-in"
    ZOOM_OUT = "zoom-out"
    FIT = "square-dashed"
    SORT = "arrow-up-down"
    FILTER = "filter"

    # 内容类型
    TEXT = "type"
    IMAGE = "image"
    SHAPE = "shapes"
    ALIGN = "align-start-vertical"
    RANDOM = "shuffle"
    LINK = "link-2"
    UNLINK = "unlink-2"

    # 批量与预设
    BATCH_EXPORT = "folder-output"
    MULTI_EXPORT = "app-window"
    PRESET = "bookmark"
    AI = "sparkles"

    # 系统
    SETTINGS = "settings-2"
    TOOLS = "wrench"
    HELP = "circle-help"
    ABOUT = "info"

    # 状态
    SUCCESS = "circle-check"
    ERROR = "circle-x"
    WARNING = "triangle-alert"
    INFO = "info"


#: 旧业务名 → 图标名。旧代码传 "delete"、"zoom_in" 也能拿到正确图标。
#: 这张表覆盖 icon_manager 时代全部 52 个名字，迁移零改动。
_ALIAS = {
    "add": IconName.ADD,
    "ai": IconName.AI,
    "align": IconName.ALIGN,
    "about": IconName.ABOUT,
    "batch_export": IconName.BATCH_EXPORT,
    # 旧 icon_manager 里 blend / opacity 没有对应图标（返回 '?'），
    # 这里补上语义最接近的，修掉这个历史 bug。
    "blend": "layers-3",
    "collapse": IconName.COLLAPSE,
    "copy": IconName.COPY,
    "cut": IconName.CUT,
    "delete": IconName.DELETE,
    "down": IconName.DOWN,
    "edit": IconName.EDIT,
    "error": IconName.ERROR,
    "expand": IconName.EXPAND,
    "export": IconName.EXPORT,
    "file": "file-text",
    "filter": IconName.FILTER,
    "fit": IconName.FIT,
    "folder": "folder",
    "help": IconName.HELP,
    "hidden": IconName.HIDDEN,
    "image": IconName.IMAGE,
    "import": IconName.IMPORT,
    "info": IconName.INFO,
    "layer": IconName.LAYER,
    "left": IconName.LEFT,
    "link": IconName.LINK,
    "lock": IconName.LOCK,
    "multi_export": IconName.MULTI_EXPORT,
    "new": IconName.NEW,
    "opacity": "circle-dot",
    "open": IconName.OPEN,
    "paste": IconName.PASTE,
    "preset": IconName.PRESET,
    "random": IconName.RANDOM,
    "redo": IconName.REDO,
    "refresh": IconName.REFRESH,
    "remove": IconName.REMOVE,
    "right": IconName.RIGHT,
    "save": IconName.SAVE,
    "settings": IconName.SETTINGS,
    "shape": IconName.SHAPE,
    "sort": IconName.SORT,
    "success": IconName.SUCCESS,
    "text": IconName.TEXT,
    "tools": IconName.TOOLS,
    "undo": IconName.UNDO,
    "unlink": IconName.UNLINK,
    "unlock": IconName.UNLOCK,
    "up": IconName.UP,
    "visible": IconName.VISIBLE,
    "warning": IconName.WARNING,
    "zoom_in": IconName.ZOOM_IN,
    "zoom_out": IconName.ZOOM_OUT,
}

#: IconName 属性名 → 值，用于容忍 `icon("DELETE")` 这种传法。
_ICON_NAME_MAP = {
    key: value
    for key, value in vars(IconName).items()
    if key.isupper() and isinstance(value, str)
}


def resolve(name: str) -> str:
    """把业务名解析成真实的 Lucide 图标名。

    支持四种传法：
        icon("delete")             → 走别名表 → trash-2
        icon(IconName.DELETE)      → 值已是 Lucide 名，原样用
        icon("DELETE")             → IconName 的属性名，也能识别
        icon("layers-3")           → 直接给 Lucide 名，原样用
    """
    if not name:
        return FALLBACK_ICON
    text = str(name)
    # 显式带前缀的旧写法（如 "mdi6.rocket"）取最后一段
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    mapped = _ALIAS.get(text)
    if mapped:
        return mapped
    upper = text.upper()
    if upper in _ICON_NAME_MAP:
        return _ICON_NAME_MAP[upper]
    return text


# ── 渲染 ──────────────────────────────────────────────────────────────

#: (图标名, 颜色, 尺寸, dpr) → QIcon。缓存避免重复解析 SVG。
_CACHE: dict[tuple, QIcon] = {}

#: SVG 文本缓存，避免每次渲染都读盘。
_SVG_TEXT: dict[str, str | None] = {}


def _dpr() -> float:
    """当前屏幕的像素比，保证高分屏不虚。"""
    try:
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        return float(screen.devicePixelRatio()) if screen else 1.0
    except Exception:
        return 1.0


def _svg_text(name: str) -> str | None:
    """读取并缓存 SVG 原文。"""
    if name in _SVG_TEXT:
        return _SVG_TEXT[name]
    path = os.path.join(ICON_DIR, f"{name}.svg")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        logger.warning("图标文件不存在: %s", path)
        text = None
    _SVG_TEXT[name] = text
    return text


def _tinted_svg(name: str, color: str) -> bytes | None:
    """把 SVG 里的 currentColor 换成具体色值。

    Qt 不认识 CSS 的 currentColor，不替换会渲染成纯黑（暗色界面上不可见）。
    """
    text = _svg_text(name)
    if text is None:
        return None
    return text.replace("currentColor", color).encode("utf-8")


def _render_pixmap(name: str, size: int, color: str, dpr: float) -> QPixmap:
    """把图标渲染成指定尺寸的位图（按 dpr 放大，避免高分屏模糊）。"""
    from PySide6.QtSvg import QSvgRenderer

    px = QPixmap(int(round(size * dpr)), int(round(size * dpr)))
    px.fill(Qt.transparent)

    data = _tinted_svg(name, color)
    if data is None:
        return px

    renderer = QSvgRenderer(data)
    if not renderer.isValid():
        logger.warning("图标 SVG 解析失败: %s", name)
        return px

    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    px.setDevicePixelRatio(dpr)
    return px


def icon(
    name: str,
    color: str | None = None,
    size: int | None = None,
    active: str | None = None,
    color_active: str | None = None,
) -> QIcon:
    """返回统一风格的 Lucide 图标。

    Args:
        name: 业务名（"delete"）或 Lucide 名（IconName.DELETE）。
        color: 十六进制色值。默认 `Color.text_secondary`。
        size: 位图像素尺寸，仅影响清晰度；实际显示尺寸由 setIconSize 决定。
        active: 选中态图标名（可选）。
        color_active: 选中态颜色（可选）。

    Returns:
        QIcon。图标名不存在时自动退到问号图标，不会返回空图标。
    """
    color = color or Color.text_secondary
    size = int(size or IconSize.MD)
    resolved = resolve(name)
    if resolved not in AVAILABLE:
        logger.warning("图标不存在，降级为 %s: %s", FALLBACK_ICON, resolved)
        resolved = FALLBACK_ICON

    key = (resolved, color, size, round(_dpr(), 2))
    if key not in _CACHE:
        _CACHE[key] = QIcon(_render_pixmap(resolved, size, color, _dpr()))

    result = _CACHE[key]
    if active is not None:
        # 选中态：把另一张位图塞进同一个 QIcon，由控件 checked 状态选用
        active_name = resolve(active)
        if active_name in AVAILABLE:
            active_color = color_active or color
            active_key = (active_name, active_color, size, round(_dpr(), 2))
            if active_key not in _CACHE:
                _CACHE[active_key] = QIcon(
                    _render_pixmap(active_name, size, active_color, _dpr())
                )
            result = QIcon(result)
            result.addPixmap(
                _CACHE[active_key].pixmap(QSize(size, size)), QIcon.Normal, QIcon.On
            )
    return result


def icon_pixmap(name: str, size: int = IconSize.MD, color: str | None = None) -> QPixmap:
    """直接拿 QPixmap（用于自绘场景，如 QLabel.setPixmap）。"""
    resolved = resolve(name)
    if resolved not in AVAILABLE:
        resolved = FALLBACK_ICON
    return _render_pixmap(resolved, int(size), color or Color.text_secondary, _dpr())


def icon_button(
    name: str,
    size: str = Scale.MD,
    tooltip: str = "",
    variant: str = "ghost",
    color: str | None = None,
    checkable: bool = False,
    parent=None,
) -> QPushButton:
    """创建图标按钮，尺寸严格来自 design_spec。

    Args:
        name: 图标名。
        size: design_spec.Scale 档位（sm / md / lg），决定按钮边长。
        tooltip: 必须给 —— 纯图标按钮没有文字，tooltip 是无障碍的最低要求。
        variant: 按钮变体，默认 ghost（透明底，hover 才出底色）。
        color: 图标颜色。
        checkable: 是否可切换（如"显示/隐藏"）。
    """
    btn = QPushButton(parent)
    btn.setProperty("variant", variant)
    btn.setProperty("uiSize", "icon")
    btn.setCursor(Qt.PointingHandCursor)
    btn.setIcon(icon(name, color=color))

    edge = Scale.PX.get(size, Scale.PX[Scale.MD])
    icon_edge = IconSize.SM if edge <= Scale.PX[Scale.SM] else IconSize.MD
    btn.setFixedSize(edge, edge)
    btn.setIconSize(QSize(icon_edge, icon_edge))

    if checkable:
        btn.setCheckable(True)
    if tooltip:
        btn.setToolTip(tooltip)
        btn.setAccessibleName(tooltip)
    return btn


def clear_cache() -> None:
    """清空图标缓存（主题切换后调用，避免旧色位图残留）。"""
    _CACHE.clear()
    _SVG_TEXT.clear()


__all__ = [
    "icon",
    "icon_pixmap",
    "icon_button",
    "resolve",
    "clear_cache",
    "IconName",
    "ICON_DIR",
    "AVAILABLE",
    "FALLBACK_ICON",
]
