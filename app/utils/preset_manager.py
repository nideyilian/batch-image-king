import os
import sys
import shutil
import pickle
import json
import datetime
import uuid
import re
import copy
from pathlib import Path

from app.utils.trusted_pickle import load_trusted_pickle

class PresetManager:
    """预设管理器，负责管理项目预设"""

    def __init__(self, app_dir=None, copy_initial=True):
        # 获取用户数据目录，避免写入程序目录（打包后可能只读）
        self.app_dir = str(app_dir) if app_dir else self._get_user_data_dir()
        # 创建预设目录
        self.presets_dir = os.path.join(self.app_dir, "presets")
        # 预设索引文件，用于管理预设元数据
        self.index_file = os.path.join(self.presets_dir, "presets_index.json")
        self._ensure_presets_dir()
        if copy_initial:
            self._copy_initial_presets()
        self._load_index()
    
    def _get_user_data_dir(self):
        """获取用户数据目录"""
        try:
            # Windows: %APPDATA%\批图王
            # Linux/Mac: ~/.config/批图王
            if os.name == 'nt':  # Windows
                base_dir = os.environ.get('APPDATA', os.path.expanduser('~'))
                app_data_dir = os.path.join(base_dir, '批图王')
            else:  # Linux/Mac
                base_dir = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config'))
                app_data_dir = os.path.join(base_dir, '批图王')
            
            # 确保目录存在
            os.makedirs(app_data_dir, exist_ok=True)
            return app_data_dir
        except Exception as e:
            safe_print(f"获取用户数据目录失败: {e}")
            # 回退到临时目录
            import tempfile
            return os.path.join(tempfile.gettempdir(), "批图王")
    
    def _copy_initial_presets(self):
        """从打包的资源中复制初始预设文件"""
        try:
            # 获取程序目录（打包后的资源位置）
            if getattr(sys, 'frozen', False):
                # 打包后的环境
                program_dir = sys._MEIPASS
            else:
                # 开发环境
                program_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            # 查找初始预设文件
            initial_presets_file = os.path.join(program_dir, "presets")
            
            # 如果用户预设目录为空且存在初始预设文件，则复制
            if (os.path.exists(initial_presets_file) and 
                os.path.isfile(initial_presets_file) and
                not os.path.exists(self.index_file)):
                
                # 复制初始预设文件到用户目录
                user_presets_file = os.path.join(self.presets_dir, "initial_presets")
                shutil.copy2(initial_presets_file, user_presets_file)
                safe_print(f"已复制初始预设文件到用户目录: {user_presets_file}")
                
        except Exception as e:
            safe_print(f"复制初始预设文件失败: {e}")
            # 不影响程序继续运行
    
    def _ensure_presets_dir(self):
        """确保预设目录存在，处理可能的异常情况"""
        if not os.path.exists(self.presets_dir):
            try:
                os.makedirs(self.presets_dir, exist_ok=True)
            except Exception as e:
                safe_print(f"创建预设目录失败: {e}")
                # 尝试使用临时目录
                import tempfile
                self.presets_dir = os.path.join(tempfile.gettempdir(), "批图王_presets")
                if not os.path.exists(self.presets_dir):
                    os.makedirs(self.presets_dir, exist_ok=True)
                # 更新索引文件路径
                self.index_file = os.path.join(self.presets_dir, "presets_index.json")
        elif not os.path.isdir(self.presets_dir):
            # 如果存在但不是目录，使用备用目录
            safe_print(f"预设路径 {self.presets_dir} 存在但不是目录，使用备用目录")
            self.presets_dir = os.path.join(self.app_dir, "presets_backup")
            if not os.path.exists(self.presets_dir):
                os.makedirs(self.presets_dir, exist_ok=True)
            # 更新索引文件路径
            self.index_file = os.path.join(self.presets_dir, "presets_index.json")

    def _load_index(self):
        """加载预设索引"""
        self.presets_index = {}
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self.presets_index = json.load(f)
            except Exception as e:
                safe_print(f"加载预设索引失败: {e}")
                self.presets_index = {}

        # 确保索引结构正确
        if not isinstance(self.presets_index, dict):
            self.presets_index = {}

    def _save_index(self):
        """保存预设索引"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.presets_index, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            safe_print(f"保存预设索引失败: {e}")
            return False

    def _generate_safe_filename(self, name):
        """生成安全的文件名"""
        # 移除或替换不安全的字符
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 限制长度
        if len(safe_name) > 50:
            safe_name = safe_name[:50]
        # 确保不为空
        if not safe_name.strip():
            safe_name = "unnamed_preset"
        return safe_name.strip()

    def _generate_unique_id(self):
        """生成唯一ID"""
        return uuid.uuid4().hex[:12]  # 12位短UUID
    
    def get_presets_dir(self):
        """获取预设目录"""
        return self.presets_dir

    def get_preset_list(self):
        """获取所有预设文件列表（兼容旧版本）"""
        presets = []
        for preset_id, preset_info in self.presets_index.items():
            preset_name = preset_info.get('name', preset_id)
            preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
            if os.path.exists(preset_path):
                presets.append((preset_name, preset_path))
        return presets

    def get_all_presets(self):
        """获取所有预设的详细信息"""
        presets = []
        for preset_id, preset_info in self.presets_index.items():
            preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
            if os.path.exists(preset_path):
                preset_data = preset_info.copy()
                preset_data['id'] = preset_id
                preset_data['path'] = preset_path
                self._ensure_optional_metadata(preset_data)
                presets.append(preset_data)

        # 按创建时间排序（最新的在前）
        presets.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return presets

    def _ensure_optional_metadata(self, preset_info):
        """补齐预设中心使用的可选元数据，兼容旧索引。"""
        if not isinstance(preset_info, dict):
            return preset_info
        preset_info.setdefault('tags', [])
        preset_info.setdefault('category', '未分类')
        preset_info.setdefault('thumbnail_path', '')
        preset_info.setdefault('last_used_at', '')
        preset_info.setdefault('run_count', 0)
        preset_info.setdefault('document_count', 0)
        return preset_info

    def get_preset_summary(self, preset_id):
        """获取预设中心卡片所需摘要信息。"""
        preset_info = self.load_preset(preset_id)
        if not preset_info:
            return None

        index_info = self.presets_index.get(preset_id, {}).copy()
        self._ensure_optional_metadata(index_info)

        documents = []
        if isinstance(preset_info, dict) and isinstance(preset_info.get('documents'), list):
            documents = preset_info.get('documents', [])
        elif isinstance(preset_info, dict):
            documents = [preset_info]

        canvas_sizes = []
        total_layers = 0
        tab_names = []
        for index, doc in enumerate(documents):
            if not isinstance(doc, dict):
                continue
            width = int(doc.get('canvas_width') or 0)
            height = int(doc.get('canvas_height') or 0)
            if width and height:
                size_text = f"{width}x{height}"
                if size_text not in canvas_sizes:
                    canvas_sizes.append(size_text)
            layers = doc.get('layers', [])
            if isinstance(layers, list):
                total_layers += len(layers)
            tab_names.append(doc.get('original_tab_name') or doc.get('tab_name') or doc.get('name') or f"标签页 {index + 1}")

        export_settings = {}
        if documents and isinstance(documents[0], dict):
            export_settings = documents[0].get('export_settings') or {}

        summary = {
            'id': preset_id,
            'path': os.path.join(self.presets_dir, f"{preset_id}.cmp"),
            'name': index_info.get('name') or preset_info.get('name') or preset_id,
            'description': index_info.get('description') or preset_info.get('description') or '',
            'created_at': index_info.get('created_at') or preset_info.get('created_at') or '',
            'modified_at': index_info.get('modified_at') or preset_info.get('modified_at') or '',
            'type': index_info.get('type') or preset_info.get('type') or ('multi_document' if len(documents) > 1 else 'single_document'),
            'document_count': len(documents),
            'canvas_sizes': canvas_sizes,
            'total_layers': total_layers,
            'tab_names': tab_names,
            'export_settings': export_settings,
            'category': index_info.get('category', '未分类'),
            'tags': index_info.get('tags', []),
            'thumbnail_path': index_info.get('thumbnail_path', ''),
            'last_used_at': index_info.get('last_used_at', ''),
            'run_count': int(index_info.get('run_count') or 0),
        }
        return summary
    
    def save_preset(self, name, source_file, description=""):
        """将当前项目保存为预设（基于已保存的文件）"""
        # 确保预设目录存在
        self._ensure_presets_dir()

        # 生成唯一ID和安全文件名
        preset_id = self._generate_unique_id()
        preset_file = os.path.join(self.presets_dir, f"{preset_id}.cmp")

        try:
            # 复制文件
            shutil.copy2(source_file, preset_file)

            # 更新索引
            self.presets_index[preset_id] = {
                'name': name,
                'description': description,
                'created_at': datetime.datetime.now().isoformat(),
                'modified_at': datetime.datetime.now().isoformat(),
                'version': 2,
                'type': 'single_document',
                'document_count': 1,
                'canvas_sizes': [],
                'total_layers': 0,
                'tags': [],
                'category': '未分类',
                'thumbnail_path': '',
                'last_used_at': '',
                'run_count': 0
            }

            # 保存索引
            self._save_index()
            return preset_id
        except Exception as e:
            safe_print(f"保存预设失败: {e}")
            return None
    
    def save_preset_from_document(self, name, document, description=""):
        """直接从文档对象保存预设，无需先保存文件

        参数:
            name (str): 预设名称
            document (Document): 文档对象
            description (str): 预设描述

        返回:
            str: 预设ID，保存失败则返回None
        """
        # 确保预设目录存在
        self._ensure_presets_dir()

        # 生成唯一ID
        preset_id = self._generate_unique_id()
        preset_file = os.path.join(self.presets_dir, f"{preset_id}.cmp")

        try:
            from app.models.document_serializer import DocumentSerializer

            document_data = DocumentSerializer.prepare_document_data(document)
            document_data['version'] = 5

            # 直接保存数据到预设文件
            with open(preset_file, 'wb') as f:
                pickle.dump(document_data, f)

            # 更新索引
            self.presets_index[preset_id] = {
                'name': name,
                'description': description,
                'created_at': datetime.datetime.now().isoformat(),
                'modified_at': datetime.datetime.now().isoformat(),
                'version': 2,
                'type': 'single_document',
                'document_count': 1,
                'canvas_sizes': [f"{int(document.canvas_width)}x{int(document.canvas_height)}"],
                'total_layers': len(getattr(document, 'layers', []) or []),
                'tags': [],
                'category': '未分类',
                'thumbnail_path': '',
                'last_used_at': '',
                'run_count': 0
            }

            # 保存索引
            self._save_index()
            return preset_id
        except Exception as e:
            safe_print(f"保存预设失败: {e}")
            return None
    
    def save_preset_documents(self, name, description, documents, global_settings=None):
        """将多个文档对象保存为预设，无需先保存文件

        参数:
            name (str): 预设名称
            description (str): 预设描述
            documents (list): 文档对象列表
            global_settings (dict): 全局设置

        返回:
            str/dict: 成功时返回预设ID，重名时返回包含重名信息的字典，失败返回None
        """
        # 检查是否已存在同名预设
        existing_preset_id = self._find_preset_by_name(name)
        if existing_preset_id:
            # 返回重名信息
            return {
                "duplicate": True,
                "name": name,
                "existing_id": existing_preset_id
            }

        # 确保预设目录存在
        self._ensure_presets_dir()

        # 生成唯一ID
        preset_id = self._generate_unique_id()
        preset_file = os.path.join(self.presets_dir, f"{preset_id}.cmp")
        
        try:
            # 创建预设数据结构
            preset_data = {
                'id': preset_id,
                'name': name,
                'description': description,
                'created_at': datetime.datetime.now().isoformat(),
                'modified_at': datetime.datetime.now().isoformat(),
                'version': 2,
                'global_settings': global_settings or {},
                'documents': []
            }

            # 为每个文档创建数据
            for index, doc in enumerate(documents):
                from app.models.document_serializer import DocumentSerializer

                doc_data = DocumentSerializer.prepare_document_data(doc)
                doc_data.update({
                    'index': index,
                    'name': getattr(doc, 'tab_name', f"标签页 {index+1}"),
                    'original_tab_name': getattr(doc, 'original_tab_name', getattr(doc, 'tab_name', f"标签页 {index+1}")),
                    'version': 5,
                })
                preset_data['documents'].append(doc_data)

            # 保存预设文件
            with open(preset_file, 'wb') as f:
                pickle.dump(preset_data, f)

            # 更新索引
            self.presets_index[preset_id] = {
                'name': name,
                'description': description,
                'created_at': datetime.datetime.now().isoformat(),
                'modified_at': datetime.datetime.now().isoformat(),
                'version': 2,
                'type': 'multi_document',
                'document_count': len(documents),
                'canvas_sizes': list(dict.fromkeys(
                    f"{int(getattr(doc, 'canvas_width', 0))}x{int(getattr(doc, 'canvas_height', 0))}"
                    for doc in documents
                    if int(getattr(doc, 'canvas_width', 0)) > 0 and int(getattr(doc, 'canvas_height', 0)) > 0
                )),
                'total_layers': sum(len(getattr(doc, 'layers', []) or []) for doc in documents),
                'tags': [],
                'category': '未分类',
                'thumbnail_path': '',
                'last_used_at': '',
                'run_count': 0
            }

            # 保存索引
            self._save_index()
            return preset_id
        except Exception as e:
            safe_print(f"保存预设文档失败: {e}")
            return None
    
    def _find_preset_by_name(self, name):
        """根据名称查找预设ID"""
        for preset_id, preset_info in self.presets_index.items():
            if preset_info.get('name') == name:
                return preset_id
        return None

    def load_preset(self, preset_id):
        """加载预设数据"""
        if isinstance(preset_id, str) and preset_id.endswith('.cmp'):
            # 兼容旧版本：如果传入的是路径，尝试从路径加载
            preset_path = preset_id
        else:
            # 新版本：根据ID构建路径
            preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")

        if not os.path.exists(preset_path):
            return None

        try:
            # 加载预设文件数据
            with open(preset_path, 'rb') as f:
                preset_data = load_trusted_pickle(f, preset_path)

            # 如果是新格式，直接返回
            if isinstance(preset_data, dict) and 'id' in preset_data:
                if preset_id in self.presets_index:
                    self._ensure_optional_metadata(self.presets_index[preset_id])
                return preset_data

            # 如果是旧格式，添加索引信息
            if preset_id in self.presets_index:
                preset_info = self.presets_index[preset_id].copy()
                self._ensure_optional_metadata(preset_info)
                preset_info.update(preset_data)
                return preset_info

            return preset_data
        except Exception as e:
            safe_print(f"加载预设失败: {e}")
            return None

    def delete_preset(self, preset_id):
        """删除预设"""
        if isinstance(preset_id, str) and preset_id.endswith('.cmp'):
            # 兼容旧版本：如果传入的是路径
            preset_path = preset_id
            # 尝试从路径中提取ID
            filename = os.path.basename(preset_path)
            preset_id = os.path.splitext(filename)[0]
        else:
            # 新版本：根据ID构建路径
            preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")

        try:
            # 删除文件
            if os.path.exists(preset_path):
                os.remove(preset_path)

            # 从索引中删除
            if preset_id in self.presets_index:
                del self.presets_index[preset_id]
                self._save_index()

            return True
        except Exception as e:
            safe_print(f"删除预设失败: {e}")
            return False

    def duplicate_preset(self, preset_id):
        """复制一个预设，返回新预设ID。"""
        preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
        if preset_id not in self.presets_index or not os.path.exists(preset_path):
            return None

        try:
            new_id = self._generate_unique_id()
            new_path = os.path.join(self.presets_dir, f"{new_id}.cmp")
            shutil.copy2(preset_path, new_path)

            old_info = copy.deepcopy(self.presets_index.get(preset_id, {}))
            base_name = old_info.get('name', '未命名预设')
            new_name = f"{base_name} 副本"
            counter = 2
            while self._find_preset_by_name(new_name):
                new_name = f"{base_name} 副本 {counter}"
                counter += 1

            now = datetime.datetime.now().isoformat()
            old_info.update({
                'name': new_name,
                'created_at': now,
                'modified_at': now,
                'thumbnail_path': '',
                'last_used_at': '',
                'run_count': 0,
            })
            self._ensure_optional_metadata(old_info)
            self.presets_index[new_id] = old_info
            self._save_index()
            return new_id
        except Exception as e:
            safe_print(f"复制预设失败: {e}")
            return None

    def touch_preset_used(self, preset_id):
        """记录预设运行时间和次数。"""
        if preset_id not in self.presets_index:
            return False
        try:
            info = self.presets_index[preset_id]
            self._ensure_optional_metadata(info)
            info['last_used_at'] = datetime.datetime.now().isoformat()
            info['run_count'] = int(info.get('run_count') or 0) + 1
            return self._save_index()
        except Exception as e:
            safe_print(f"更新预设使用记录失败: {e}")
            return False

    def update_preset(self, preset_id, name=None, description=None):
        """更新预设信息"""
        if preset_id not in self.presets_index:
            return False

        try:
            # 更新索引信息
            if name is not None:
                self.presets_index[preset_id]['name'] = name
            if description is not None:
                self.presets_index[preset_id]['description'] = description

            # 更新修改时间
            self.presets_index[preset_id]['modified_at'] = datetime.datetime.now().isoformat()

            # 保存索引
            return self._save_index()
        except Exception as e:
            safe_print(f"更新预设失败: {e}")
            return False

    def export_preset(self, preset_id, export_path):
        """导出单个预设"""
        try:
            preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
            if not os.path.exists(preset_path):
                return False

            # 创建导出数据
            export_data = {
                'version': 2,
                'export_type': 'single_preset',
                'exported_at': datetime.datetime.now().isoformat(),
                'preset_info': self.presets_index.get(preset_id, {}),
                'preset_data': None
            }

            # 加载预设数据
            with open(preset_path, 'rb') as f:
                export_data['preset_data'] = load_trusted_pickle(f, preset_path)

            # 保存导出文件
            with open(export_path, 'wb') as f:
                pickle.dump(export_data, f)

            return True
        except Exception as e:
            safe_print(f"导出预设失败: {e}")
            return False

    def import_preset(self, import_path):
        """导入预设"""
        try:
            # 加载导入文件
            with open(import_path, 'rb') as f:
                import_data = load_trusted_pickle(f, import_path)

            # 检查导入数据格式
            if isinstance(import_data, dict) and 'export_type' in import_data:
                if import_data.get('export_type') == 'all_presets':
                    imported_ids = []
                    for preset_package in import_data.get('presets', []) or []:
                        preset_info = preset_package.get('info', {}) if isinstance(preset_package, dict) else {}
                        preset_data = preset_package.get('data') if isinstance(preset_package, dict) else None
                        if not preset_data:
                            continue
                        preset_id = self._generate_unique_id()
                        preset_name = preset_info.get('name', '导入的预设')
                        counter = 1
                        original_name = preset_name
                        while self._find_preset_by_name(preset_name):
                            preset_name = f"{original_name} ({counter})"
                            counter += 1

                        preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
                        with open(preset_path, 'wb') as f:
                            pickle.dump(preset_data, f)

                        now = datetime.datetime.now().isoformat()
                        info = {
                            'name': preset_name,
                            'description': preset_info.get('description', ''),
                            'created_at': now,
                            'modified_at': now,
                            'version': preset_info.get('version', 2),
                            'type': preset_info.get('type', 'unknown'),
                            'document_count': preset_info.get('document_count', 0),
                            'imported': True
                        }
                        self._ensure_optional_metadata(info)
                        self.presets_index[preset_id] = info
                        imported_ids.append(preset_id)
                    self._save_index()
                    return imported_ids[0] if imported_ids else None

                # 新格式导入
                preset_info = import_data.get('preset_info', {})
                preset_data = import_data.get('preset_data')

                if not preset_data:
                    return None

                # 生成新的预设ID
                preset_id = self._generate_unique_id()
                preset_name = preset_info.get('name', '导入的预设')

                # 检查名称冲突
                counter = 1
                original_name = preset_name
                while self._find_preset_by_name(preset_name):
                    preset_name = f"{original_name} ({counter})"
                    counter += 1

                # 保存预设文件
                preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
                with open(preset_path, 'wb') as f:
                    pickle.dump(preset_data, f)

                # 更新索引
                info = {
                    'name': preset_name,
                    'description': preset_info.get('description', ''),
                    'created_at': datetime.datetime.now().isoformat(),
                    'modified_at': datetime.datetime.now().isoformat(),
                    'version': preset_info.get('version', 2),
                    'type': preset_info.get('type', 'unknown'),
                    'imported': True
                }
                self._ensure_optional_metadata(info)
                self.presets_index[preset_id] = info

                # 保存索引
                self._save_index()
                return preset_id
            else:
                # 旧格式导入（直接是预设数据）
                preset_id = self._generate_unique_id()
                preset_name = "导入的预设"

                # 检查名称冲突
                counter = 1
                original_name = preset_name
                while self._find_preset_by_name(preset_name):
                    preset_name = f"{original_name} ({counter})"
                    counter += 1

                # 保存预设文件
                preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
                with open(preset_path, 'wb') as f:
                    pickle.dump(import_data, f)

                # 更新索引
                info = {
                    'name': preset_name,
                    'description': '',
                    'created_at': datetime.datetime.now().isoformat(),
                    'modified_at': datetime.datetime.now().isoformat(),
                    'version': 2,
                    'type': 'unknown',
                    'imported': True
                }
                self._ensure_optional_metadata(info)
                self.presets_index[preset_id] = info

                # 保存索引
                self._save_index()
                return preset_id

        except Exception as e:
            safe_print(f"导入预设失败: {e}")
            return None

    def export_all_presets(self, export_path):
        """导出所有预设"""
        try:
            export_data = {
                'version': 2,
                'export_type': 'all_presets',
                'exported_at': datetime.datetime.now().isoformat(),
                'presets': []
            }

            # 收集所有预设
            for preset_id, preset_info in self.presets_index.items():
                preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
                if os.path.exists(preset_path):
                    try:
                        with open(preset_path, 'rb') as f:
                            preset_data = load_trusted_pickle(f, preset_path)

                        export_data['presets'].append({
                            'info': preset_info,
                            'data': preset_data
                        })
                    except Exception as e:
                        safe_print(f"导出预设 {preset_id} 失败: {e}")
                        continue

            # 保存导出文件
            with open(export_path, 'wb') as f:
                pickle.dump(export_data, f)

            return len(export_data['presets'])
        except Exception as e:
            safe_print(f"导出所有预设失败: {e}")
            return 0


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except Exception:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")
