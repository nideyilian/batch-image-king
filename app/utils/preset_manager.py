import os
import sys
import shutil
import pickle
import json
import datetime
import threading
import uuid
import re
import copy
import tempfile

from app.utils.trusted_pickle import load_trusted_pickle

# 侧栏分类（文件夹）的兜底桶与命名上限。
# 上限是为了不让一个超长名字把 208px 的侧栏撑破——超出部分会被 elide 吃掉，
# 但输入时不拦的话用户会以为名字存丢了。
CATEGORY_UNSORTED = "未分类"
CATEGORY_NAME_MAX_LEN = 24


class PresetManager:
    """预设管理器，负责管理项目预设"""

    def __init__(self, app_dir=None, copy_initial=True):
        # 获取用户数据目录，避免写入程序目录（打包后可能只读）
        self.app_dir = str(app_dir) if app_dir else self._get_user_data_dir()
        # 创建预设目录
        self.presets_dir = os.path.join(self.app_dir, "presets")
        # 预设索引文件，用于管理预设元数据
        self.index_file = os.path.join(self.presets_dir, "presets_index.json")
        self.last_error = ""
        # 「读—改—写」整段必须持锁：缩略图后台线程、导出线程、UI 三方都会读同一个 .cmp。
        # 只锁写不锁读，会出现两个入口各自读到旧副本、后写的覆盖先写的。
        self._preset_write_lock = threading.RLock()
        self._ensure_presets_dir()
        if copy_initial:
            self._copy_initial_presets()
        self._load_index()
        # 用户显式创建的分类名单（保持用户顺序）。分类本身仍是预设上的
        # category 字段，这份名单只多记「哪些分类是用户建的、按什么顺序排」。
        self._category_order = []
        self._load_categories()
    
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
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                dir=self.presets_dir,
                prefix='.presets-index-',
                suffix='.json',
            )
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.presets_index, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.index_file)
            return True
        except Exception as e:
            safe_print(f"保存预设索引失败: {e}")
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _set_error(self, message):
        self.last_error = str(message or "")

    @staticmethod
    def _is_valid_document_data(document_data):
        if not isinstance(document_data, dict):
            return False
        try:
            width = int(document_data.get('canvas_width'))
            height = int(document_data.get('canvas_height'))
        except (TypeError, ValueError, OverflowError):
            return False
        return (
            width > 0
            and height > 0
            and isinstance(document_data.get('layers'), list)
        )

    @classmethod
    def _is_valid_preset_data(cls, preset_data):
        if not isinstance(preset_data, dict):
            return False
        if 'documents' not in preset_data:
            return cls._is_valid_document_data(preset_data)
        documents = preset_data.get('documents')
        return (
            isinstance(documents, list)
            and bool(documents)
            and all(cls._is_valid_document_data(item) for item in documents)
        )

    @staticmethod
    def _document_payloads(preset_data):
        if isinstance(preset_data, dict) and isinstance(preset_data.get('documents'), list):
            return preset_data['documents']
        return [preset_data]

    @classmethod
    def _metadata_from_preset_data(cls, preset_data):
        documents = cls._document_payloads(preset_data)
        canvas_sizes = []
        total_layers = 0
        for document in documents:
            size = f"{int(document['canvas_width'])}x{int(document['canvas_height'])}"
            if size not in canvas_sizes:
                canvas_sizes.append(size)
            total_layers += len(document['layers'])
        return {
            'type': 'multi_document' if len(documents) > 1 else 'single_document',
            'document_count': len(documents),
            'canvas_sizes': canvas_sizes,
            'total_layers': total_layers,
        }

    @staticmethod
    def _dump_pickle_atomic(data, destination):
        destination = os.path.abspath(os.fspath(destination))
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                dir=os.path.dirname(destination),
                prefix=f'.{os.path.basename(destination)}-',
                suffix='.tmp',
            )
            with os.fdopen(fd, 'wb') as f:
                pickle.dump(data, f)
            os.replace(temp_path, destination)
            temp_path = None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # 原地改写已有预设（卡片内标签页管理）
    #
    # 全仓此前 4 处 pickle.dump 全是「新建」：save_preset / save_preset_from_document /
    # save_preset_documents / import_preset。没有任何路径能改写**已存在**预设的
    # documents[]，所以「重命名标签页 / 清空标签页」无处落盘。
    # 下面几个方法补上这条路，全部走同一套约束：
    #   1. 读—改—写整段持 self._preset_write_lock
    #   2. 写前用 mtime 做乐观锁，防止覆盖别的入口刚做的修改
    #   3. 原子写（复用 _dump_pickle_atomic：mkstemp + os.replace）
    #   4. 写成功后同步索引里的 document_count / total_layers / canvas_sizes / type
    # ------------------------------------------------------------------

    def _preset_file_path(self, preset_id):
        return os.path.join(self.presets_dir, f"{preset_id}.cmp")

    def _read_preset_for_write(self, preset_id):
        """读取预设用于改写，返回 (preset_data, mtime) 或 (None, reason)。

        reason 取值：``preset_missing``（文件不存在）/ ``preset_corrupt``（格式不合法）。
        **不**在此处加锁，由调用方在外层持锁，保证「读到的就是将要改的那份」。
        """
        preset_id = str(preset_id or "").strip()
        if not preset_id:
            return None, "preset_missing"
        path = self._preset_file_path(preset_id)
        if not os.path.isfile(path):
            return None, "preset_missing"
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None, "preset_missing"
        try:
            with open(path, "rb") as f:
                data = load_trusted_pickle(f, path)
        except Exception as e:
            safe_print(f"读取预设失败（可能已损坏）: {e}")
            return None, "preset_corrupt"
        if not isinstance(data, dict):
            return None, "preset_corrupt"
        # 兼容旧格式：单文档预设没有 documents 键，包成一层
        if not isinstance(data.get("documents"), list):
            if self._is_valid_document_data(data):
                data = dict(data)
                data["documents"] = [dict(data)]
            else:
                return None, "preset_corrupt"
        return data, mtime

    def _commit_preset_write(self, preset_id, preset_data, expected_mtime):
        """把改好的 preset_data 写回磁盘并同步索引。

        返回 (ok, reason)。reason 取值：``stale`` / ``io_failed`` / ``preset_missing``。
        """
        path = self._preset_file_path(preset_id)
        # 乐观锁：写前再取一次 mtime，与读时不一致说明别人改过，不能覆盖
        if expected_mtime is not None:
            try:
                if os.path.getmtime(path) != expected_mtime:
                    return False, "stale"
            except OSError:
                return False, "preset_missing"
        preset_data["modified_at"] = datetime.datetime.now().isoformat()
        try:
            self._dump_pickle_atomic(preset_data, path)
        except Exception as e:
            safe_print(f"写回预设失败: {e}")
            return False, "io_failed"
        # 索引是卡片的数据源，必须同步，否则卡片页数/图层数还是旧的
        info = self.presets_index.get(preset_id)
        if isinstance(info, dict):
            try:
                self._ensure_optional_metadata(info)
                info.update(self._metadata_from_preset_data(preset_data))
                info["modified_at"] = preset_data["modified_at"]
                # 页数变少后 cover_index 可能越界，这里钳到最后一页而非归零。
                # 归零会把 close_document 精心算好的「后一页接上来」覆盖掉
                # （删第 3 页时 cover 已被置为 1，若这里再归 0 就变成跳回首图）。
                count = int(info.get("document_count") or 0)
                cover = int(info.get("cover_index") or 0)
                if count <= 0:
                    info["cover_index"] = 0
                else:
                    info["cover_index"] = max(0, min(cover, count - 1))
                self._save_index()
            except Exception as e:
                # 索引写失败不回滚 .cmp：内容已正确落盘，索引下次启动会重建，
                # 而回滚 .cmp 反而会把用户刚做的修改丢掉。只记日志。
                safe_print(f"预设索引同步失败（内容已保存）: {e}")
        return True, ""

    def rename_document(self, preset_id, page_index, title):
        """重命名单个标签页，返回 (ok, reason)。

        ⚠️ 必须同时写 ``name`` 与 ``original_tab_name``：
        ``get_preset_summary()`` 取页名的表达式是
        ``original_tab_name or tab_name or name``（本文件 321 行附近）。
        只改 name 而 original_tab_name 还是旧值，卡片读到的永远是旧名 ——
        这是本功能最容易出现「改了没生效」的地方。
        """
        preset_id = str(preset_id or "").strip()
        title = str(title or "").strip()
        with self._preset_write_lock:
            data, mtime = self._read_preset_for_write(preset_id)
            if data is None:
                return False, mtime  # mtime 位此时是 reason
            documents = data["documents"]
            try:
                index = int(page_index)
            except (TypeError, ValueError):
                return False, "page_missing"
            if index < 0 or index >= len(documents):
                return False, "page_missing"
            document = documents[index]
            if not isinstance(document, dict):
                return False, "page_missing"
            document["name"] = title
            document["original_tab_name"] = title
            return self._commit_preset_write(preset_id, data, mtime)

    def clear_preset_documents(self, preset_id):
        """清空预设的全部标签页（保留预设本身、分类、标签、封面、使用次数）。

        返回 (ok, reason)。
        """
        preset_id = str(preset_id or "").strip()
        with self._preset_write_lock:
            data, mtime = self._read_preset_for_write(preset_id)
            if data is None:
                return False, mtime
            data["documents"] = []
            return self._commit_preset_write(preset_id, data, mtime)

    def close_document(self, preset_id, page_index):
        """关闭（删除）单个标签页，返回 (ok, remaining, reason, removed_payload)。

        ``removed_payload`` 是被删页的完整 dict（含 layers），供调用方做撤销。
        漏掉它会导致「关掉最后一页后无法恢复内容」—— 只恢复一个空页壳
        比不给撤销更糟（用户以为救回来了，实际图层全丢）。

        剩余页数为 0 时**不自动删除预设** —— 与「关闭全部」保持同一套语义：
        清空内容 ≠ 删除条目。
        """
        preset_id = str(preset_id or "").strip()
        with self._preset_write_lock:
            data, mtime = self._read_preset_for_write(preset_id)
            if data is None:
                return False, 0, mtime, None
            documents = data["documents"]
            try:
                index = int(page_index)
            except (TypeError, ValueError):
                return False, len(documents), "page_missing", None
            if index < 0 or index >= len(documents):
                return False, len(documents), "page_missing", None
            removed = copy.deepcopy(documents.pop(index))
            # 封面让位规则（与浏览器关标签页的心智一致）：
            # - 删的是封面页：让**后一页接上来**（下标不变），已经是最后一页则退一格
            # - 删的是封面页之前的页：封面下标整体前移一格
            # - 删的是封面页之后的页：封面不动
            info = self.presets_index.get(preset_id)
            if isinstance(info, dict):
                cover = int(info.get("cover_index") or 0)
                if cover > index:
                    info["cover_index"] = cover - 1
                elif cover == index:
                    info["cover_index"] = max(0, min(index, len(documents) - 1))
            ok, reason = self._commit_preset_write(preset_id, data, mtime)
            if not ok:
                return False, len(documents) + 1, reason, None
            return True, len(documents), "", removed

    def restore_document_payloads(self, preset_id, documents):
        """把一批 documents 快照原样写回（供「清空全部」的 30s 撤销使用）。

        返回 (ok, reason)。documents 必须是纯 dict 列表（即 load 时拿到的原始结构），
        不接受 Document 对象 —— 后者需要走 prepare_document_data，属于保存新预设的路径。
        """
        preset_id = str(preset_id or "").strip()
        if not isinstance(documents, list):
            return False, "invalid_payload"
        with self._preset_write_lock:
            data, mtime = self._read_preset_for_write(preset_id)
            if data is None:
                return False, mtime
            data["documents"] = [copy.deepcopy(item) for item in documents]
            return self._commit_preset_write(preset_id, data, mtime)

    def update_preset_documents(self, preset_id, documents):
        """把**编辑后的 Document 对象**覆盖写回已有预设，返回 (ok, reason)。

        与 ``restore_document_payloads`` 的区别，两者不能合并：
        - ``restore_document_payloads`` 写回的是**原样快照**（撤销用，不做任何转换）
        - 本方法写回的是**用户编辑过的文档**，必须走 ``prepare_document_data``
          把图层树序列化一遍，否则存进去的只是旧 data 的深拷贝

        为什么不能再用 ``save_preset_documents``：那个方法每次都生成新 id、
        新建 .cmp，语义是"另存为"。用户在工作区改完内容后想存回**同一张卡片**，
        另存为会留下一堆重复预设。

        封面下标按「总页数」重新钳位：用户可能删了几页，旧 ``cover_index`` 会越界。
        """
        preset_id = str(preset_id or "").strip()
        if not preset_id:
            return False, "preset_missing"
        valid = [document for document in list(documents or []) if document is not None]
        if not valid:
            return False, "no_documents"

        from app.models.document_serializer import DocumentSerializer

        payloads = []
        for index, document in enumerate(valid):
            payload = DocumentSerializer.prepare_document_data(document)
            payload.update({
                'index': index,
                # 页名优先用运行时改名后的 tab_name，保证「改了名再保存」能存住
                'name': str(
                    getattr(document, 'tab_name', '')
                    or getattr(document, 'original_tab_name', '')
                    or f"标签页 {index + 1}"
                ),
                'original_tab_name': str(
                    getattr(document, 'original_tab_name', '')
                    or getattr(document, 'tab_name', '')
                    or f"标签页 {index + 1}"
                ),
                'version': 5,
            })
            payloads.append(payload)

        with self._preset_write_lock:
            data, mtime = self._read_preset_for_write(preset_id)
            if data is None:
                return False, mtime
            data["documents"] = payloads
            data["modified_at"] = datetime.datetime.now().isoformat()
            ok, reason = self._commit_preset_write(preset_id, data, mtime)
            if not ok:
                return False, reason
            # 页数可能变了，封面下标跟着钳位
            info = self.presets_index.get(preset_id)
            if isinstance(info, dict):
                count = len(payloads)
                cover = int(info.get("cover_index") or 0)
                info["cover_index"] = 0 if count <= 0 else max(0, min(cover, count - 1))
            return True, ""

    def _next_import_name(self, requested_name, reserved_names):
        base_name = str(requested_name or '导入的预设').strip() or '导入的预设'
        name = base_name
        counter = 1
        while name in reserved_names:
            name = f"{base_name} ({counter})"
            counter += 1
        reserved_names.add(name)
        return name

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

        # 按创建时间排序（最新的在前）。
        # 注意：这里**不**按 order 排——order 只服务于工作台的「手动排序」模式，
        # 由 VM 层决定是否采用。放这里会污染所有调用方。
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
        preset_info.setdefault('favorite', False)
        # 手动排序位次：None 表示「还没参与过手动排序」，由 ensure_order()
        # 统一种子化。用 None 而不是 0，才能区分「首位」和「未排序」。
        preset_info.setdefault('order', None)
        # 封面文档下标：多标签预设里用哪一页当卡片封面。
        preset_info.setdefault('cover_index', 0)
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
            'favorite': bool(index_info.get('favorite', False)),
            'order': index_info.get('order'),
            'cover_index': int(index_info.get('cover_index') or 0),
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
                'type': 'multi_document' if len(documents) > 1 else 'single_document',
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

    def set_favorite(self, preset_id, favorite):
        """设置/取消预设收藏（工作台「收藏」分类的数据来源）。"""
        if preset_id not in self.presets_index:
            return False
        try:
            info = self.presets_index[preset_id]
            self._ensure_optional_metadata(info)
            info['favorite'] = bool(favorite)
            return self._save_index()
        except Exception as e:
            safe_print(f"更新预设收藏状态失败: {e}")
            return False

    def set_category(self, preset_id, category):
        """设置预设分类（工作台左侧分类树的数据来源）。

        空串统一归一为「未分类」，避免出现空分类节点。
        """
        if preset_id not in self.presets_index:
            return False
        try:
            info = self.presets_index[preset_id]
            self._ensure_optional_metadata(info)
            info['category'] = str(category or '').strip() or CATEGORY_UNSORTED
            info['modified_at'] = datetime.datetime.now().isoformat()
            if not self._save_index():
                return False
            # 通过检查器新起的名字也登记进名单：否则它在侧栏里只是「派生」项，
            # 一旦没有预设再用这个名字就会从列表里消失。
            name = info['category']
            if name != CATEGORY_UNSORTED and name not in self._category_order:
                self._category_order.append(name)
                self._save_categories()
            return True
        except Exception as e:
            safe_print(f"更新预设分类失败: {e}")
            return False

    def set_tags(self, preset_id, tags):
        """设置预设标签列表。

        去空、去重、保序；写成列表而非字符串，便于工作台搜索直接 join。
        """
        if preset_id not in self.presets_index:
            return False
        try:
            info = self.presets_index[preset_id]
            self._ensure_optional_metadata(info)
            cleaned = []
            for tag in tags or []:
                text = str(tag or '').strip()
                if text and text not in cleaned:
                    cleaned.append(text)
            info['tags'] = cleaned
            info['modified_at'] = datetime.datetime.now().isoformat()
            return self._save_index()
        except Exception as e:
            safe_print(f"更新预设标签失败: {e}")
            return False

    def set_thumbnail_path(self, preset_id, thumbnail_path):
        """记录缩略图相对路径（工作台卡片封面）。"""
        if preset_id not in self.presets_index:
            return False
        try:
            info = self.presets_index[preset_id]
            self._ensure_optional_metadata(info)
            info['thumbnail_path'] = str(thumbnail_path or '')
            return self._save_index()
        except Exception as e:
            safe_print(f"更新预设缩略图路径失败: {e}")
            return False

    def set_cover_index(self, preset_id, cover_index):
        """指定多标签预设用第几页当卡片封面。

        只影响展示，不改预设内容本身。换封面后缩略图必须失效重算，
        由调用方负责触发（VM 里会 force 重新渲染）。
        """
        if preset_id not in self.presets_index:
            return False
        try:
            info = self.presets_index[preset_id]
            self._ensure_optional_metadata(info)
            index = int(cover_index or 0)
            info['cover_index'] = max(0, index)
            return self._save_index()
        except (TypeError, ValueError):
            safe_print(f"无效的封面下标: {cover_index}")
            return False
        except Exception as e:
            safe_print(f"更新预设封面失败: {e}")
            return False

    def ensure_order(self):
        """给所有还没排序位次的预设播种 order。

        种子策略：按当前「创建时间倒序」的展示顺序编号，这样用户第一次
        看到手动排序时，顺序和他习惯的完全一致，不会突然乱掉。
        已有序号的预设不动。
        """
        try:
            unordered = [
                pid for pid, info in self.presets_index.items()
                if info.get('order') is None
            ]
            if not unordered:
                return 0

            # 取当前实际展示顺序作为基准
            ordered_ids = [p['id'] for p in self.get_all_presets()]
            existing_max = max(
                (
                    int(info.get('order'))
                    for info in self.presets_index.values()
                    if info.get('order') is not None
                ),
                default=-1,
            )
            next_order = existing_max + 1
            planted = 0
            for pid in ordered_ids:
                info = self.presets_index.get(pid)
                if not isinstance(info, dict) or info.get('order') is not None:
                    continue
                info['order'] = next_order
                next_order += 1
                planted += 1
            if planted:
                self._save_index()
            return planted
        except Exception as e:
            safe_print(f"初始化预设顺序失败: {e}")
            return 0

    def reorder_presets(self, ordered_ids):
        """按给定 id 顺序重写全部 order（0..n-1）。

        只处理传入的 id；不在列表里的预设保留原位次并顺延到末尾之后的区段，
        避免部分排序把其它预设的序号挤乱。
        """
        try:
            ordered_ids = [str(pid) for pid in (ordered_ids or [])]
            if not ordered_ids:
                return False

            stamp = datetime.datetime.now().isoformat()
            cursor = 0
            for pid in ordered_ids:
                info = self.presets_index.get(pid)
                if not isinstance(info, dict):
                    continue
                self._ensure_optional_metadata(info)
                info['order'] = cursor
                info['modified_at'] = stamp
                cursor += 1

            # 未出现在列表里的预设，按原 order 排在后面，保持相对次序
            rest = [
                (pid, info) for pid, info in self.presets_index.items()
                if pid not in ordered_ids and isinstance(info, dict)
            ]
            rest.sort(key=lambda pair: (pair[1].get('order') is None,
                                        pair[1].get('order') or 0))
            for pid, info in rest:
                self._ensure_optional_metadata(info)
                info['order'] = cursor
                cursor += 1

            return self._save_index()
        except Exception as e:
            safe_print(f"重排预设失败: {e}")
            return False

    # ---- 分类（侧栏文件夹） ----
    #
    # 历史设计：分类只存在于预设的 category 字段上，侧栏清单由预设聚合出来。
    # 代价是「新建分类」根本建不出来——空分类没有落脚点，下一个预设没归进去，
    # 它就从侧栏消失了；也没有地方存顺序。所以补一份很小的名单文件
    # （categories.json），只记「用户建了哪些分类、按什么顺序排」。
    # 成员关系仍然只看预设的 category 字段，不做双向维护，避免两份数据打架。

    def _categories_path(self):
        return os.path.join(self.presets_dir, "categories.json")

    def _load_categories(self):
        path = self._categories_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except Exception as e:
            safe_print(f"加载分类清单失败: {e}")
            return
        names = raw.get('names') if isinstance(raw, dict) else raw
        if not isinstance(names, list):
            return
        seen = set()
        for item in names:
            name = str(item or '').strip()
            if not name or name == CATEGORY_UNSORTED or name in seen:
                continue
            seen.add(name)
            self._category_order.append(name)

    def _save_categories(self):
        path = self._categories_path()
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                dir=self.presets_dir,
                prefix='.preset-categories-',
                suffix='.json',
            )
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({'names': list(self._category_order)}, f,
                          ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
            return True
        except Exception as e:
            safe_print(f"保存分类清单失败: {e}")
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _category_counts(self):
        """分类名 -> 预设条数。空串/缺失统一算「未分类」。"""
        counts = {}
        for info in self.presets_index.values():
            if not isinstance(info, dict):
                continue
            name = str(info.get('category') or CATEGORY_UNSORTED).strip() or CATEGORY_UNSORTED
            counts[name] = counts.get(name, 0) + 1
        return counts

    def get_category_names(self):
        """侧栏要显示的分类顺序。

        用户建过的分类按创建顺序排在前面（即使当前 0 个预设也保留），
        剩下「只在预设里出现过、没进过名单」的旧分类按条数排在后面。
        「未分类」永远压尾——它是兜底桶，不是文件夹。
        """
        counts = self._category_counts()
        names = list(self._category_order)
        extra = [(name, count) for name, count in counts.items() if name not in names]
        extra.sort(key=lambda item: (-item[1], item[0]))
        names.extend(name for name, _count in extra)
        if CATEGORY_UNSORTED in names:
            names.remove(CATEGORY_UNSORTED)
            names.append(CATEGORY_UNSORTED)
        return names

    def _validate_category_name(self, name):
        """通用校验，返回 (归一化名字, 错误文案)。"""
        name = str(name or '').strip()
        if not name:
            return '', '分类名不能为空'
        if name == CATEGORY_UNSORTED:
            return '', '「未分类」是内置分类'
        if len(name) > CATEGORY_NAME_MAX_LEN:
            return '', f'分类名不能超过 {CATEGORY_NAME_MAX_LEN} 个字'
        return name, ''

    def category_exists(self, name):
        name = str(name or '').strip()
        if not name:
            return False
        return name in self._category_counts() or name in self._category_order

    def create_category(self, name):
        """新建一个（可以是空的）分类。重名直接拒绝，不做隐式合并。"""
        name, error = self._validate_category_name(name)
        if error:
            self._set_error(error)
            return False
        with self._preset_write_lock:
            if self.category_exists(name):
                self._set_error('已存在同名分类')
                return False
            self._category_order.append(name)
            if not self._save_categories():
                self._category_order.pop()
                self._set_error('保存分类失败')
                return False
        self._set_error('')
        return True

    def rename_category(self, old_name, new_name):
        """重命名分类：成员跟着改名，名单里的位置保持不变。

        重名时拒绝而不是合并——合并会悄悄吞掉一个分类，用户事后无法追溯。
        """
        old_name = str(old_name or '').strip()
        if not old_name or old_name == CATEGORY_UNSORTED:
            self._set_error('「未分类」不能重命名')
            return False
        new_name, error = self._validate_category_name(new_name)
        if error:
            self._set_error(error)
            return False
        if new_name == old_name:
            self._set_error('')
            return True

        with self._preset_write_lock:
            if not self.category_exists(old_name):
                self._set_error('分类不存在')
                return False
            if self.category_exists(new_name):
                self._set_error('已存在同名分类')
                return False

            backup_index = copy.deepcopy(self.presets_index)
            backup_order = list(self._category_order)

            stamp = datetime.datetime.now().isoformat()
            moved = 0
            for info in self.presets_index.values():
                if not isinstance(info, dict):
                    continue
                self._ensure_optional_metadata(info)
                if str(info.get('category') or '').strip() == old_name:
                    info['category'] = new_name
                    info['modified_at'] = stamp
                    moved += 1
            if moved and not self._save_index():
                self.presets_index = backup_index
                self._set_error('重命名分类失败')
                return False

            if old_name in self._category_order:
                self._category_order[self._category_order.index(old_name)] = new_name
            else:
                # 只在预设里出现过的旧分类：重命名后登记进名单，
                # 否则它还是「派生」状态，下次改回去就找不到了。
                self._category_order.append(new_name)
            if not self._save_categories():
                self.presets_index = backup_index
                self._category_order = backup_order
                self._save_index()
                self._set_error('重命名分类失败')
                return False
        self._set_error('')
        return True

    def delete_category(self, category):
        """删除分类：成员归回「未分类」，不删预设。

        返回受影响条数；分类不存在或不允许删除时返回 -1。
        空分类（用户建了但没放东西）也允许删，此时返回 0。
        """
        name = str(category or '').strip()
        if not name or name == CATEGORY_UNSORTED:
            self._set_error('「未分类」不能删除')
            return -1
        with self._preset_write_lock:
            try:
                if not self.category_exists(name):
                    self._set_error('分类不存在')
                    return -1

                affected = 0
                stamp = datetime.datetime.now().isoformat()
                for info in self.presets_index.values():
                    if not isinstance(info, dict):
                        continue
                    self._ensure_optional_metadata(info)
                    if str(info.get('category') or '').strip() == name:
                        info['category'] = CATEGORY_UNSORTED
                        info['modified_at'] = stamp
                        affected += 1
                if affected and not self._save_index():
                    self._set_error('删除分类失败')
                    return -1

                if name in self._category_order:
                    self._category_order.remove(name)
                    if not self._save_categories():
                        self._set_error('保存分类清单失败')
                        return -1
                self._set_error('')
                return affected
            except Exception as e:
                safe_print(f"删除预设分类失败: {e}")
                self._set_error('删除分类失败')
                return -1

    def export_preset(self, preset_id, export_path):
        """导出单个预设"""
        try:
            preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
            if preset_id not in self.presets_index or not os.path.exists(preset_path):
                self._set_error("预设不存在")
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
            if not self._is_valid_preset_data(export_data['preset_data']):
                self._set_error("预设数据已损坏或格式不正确")
                return False

            self._dump_pickle_atomic(export_data, export_path)

            self._set_error("")
            return True
        except Exception as e:
            safe_print(f"导出预设失败: {e}")
            self._set_error(f"导出预设失败: {e}")
            return False

    def import_preset(self, import_path):
        """导入预设"""
        temp_paths = []
        committed_paths = []
        original_index = copy.deepcopy(self.presets_index)
        try:
            with open(import_path, 'rb') as f:
                import_data = load_trusted_pickle(f, import_path)

            if isinstance(import_data, dict) and import_data.get('export_type') == 'all_presets':
                packages = import_data.get('presets')
                if not isinstance(packages, list) or not packages:
                    raise ValueError("预设合集为空或格式不正确")
                candidates = []
                for package in packages:
                    if not isinstance(package, dict):
                        raise ValueError("预设合集包含无效项目")
                    info = package.get('info')
                    data = package.get('data')
                    if not isinstance(info, dict) or not self._is_valid_preset_data(data):
                        raise ValueError("预设合集包含损坏或格式不正确的项目")
                    candidates.append((info, data))
            elif isinstance(import_data, dict) and 'export_type' in import_data:
                if import_data.get('export_type') != 'single_preset':
                    raise ValueError("不支持的预设导出格式")
                info = import_data.get('preset_info')
                data = import_data.get('preset_data')
                if not isinstance(info, dict) or not self._is_valid_preset_data(data):
                    raise ValueError("预设数据已损坏或格式不正确")
                candidates = [(info, data)]
            else:
                if not self._is_valid_preset_data(import_data):
                    raise ValueError("预设数据已损坏或格式不正确")
                candidates = [({}, import_data)]

            reserved_names = {
                str(item.get('name') or '') for item in self.presets_index.values()
            }
            reserved_ids = set(self.presets_index)
            pending = []
            for preset_info, preset_data in candidates:
                preset_id = self._generate_unique_id()
                while preset_id in reserved_ids:
                    preset_id = self._generate_unique_id()
                reserved_ids.add(preset_id)
                preset_name = self._next_import_name(
                    preset_info.get('name', '导入的预设'), reserved_names
                )
                now = datetime.datetime.now().isoformat()
                info = {
                    'name': preset_name,
                    'description': str(preset_info.get('description') or ''),
                    'created_at': now,
                    'modified_at': now,
                    'version': preset_info.get('version', 2),
                    'imported': True,
                    **self._metadata_from_preset_data(preset_data),
                }
                self._ensure_optional_metadata(info)

                fd, temp_path = tempfile.mkstemp(
                    dir=self.presets_dir,
                    prefix=f'.import-{preset_id}-',
                    suffix='.cmp',
                )
                with os.fdopen(fd, 'wb') as f:
                    pickle.dump(preset_data, f)
                temp_paths.append(temp_path)
                pending.append((preset_id, info, preset_data, temp_path))

            for preset_id, _info, _data, temp_path in pending:
                final_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
                os.replace(temp_path, final_path)
                temp_paths.remove(temp_path)
                committed_paths.append(final_path)

            self.presets_index.update({
                preset_id: info for preset_id, info, _data, _temp_path in pending
            })
            if not self._save_index():
                raise OSError("无法保存预设索引")

            self._set_error("")
            return pending[0][0]

        except Exception as e:
            safe_print(f"导入预设失败: {e}")
            self.presets_index = original_index
            for path in committed_paths + temp_paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            self._set_error(f"导入预设失败: {e}")
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

            if not self.presets_index:
                self._set_error("没有可导出的预设")
                return 0

            for preset_id, preset_info in self.presets_index.items():
                preset_path = os.path.join(self.presets_dir, f"{preset_id}.cmp")
                if not os.path.exists(preset_path):
                    raise FileNotFoundError(f"预设文件不存在: {preset_info.get('name', preset_id)}")
                with open(preset_path, 'rb') as f:
                    preset_data = load_trusted_pickle(f, preset_path)
                if not self._is_valid_preset_data(preset_data):
                    raise ValueError(f"预设数据已损坏: {preset_info.get('name', preset_id)}")
                export_data['presets'].append({
                    'info': copy.deepcopy(preset_info),
                    'data': preset_data
                })

            self._dump_pickle_atomic(export_data, export_path)

            self._set_error("")
            return len(export_data['presets'])
        except Exception as e:
            safe_print(f"导出所有预设失败: {e}")
            self._set_error(f"导出预设合集失败: {e}")
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
