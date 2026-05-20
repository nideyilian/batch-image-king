"""
画布尺寸预设常量模块
用于统一管理应用中使用的预设画布尺寸
"""

# 预设尺寸字典，键为尺寸ID，值为元组(宽度, 高度, 描述)
CANVAS_SIZE_PRESETS = {
    1: (1280, 720, "横向高清"),
    2: (720, 1280, "竖向高清"),
    3: (1080, 1920, "竖向全高清"),
    4: (800, 800, "正方形"),
}

# 预设尺寸的组合字符串，用于显示在UI中
def get_preset_display_name(preset_id):
    """获取预设尺寸的显示名称"""
    if preset_id not in CANVAS_SIZE_PRESETS:
        return "自定义"

    width, height, desc = CANVAS_SIZE_PRESETS[preset_id]
    return f"{width} × {height} ({desc})"

# 获取所有预设的显示名称列表
def get_all_preset_names():
    """获取所有预设尺寸的显示名称列表，包括"自定义"选项"""
    result = ["自定义"]
    for preset_id in sorted(CANVAS_SIZE_PRESETS.keys()):
        result.append(get_preset_display_name(preset_id))
    return result

# 根据预设ID获取尺寸
def get_preset_size(preset_id):
    """获取指定预设ID的宽度和高度"""
    if preset_id not in CANVAS_SIZE_PRESETS:
        return None

    width, height, _ = CANVAS_SIZE_PRESETS[preset_id]
    return (width, height) 