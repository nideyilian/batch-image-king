"""
统一快捷键契约 (Shortcut Contract)
===================================

集中维护 Photoshop 风格的快捷键映射，供 QML 界面、经典 PySide6 界面、
画布事件处理器和自动化契约测试共享同一数据源，避免两端各自维护
导致冲突或漂移。

三层职责
--------
1. FILE_HISTORY   文件 / 历史（遵循通用文档习惯）
2. LAYER          图层编辑（复制 / 合并 / 编组 / 变换 / 前后移动等）
3. TOOL           工具切换（V=移动 H=抓手 Z=缩放 T=文字 …）
4. VIEW           视图（标尺 / 参考线 / 缩放）
5. APP_EXCLUSIVE  批图王专属功能（刻意避开 Photoshop 核心键位）
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Tuple


class ShortcutLayer(str, Enum):
    """快捷键分层标签，对应 Photoshop 三大分组 + 应用专属。"""
    FILE_HISTORY = "file_history"
    LAYER = "layer"
    TOOL = "tool"
    VIEW = "view"
    APP_EXCLUSIVE = "app_exclusive"


class ShortcutScope(str, Enum):
    """按键作用域，用于 enabled 判断。"""
    ALWAYS = "always"
    HAS_DOCUMENT = "has_document"
    LAYER_ENABLED = "layer_enabled"
    TEXT_NOT_EDITING = "text_not_editing"
    HAS_SELECTED_LAYER = "has_selected_layer"
    VECTOR_NODE_EDITING = "vector_node_editing"


class ShortcutEntry(object):
    """一条快捷键映射条目（普通对象版本，避免 dataclass+Enum 在旧环境的兼容问题）。"""

    __slots__ = ("action_id", "label", "sequence", "layer", "scope",
                 "replaces_old_sequence", "notes")

    def __init__(
        self,
        action_id: str,
        label: str,
        sequence: str,
        layer: ShortcutLayer,
        scope: ShortcutScope,
        replaces_old_sequence: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        self.action_id = action_id
        self.label = label
        self.sequence = sequence
        self.layer = layer
        self.scope = scope
        self.replaces_old_sequence = replaces_old_sequence
        self.notes = notes

    @property
    def is_photoshop_core(self) -> bool:
        return self.layer in (
            ShortcutLayer.FILE_HISTORY,
            ShortcutLayer.LAYER,
            ShortcutLayer.TOOL,
            ShortcutLayer.VIEW,
        )

    def __repr__(self) -> str:
        return (
            f"ShortcutEntry(action_id={self.action_id!r}, seq={self.sequence!r}, "
            f"layer={self.layer.value}, scope={self.scope.value})"
        )


def _E(action_id, label, sequence, layer, scope, old=None, notes=None):
    """构造辅助函数，保持字面简洁。"""
    return ShortcutEntry(action_id, label, sequence, layer, scope, old, notes)


# ---------------------------------------------------------------------------
# 1) 文件 / 历史
# ---------------------------------------------------------------------------
PS_FILE_HISTORY: Dict[str, ShortcutEntry] = {
    "NEW":           _E("file.new",           "新建文档",        "Ctrl+N",          ShortcutLayer.FILE_HISTORY, ShortcutScope.ALWAYS),
    "OPEN":          _E("file.open",          "打开项目",        "Ctrl+O",          ShortcutLayer.FILE_HISTORY, ShortcutScope.ALWAYS),
    "SAVE":          _E("file.save",          "保存",            "Ctrl+S",          ShortcutLayer.FILE_HISTORY, ShortcutScope.HAS_DOCUMENT),
    "SAVE_AS":       _E("file.save_as",       "另存为",          "Ctrl+Shift+S",    ShortcutLayer.FILE_HISTORY, ShortcutScope.HAS_DOCUMENT),
    "CLOSE_TAB":     _E("file.close_tab",     "关闭当前标签",    "Ctrl+W",          ShortcutLayer.FILE_HISTORY, ShortcutScope.HAS_DOCUMENT),
    "PRINT":         _E("file.print",         "打印(预留)",      "Ctrl+P",          ShortcutLayer.FILE_HISTORY, ShortcutScope.HAS_DOCUMENT,
                                                      notes="应用暂未实现打印；Ctrl+P 必须留给 PS 语义，禁止用于预设中心"),
    "UNDO":          _E("edit.undo",          "撤销",            "Ctrl+Z",          ShortcutLayer.FILE_HISTORY, ShortcutScope.HAS_DOCUMENT),
    "REDO":          _E("edit.redo",          "重做",            "Ctrl+Shift+Z",    ShortcutLayer.FILE_HISTORY, ShortcutScope.HAS_DOCUMENT,
                                                      notes="PS 标准；Ctrl+Y 保留为兼容别名"),
    "REDO_ALIAS":    _E("edit.redo_alias",    "重做(兼容)",      "Ctrl+Y",          ShortcutLayer.FILE_HISTORY, ShortcutScope.HAS_DOCUMENT),
    "STEP_BACKWARD": _E("edit.step_backward", "后退一步(历史)",  "Ctrl+Alt+Z",      ShortcutLayer.FILE_HISTORY, ShortcutScope.HAS_DOCUMENT),
}

# ---------------------------------------------------------------------------
# 2) 图层编辑（PS 核心语义区 —— 应用专属严禁抢占）
# ---------------------------------------------------------------------------
PS_LAYER: Dict[str, ShortcutEntry] = {
    "COPY":                  _E("layer.copy",                   "复制图层",                 "Ctrl+C",        ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "PASTE":                 _E("layer.paste",                  "粘贴图层",                 "Ctrl+V",        ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "COPY_STYLE":            _E("layer.copy_style",             "复制图层样式",             "Ctrl+Shift+C",  ShortcutLayer.LAYER, ShortcutScope.HAS_SELECTED_LAYER),
    "PASTE_STYLE":           _E("layer.paste_style",            "粘贴图层样式",             "Ctrl+Shift+V",  ShortcutLayer.LAYER, ShortcutScope.HAS_SELECTED_LAYER),
    "DUPLICATE_LAYER":       _E("layer.duplicate",              "复制选中图层(到新图层)",    "Ctrl+J",        ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED,
                                                                                          old="Ctrl+D(原:复制标签页)"),
    "DELETE":                _E("layer.delete",                 "删除选中图层",             "Delete",        ShortcutLayer.LAYER, ShortcutScope.HAS_SELECTED_LAYER),
    "SELECT_ALL":            _E("layer.select_all",             "全选图层",                 "Ctrl+A",        ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "RENAME":                _E("layer.rename",                 "重命名图层",               "F2",            ShortcutLayer.LAYER, ShortcutScope.HAS_SELECTED_LAYER),

    "FREE_TRANSFORM":        _E("layer.free_transform",         "自由变换",                 "Ctrl+T",        ShortcutLayer.LAYER, ShortcutScope.HAS_SELECTED_LAYER,
                                                                                          old="Ctrl+T(原:新建文字层→Shift+F8)"),
    "MERGE_DOWN":            _E("layer.merge_down",             "向下合并图层",             "Ctrl+E",        ShortcutLayer.LAYER, ShortcutScope.HAS_SELECTED_LAYER,
                                                                                          old="Ctrl+E(原:导出→Ctrl+Shift+X)"),
    "GROUP_LAYERS":          _E("layer.group",                  "图层编组",                 "Ctrl+G",        ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "UNGROUP_LAYERS":        _E("layer.ungroup",                "取消图层编组",             "Ctrl+Shift+G",  ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),

    "MOVE_BACKWARD":         _E("layer.move_backward",          "图层下移一层",             "Ctrl+[",        ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "MOVE_FORWARD":          _E("layer.move_forward",           "图层上移一层",             "Ctrl+]",        ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "SEND_TO_BACK":          _E("layer.send_to_back",           "图层置于底层",             "Ctrl+Shift+[",  ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "BRING_TO_FRONT":        _E("layer.bring_to_front",         "图层置于顶层",             "Ctrl+Shift+]",  ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "MOVE_BACKWARD_ALIAS":   _E("layer.move_backward_alias",    "图层下移一层(兼容)",       "Ctrl+Down",     ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
    "MOVE_FORWARD_ALIAS":    _E("layer.move_forward_alias",     "图层上移一层(兼容)",       "Ctrl+Up",       ShortcutLayer.LAYER, ShortcutScope.LAYER_ENABLED),
}

# ---------------------------------------------------------------------------
# 3) 工具切换（单字母键 —— 非文字编辑态生效）
#    没有的能力（选区/滤镜）不伪造快捷键，避免「有按键却语义错误」
# ---------------------------------------------------------------------------
PS_TOOL: Dict[str, ShortcutEntry] = {
    "MOVE":         _E("tool.move",          "移动/选择工具(V)",   "V",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING),
    "HAND":         _E("tool.hand",          "抓手工具(H)",        "H",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING),
    "ZOOM":         _E("tool.zoom",          "缩放工具(Z)",        "Z",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING,
                                                      notes="此前缺失"),
    "TEXT":         _E("tool.text",          "文字工具(T)",        "T",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING,
                                                      old="T(原 Ctrl+T 弹窗)"),
    "CROP":         _E("tool.crop",          "裁剪工具(C)",        "C",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING,
                                                      old="C(原画布内:路径闭合→Shift+C 门控化)"),
    "PATH":         _E("tool.path",          "路径/钢笔工具(P)",   "P",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING,
                                                      notes="此前缺失"),
    "GRADIENT":     _E("tool.gradient",      "渐变/油漆桶(G)",     "G",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING,
                                                      notes="此前缺失"),
    "EYEDROPPER":   _E("tool.eyedropper",    "吸管/取色器(I)",     "I",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING,
                                                      notes="此前缺失"),
    "SHAPE":        _E("tool.shape",         "形状/矢量工具(U)",   "U",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING,
                                                      notes="此前缺失"),
    "PATH_SELECT":  _E("tool.path_select",   "路径选择工具(A)",    "A",  ShortcutLayer.TOOL, ShortcutScope.TEXT_NOT_EDITING,
                                                      notes="仅在路径编辑场景生效；Ctrl+A 仍保留图层全选"),
}

# ---------------------------------------------------------------------------
# 4) 视图
# ---------------------------------------------------------------------------
PS_VIEW: Dict[str, ShortcutEntry] = {
    "TOGGLE_RULERS":   _E("view.toggle_rulers",    "切换标尺",         "Ctrl+R",    ShortcutLayer.VIEW, ShortcutScope.HAS_DOCUMENT,
                                                                  old="Ctrl+R(原:修改画布尺寸→Alt+Ctrl+C)"),
    "TOGGLE_GUIDES":   _E("view.toggle_guides",    "切换参考线",       ";",         ShortcutLayer.VIEW, ShortcutScope.HAS_DOCUMENT),
    "ZOOM_IN":         _E("view.zoom_in",          "放大",             "Ctrl++",    ShortcutLayer.VIEW, ShortcutScope.HAS_DOCUMENT),
    "ZOOM_OUT":        _E("view.zoom_out",         "缩小",             "Ctrl+-",    ShortcutLayer.VIEW, ShortcutScope.HAS_DOCUMENT),
    "ZOOM_RESET":      _E("view.zoom_reset",       "重置缩放/适合窗口", "Ctrl+0",    ShortcutLayer.VIEW, ShortcutScope.HAS_DOCUMENT),
    "SPACE_HAND_TEMP": _E("view.space_hand_temp",  "临时抓手(按住)",   "Space",     ShortcutLayer.VIEW, ShortcutScope.HAS_DOCUMENT),
}

# ---------------------------------------------------------------------------
# 5) 批图王专属功能 —— 刻意避开 PS 核心键位
# ---------------------------------------------------------------------------
APP_EXCLUSIVE: Dict[str, ShortcutEntry] = {
    "EXPORT_IMAGE":              _E("app.export_image",            "导出当前画面",         "Ctrl+Shift+X",      ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.HAS_DOCUMENT,
                                                                         old="Ctrl+E"),
    "MULTI_TAB_BATCH_EXPORT":    _E("app.multi_tab_batch_export",  "多标签高级批量导出",   "Ctrl+Alt+Shift+X",  ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.HAS_DOCUMENT,
                                                                         old="Ctrl+Shift+E"),
    "BATCH_EXPORT":              _E("app.batch_export",            "批量导出",            "F12",                ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.HAS_DOCUMENT),
    "DUPLICATE_TAB":             _E("app.duplicate_tab",           "复制当前标签页",       "Alt+Shift+D",       ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.HAS_DOCUMENT,
                                                                         old="Ctrl+D"),
    "CREATE_TEXT_LAYER":         _E("app.create_text_layer",       "添加文字图层",         "Shift+F8",          ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.LAYER_ENABLED,
                                                                         old="Ctrl+T"),
    "CREATE_EMPTY_IMAGE_LAYER":  _E("app.create_empty_image_layer","新建空图片图层",       "Shift+Ctrl+N",      ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.LAYER_ENABLED,
                                                                         old="Ctrl+L"),
    "OPEN_PRESET_CENTER":        _E("app.open_preset_center",      "打开项目预设中心",     "Ctrl+Shift+P",      ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.ALWAYS,
                                                                         old="Ctrl+P"),
    "RESIZE_CANVAS":             _E("app.resize_canvas",           "修改画布尺寸",         "Alt+Ctrl+C",        ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.HAS_DOCUMENT,
                                                                         old="Ctrl+R",
                                                                         notes="对齐 Photoshop Alt+Ctrl+C = Canvas Size"),
    "DEBUG_PREVIEW_PERF":        _E("app.debug_preview_perf",      "打印预览性能报告(调试)", "Ctrl+Shift+Alt+P", ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.HAS_DOCUMENT,
                                                                         old="Ctrl+P"),

    # 画布矢量编辑（仅矢量节点选中态生效，避免抢占工具单字母键）
    "PATH_HANDLE_MIRROR":        _E("app.path_handle_mirror",      "路径手柄=镜像",         "Q",                 ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.VECTOR_NODE_EDITING),
    "PATH_HANDLE_COLLINEAR":     _E("app.path_handle_collinear",   "路径手柄=共线",         "W",                 ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.VECTOR_NODE_EDITING),
    "PATH_HANDLE_FREE":          _E("app.path_handle_free",        "路径手柄=自由",         "E",                 ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.VECTOR_NODE_EDITING),
    "TOGGLE_PATH_CLOSED":        _E("app.toggle_path_closed",      "切换路径闭合",          "Shift+C",           ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.VECTOR_NODE_EDITING,
                                                                         old="C"),
    "NODE_CORNER":               _E("app.node_corner",             "节点类型=尖角",         "1",                 ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.VECTOR_NODE_EDITING),
    "NODE_SMOOTH":               _E("app.node_smooth",             "节点类型=平滑",         "2",                 ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.VECTOR_NODE_EDITING),
    "NODE_SYMMETRIC":            _E("app.node_symmetric",          "节点类型=对称",         "3",                 ShortcutLayer.APP_EXCLUSIVE, ShortcutScope.VECTOR_NODE_EDITING),
}


SHORTCUT_LAYERS: Dict[ShortcutLayer, Dict[str, ShortcutEntry]] = {
    ShortcutLayer.FILE_HISTORY:   PS_FILE_HISTORY,
    ShortcutLayer.LAYER:          PS_LAYER,
    ShortcutLayer.TOOL:           PS_TOOL,
    ShortcutLayer.VIEW:           PS_VIEW,
    ShortcutLayer.APP_EXCLUSIVE:  APP_EXCLUSIVE,
}

SHORTCUTS_BY_ACTION_ID: Dict[str, ShortcutEntry] = {}
for _layer_map in SHORTCUT_LAYERS.values():
    for _entry in _layer_map.values():
        # 兼容别名（如 Ctrl+Y 作为 Ctrl+Shift+Z 第二别名）会出现重复 action_id，忽略
        SHORTCUTS_BY_ACTION_ID.setdefault(_entry.action_id, _entry)


def seq(action_id: str) -> str:
    """按动作 ID 取快捷键序列（QML / 经典 / 画布三方通用）。"""
    entry = SHORTCUTS_BY_ACTION_ID.get(action_id)
    if entry is None:
        raise KeyError(f"[shortcut_contract] 未知快捷键动作: {action_id}")
    return entry.sequence


def photoshop_core_sequences() -> List[str]:
    """所有 PS 核心层序列，用于「应用专属层不许占用」断言。"""
    seqs: List[str] = []
    for _layer_name in (ShortcutLayer.FILE_HISTORY, ShortcutLayer.LAYER,
                        ShortcutLayer.TOOL, ShortcutLayer.VIEW):
        for entry in SHORTCUT_LAYERS[_layer_name].values():
            seqs.append(entry.sequence)
    return seqs


def app_exclusive_sequences() -> List[str]:
    return [e.sequence for e in APP_EXCLUSIVE.values()]


def detect_core_hijacks() -> List[Tuple[str, str, str, str]]:
    """检测 APP_EXCLUSIVE 是否意外占用了 PS 核心键位。

    返回 [(被占序列, APP_EXCLUSIVE 动作ID, 被占核心动作ID, 被占核心层级value)]
    """
    core_map: Dict[str, Tuple[str, str]] = {}
    for layer_name, layer_map in SHORTCUT_LAYERS.items():
        if layer_name == ShortcutLayer.APP_EXCLUSIVE:
            continue
        for entry in layer_map.values():
            if entry.sequence not in core_map:
                core_map[entry.sequence] = (entry.action_id, layer_name.value)

    hijacks: List[Tuple[str, str, str, str]] = []
    for entry in APP_EXCLUSIVE.values():
        if entry.sequence in core_map:
            core_action, core_layer = core_map[entry.sequence]
            hijacks.append((entry.sequence, entry.action_id, core_action, core_layer))
    return hijacks


def shortcut_table() -> List[ShortcutEntry]:
    """返回全部快捷键条目列表（供 QML / 经典 / 画布 / 测试共享索引）。

    顺序与 SHORTCUT_LAYERS 定义一致：FILE_HISTORY → LAYER → TOOL → VIEW → APP_EXCLUSIVE。
    同一层级内按字典插入顺序（Python 3.7+ 稳定）。
    """
    out: List[ShortcutEntry] = []
    for layer_map in SHORTCUT_LAYERS.values():
        out.extend(layer_map.values())
    return out


__all__ = [
    "ShortcutLayer",
    "ShortcutScope",
    "ShortcutEntry",
    "PS_FILE_HISTORY",
    "PS_LAYER",
    "PS_TOOL",
    "PS_VIEW",
    "APP_EXCLUSIVE",
    "SHORTCUT_LAYERS",
    "SHORTCUTS_BY_ACTION_ID",
    "shortcut_table",
    "seq",
    "photoshop_core_sequences",
    "app_exclusive_sequences",
    "detect_core_hijacks",
]
