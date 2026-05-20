import os
import json
from typing import List, Dict, Tuple, Optional

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        safe_print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            safe_print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            safe_print("[DEBUG] Message encoding failed")


class CanvasPresetManager:
    """画布尺寸预设管理器"""
    
    def __init__(self):
        # 获取用户配置目录
        self.config_dir = os.path.join(os.path.expanduser('~'), '.config', '批图王')
        self.presets_file = os.path.join(self.config_dir, 'canvas_presets.json')
        
        # 确保配置目录存在
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 默认预设（内置预设）
        self.default_presets = {
            "built_in": [
                {"name": "640x480 (标准VGA)", "width": 640, "height": 480, "category": "标准"},
                {"name": "800x600 (SVGA)", "width": 800, "height": 600, "category": "标准"},
                {"name": "1024x768 (XGA)", "width": 1024, "height": 768, "category": "标准"},
                {"name": "1280x720 (HD 720p)", "width": 1280, "height": 720, "category": "高清"},
                {"name": "1920x1080 (全高清 1080p)", "width": 1920, "height": 1080, "category": "高清"},
                {"name": "2560x1440 (QHD)", "width": 2560, "height": 1440, "category": "高清"},
                {"name": "3840x2160 (4K UHD)", "width": 3840, "height": 2160, "category": "超高清"},
                {"name": "720x1280 (竖屏HD)", "width": 720, "height": 1280, "category": "竖屏"},
                {"name": "1080x1920 (竖屏FHD)", "width": 1080, "height": 1920, "category": "竖屏"},
                {"name": "1000x1000 (正方形)", "width": 1000, "height": 1000, "category": "正方形"},
                {"name": "2000x2000 (大正方形)", "width": 2000, "height": 2000, "category": "正方形"},
            ]
        }
        
        # 加载用户自定义预设
        self.user_presets = self.load_user_presets()
    
    def load_user_presets(self) -> Dict:
        """加载用户自定义预设"""
        if os.path.exists(self.presets_file):
            try:
                with open(self.presets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                safe_print(f"加载用户预设失败: {e}")
                return {"custom": []}
        return {"custom": []}
    
    def save_user_presets(self) -> bool:
        """保存用户自定义预设"""
        try:
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_presets, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            safe_print(f"保存用户预设失败: {e}")
            return False
    
    def get_all_presets(self) -> List[Dict]:
        """获取所有预设（内置 + 用户自定义）"""
        all_presets = []
        
        # 添加内置预设
        for preset in self.default_presets["built_in"]:
            preset_copy = preset.copy()
            preset_copy["is_builtin"] = True
            all_presets.append(preset_copy)
        
        # 添加用户自定义预设
        for preset in self.user_presets.get("custom", []):
            preset_copy = preset.copy()
            preset_copy["is_builtin"] = False
            all_presets.append(preset_copy)
        
        return all_presets
    
    def get_preset_names(self) -> List[str]:
        """获取所有预设名称列表，用于下拉框"""
        names = ["自定义"]
        
        # 添加内置预设名称
        for preset in self.default_presets["built_in"]:
            names.append(preset["name"])
        
        # 添加用户自定义预设名称
        for preset in self.user_presets.get("custom", []):
            names.append(f"{preset['name']} (自定义)")
        
        return names
    
    def get_preset_size(self, index: int) -> Optional[Tuple[int, int]]:
        """根据索引获取预设尺寸"""
        if index == 0:  # 自定义
            return None
        
        all_presets = self.get_all_presets()
        preset_index = index - 1  # 减去"自定义"选项
        
        if 0 <= preset_index < len(all_presets):
            preset = all_presets[preset_index]
            return (preset["width"], preset["height"])
        
        return None
    
    def add_custom_preset(self, name: str, width: int, height: int, category: str = "自定义") -> bool:
        """添加自定义预设"""
        # 检查名称是否已存在
        if self.preset_exists(name):
            return False
        
        # 验证尺寸
        if width <= 0 or height <= 0:
            return False
        
        # 添加预设
        new_preset = {
            "name": name,
            "width": width,
            "height": height,
            "category": category
        }
        
        if "custom" not in self.user_presets:
            self.user_presets["custom"] = []
        
        self.user_presets["custom"].append(new_preset)
        
        # 保存到文件
        return self.save_user_presets()
    
    def remove_custom_preset(self, name: str) -> bool:
        """删除自定义预设"""
        if "custom" not in self.user_presets:
            return False
        
        # 查找并删除预设
        for i, preset in enumerate(self.user_presets["custom"]):
            if preset["name"] == name:
                del self.user_presets["custom"][i]
                return self.save_user_presets()
        
        return False
    
    def preset_exists(self, name: str) -> bool:
        """检查预设名称是否已存在"""
        # 检查内置预设
        for preset in self.default_presets["built_in"]:
            if preset["name"] == name:
                return True
        
        # 检查用户自定义预设
        for preset in self.user_presets.get("custom", []):
            if preset["name"] == name:
                return True
        
        return False
    
    def get_categories(self) -> List[str]:
        """获取所有类别"""
        categories = set()
        
        # 内置预设类别
        for preset in self.default_presets["built_in"]:
            categories.add(preset["category"])
        
        # 用户自定义预设类别
        for preset in self.user_presets.get("custom", []):
            categories.add(preset["category"])
        
        return sorted(list(categories))
    
    def get_presets_by_category(self, category: str) -> List[Dict]:
        """根据类别获取预设"""
        presets = []
        
        for preset in self.get_all_presets():
            if preset["category"] == category:
                presets.append(preset)
        
        return presets
    
    def update_custom_preset(self, old_name: str, new_name: str, width: int, height: int, category: str = "自定义") -> bool:
        """更新自定义预设"""
        if "custom" not in self.user_presets:
            return False
        
        # 如果改名，检查新名称是否已存在
        if old_name != new_name and self.preset_exists(new_name):
            return False
        
        # 查找并更新预设
        for preset in self.user_presets["custom"]:
            if preset["name"] == old_name:
                preset["name"] = new_name
                preset["width"] = width
                preset["height"] = height
                preset["category"] = category
                return self.save_user_presets()
        
        return False 