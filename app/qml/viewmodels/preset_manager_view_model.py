from __future__ import annotations

import os

import shiboken6
from PySide6.QtCore import QMetaObject, QObject, Property, QUrl, Qt, Signal, Slot

from app.utils.preset_document_loader import documents_from_preset_data
from app.utils.preset_manager import PresetManager
from app.utils.preset_thumbnail import (
    check_missing_sources,
    get_thumbnail_service,
    thumb_path_for,
)


class PresetManagerViewModel(QObject):
    presetsChanged = Signal()
    stateChanged = Signal()
    # 工作台查询条件变化（搜索词/排序/筛选/收藏视图）后重算可见列表
    viewChanged = Signal()
    # 单张缩略图就绪，QML 据此只刷新对应卡片而不是整表
    thumbnailReady = Signal(str)

    def __init__(self, workspace, sessions=None, manager=None, parent=None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._sessions = sessions
        self._manager = manager or PresetManager()
        self._last_error = ""
        self._search_text = ""
        self._sort_mode = "recent"
        self._scope = "all"  # all / recent / favorite
        self._category = ""
        self._thumb_service = None
        self._pending_thumbs: dict[str, str] = {}
        self._missing_cache: dict[str, list] = {}
        self._cover_cache: dict[str, list] = {}
        self._shutdown_flag = False

    def _set_error(self, message: str) -> None:
        self._last_error = str(message or "")
        self.stateChanged.emit()

    def _manager_error(self, fallback: str) -> str:
        return str(getattr(self._manager, "last_error", "") or fallback)

    @Property(str, notify=stateChanged)
    def lastError(self) -> str:
        return self._last_error

    @Property("QVariantList", notify=presetsChanged)
    def presets(self):
        result = []
        for preset in self._manager.get_all_presets():
            # get_all_presets() 只返回索引项，不含 canvas_sizes / total_layers
            # ——那两个要靠 get_preset_summary() 解析 .cmp 才有。早先直接拿索引
            # 当摘要用，导致卡片上所有预设都显示「未知画布」。
            # 合并策略：索引项优先（category / favorite / last_used_at 是用户
            # 刚改过的最新值），缺的字段用 summary 补齐。
            preset_id = str(preset.get("id") or "")
            detail = self._manager.get_preset_summary(preset_id) or {}
            summary = dict(detail)
            summary.update(preset)
            result.append(
                {
                    "id": preset_id,
                    "name": str(summary.get("name") or "未命名预设"),
                    "description": str(summary.get("description") or ""),
                    "type": str(summary.get("type") or "single_document"),
                    "documentCount": int(summary.get("document_count") or 1),
                    "totalLayers": int(summary.get("total_layers") or 0),
                    "canvasSizes": list(summary.get("canvas_sizes") or []),
                    "createdAt": str(summary.get("created_at") or ""),
                    "modifiedAt": str(summary.get("modified_at") or ""),
                    "category": str(summary.get("category") or "未分类"),
                    "tags": list(summary.get("tags") or []),
                    "favorite": bool(summary.get("favorite", False)),
                    "lastUsedAt": str(summary.get("last_used_at") or ""),
                    "runCount": int(summary.get("run_count") or 0),
                    "thumbnailUrl": self._thumbnail_url(preset_id),
                    "thumbnailRevision": self._thumbnail_revision(preset_id),
                    "missingSources": self._missing_sources(preset_id),
                    "order": int(summary.get("order") if summary.get("order") is not None else 1 << 30),
                    "coverIndex": int(summary.get("cover_index") or 0),
                    "coverCandidates": self._cover_candidates(preset_id),
                    "pageThumbs": self._page_thumbs(preset_id),
                }
            )
        return result

    def _thumbnail_url(self, preset_id: str) -> str:
        """QML ``Image.source`` 用的缩略图地址。

        文件不存在时返回空串，QML 侧显示骨架占位并触发后台生成。
        带 ``?v=<mtime>`` 是为了让 QML 在缩略图重生成后刷新缓存，而不是
        一直用旧图。
        """
        path = thumb_path_for(self._manager.presets_dir, preset_id)
        try:
            if not os.path.isfile(path) or os.path.getsize(path) <= 0:
                return ""
            stamp = int(os.path.getmtime(path))
        except OSError:
            return ""
        return QUrl.fromLocalFile(path).toString() + f"?v={stamp}"

    def _cover_candidates(self, preset_id: str) -> list:
        """多标签预设的「可选封面」清单：每页的序号 + 尺寸 + 名称。

        只解析轻量元数据（不解码图层），供检查器里的封面选择器渲染。
        单文档预设返回空列表——没有可选项就不该显示选择器。
        """
        if preset_id in self._cover_cache:
            return self._cover_cache[preset_id]
        candidates: list = []
        try:
            data = self._manager.load_preset(preset_id)
            documents = []
            if isinstance(data, dict) and isinstance(data.get("documents"), list):
                documents = [d for d in data["documents"] if isinstance(d, dict)]
            elif isinstance(data, dict):
                documents = [data]
            if len(documents) > 1:
                for index, doc in enumerate(documents):
                    width = int(doc.get("canvas_width") or 0)
                    height = int(doc.get("canvas_height") or 0)
                    name = (
                        doc.get("original_tab_name")
                        or doc.get("tab_name")
                        or doc.get("name")
                        or f"第 {index + 1} 页"
                    )
                    candidates.append(
                        {
                            "index": index,
                            "name": str(name),
                            "size": f"{width}x{height}" if width and height else "",
                        }
                    )
        except Exception:  # noqa: BLE001 - 封面清单失败不该影响列表
            candidates = []
        self._cover_cache[preset_id] = candidates
        return candidates

    def _missing_sources(self, preset_id: str) -> list:
        """素材已失效的图层名（缓存，避免每次重建 presets 都读盘解析）。"""
        if preset_id in self._missing_cache:
            return self._missing_cache[preset_id]
        missing = check_missing_sources(preset_id, self._manager.presets_dir)
        self._missing_cache[preset_id] = missing
        return missing

    def _invalidate_missing_cache(self) -> None:
        self._missing_cache.clear()

    def _page_thumbs(self, preset_id: str) -> list:
        """各页已落盘的缩略图地址（按页号顺序），供卡片悬停轮播。

        只返回**已经存在**的页：没渲染好的页跳过，避免 QML 拿到空串后
        显示破图。页数少于等于 1 时返回空列表，卡片就不启用轮播。
        """
        total = len(self._cover_candidates(preset_id))
        if total <= 1:
            return []
        presets_dir = self._manager.presets_dir
        result = []
        for page in range(total):
            path = thumb_path_for(presets_dir, preset_id, page)
            try:
                if not os.path.isfile(path) or os.path.getsize(path) <= 0:
                    continue
                stamp = int(os.path.getmtime(path))
            except OSError:
                continue
            result.append(QUrl.fromLocalFile(path).toString() + f"?v={stamp}")
        return result

    def _thumbnail_revision(self, preset_id: str) -> int:
        path = thumb_path_for(self._manager.presets_dir, preset_id)
        try:
            return int(os.path.getmtime(path))
        except OSError:
            return 0

    @Property(int, notify=presetsChanged)
    def count(self) -> int:
        return len(self._manager.get_all_presets())

    def _name_exists(self, name: str, *, exclude_id: str = "") -> bool:
        normalized = str(name or "").strip().casefold()
        return any(
            str(preset.get("name") or "").strip().casefold() == normalized
            and str(preset.get("id") or "") != str(exclude_id or "")
            for preset in self._manager.get_all_presets()
        )

    def _preset_exists(self, preset_id: str) -> bool:
        preset_id = str(preset_id or "")
        return bool(preset_id) and any(
            str(preset.get("id") or "") == preset_id
            for preset in self._manager.get_all_presets()
        )

    @staticmethod
    def _local_path(path_or_url: str) -> str:
        text = str(path_or_url or "")
        url = QUrl(text)
        return url.toLocalFile() if url.isLocalFile() else text

    def _session_document(self, index: int):
        if self._sessions is None or not 0 <= int(index) < self._sessions.count:
            return None
        document = self._sessions.documentAt(int(index))
        if document is None:
            return None
        title = str(
            self._sessions.data(
                self._sessions.index(int(index), 0), self._sessions.TitleRole
            )
            or f"标签页 {int(index) + 1}"
        )
        document.tab_name = title
        document.original_tab_name = title
        return document

    def _documents_for_save(self, *, include_all: bool):
        if self._sessions is not None:
            if self._sessions.count <= 0:
                return []
            indices = (
                range(self._sessions.count)
                if include_all
                else [self._sessions.activeIndex]
            )
            return [
                document
                for index in indices
                if (document := self._session_document(index)) is not None
            ]
        document = getattr(self._workspace, "document", None)
        return [document] if document is not None else []

    def _save_documents(self, name: str, description: str, documents) -> bool:
        name = str(name or "").strip()
        if not name:
            self._set_error("预设名称不能为空")
            return False
        if self._name_exists(name):
            self._set_error("已存在同名预设")
            return False
        documents = list(documents or [])
        if not documents:
            self._set_error("没有可保存的文档")
            return False
        preset_id = self._manager.save_preset_documents(
            name,
            str(description or "").strip(),
            documents,
            {},
        )
        if not isinstance(preset_id, str) or not preset_id:
            self._set_error("保存预设失败")
            return False
        self._set_error("")
        self.presetsChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def saveCurrent(self, name: str, description: str = "") -> bool:
        return self._save_documents(
            name,
            description,
            self._documents_for_save(include_all=False),
        )

    @Slot(str, str, result=bool)
    def saveAll(self, name: str, description: str = "") -> bool:
        return self._save_documents(
            name,
            description,
            self._documents_for_save(include_all=True),
        )

    @Slot(str, result=int)
    def loadPreset(self, preset_id: str) -> int:
        data = self._manager.load_preset(str(preset_id or ""))
        if not data:
            self._set_error("无法读取预设")
            return 0
        documents = documents_from_preset_data(data)
        if not documents:
            self._set_error("预设中没有可用文档")
            return 0
        if self._sessions is not None:
            loaded = int(self._sessions.appendDocuments(documents, "加载预设"))
        else:
            loaded = 1 if self._workspace.activateDocument(documents[0]) else 0
        if not loaded:
            self._set_error("无法将预设加入工作区")
            return 0
        self._manager.touch_preset_used(str(preset_id or ""))
        self._set_error("")
        self.presetsChanged.emit()
        return loaded

    @Slot(str, result=str)
    def duplicatePreset(self, preset_id: str) -> str:
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return ""
        new_id = str(self._manager.duplicate_preset(preset_id) or "")
        if not new_id:
            self._set_error("复制预设失败")
            return ""
        self._set_error("")
        self.presetsChanged.emit()
        return new_id

    @Slot(str, str, result=bool)
    def exportPreset(self, preset_id: str, export_path: str) -> bool:
        preset_id = str(preset_id or "")
        export_path = self._local_path(export_path)
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False
        if not export_path:
            self._set_error("请选择导出位置")
            return False
        success = bool(self._manager.export_preset(preset_id, export_path))
        self._set_error("" if success else self._manager_error("导出预设失败"))
        return success

    @Slot(str, result=int)
    def exportAll(self, export_path: str) -> int:
        export_path = self._local_path(export_path)
        if not export_path:
            self._set_error("请选择导出位置")
            return 0
        if self.count <= 0:
            self._set_error("没有可导出的预设")
            return 0
        exported = int(self._manager.export_all_presets(export_path) or 0)
        self._set_error(
            "" if exported > 0 else self._manager_error("导出预设合集失败")
        )
        return exported

    @Slot(str, result=int)
    def importPreset(self, import_path: str) -> int:
        import_path = self._local_path(import_path)
        if not import_path:
            self._set_error("请选择要导入的预设文件")
            return 0
        before_count = self.count
        imported_id = self._manager.import_preset(import_path)
        imported = max(0, self.count - before_count)
        if not imported_id or imported <= 0:
            self._set_error(
                self._manager_error("导入预设失败，文件可能已损坏或格式不正确")
            )
            return 0
        self._set_error("")
        self.presetsChanged.emit()
        return imported

    @Slot(str, str, str, result=bool)
    def renamePreset(self, preset_id: str, name: str, description: str = "") -> bool:
        preset_id = str(preset_id or "")
        name = str(name or "").strip()
        if not preset_id or not name:
            self._set_error("预设名称不能为空")
            return False
        if self._name_exists(name, exclude_id=preset_id):
            self._set_error("已存在同名预设")
            return False
        success = bool(self._manager.update_preset(preset_id, name=name, description=str(description or "").strip()))
        self._set_error("" if success else "更新预设失败")
        if success:
            self.presetsChanged.emit()
        return success

    @Slot(str, result=bool)
    def deletePreset(self, preset_id: str) -> bool:
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False
        success = bool(self._manager.delete_preset(preset_id))
        self._set_error("" if success else "删除预设失败")
        if success:
            self.presetsChanged.emit()
        return success

    # ------------------------------------------------------------------
    # 工作台查询层（搜索 / 排序 / 收藏 / 分类 / 缩略图）
    # ------------------------------------------------------------------

    @Property(str, notify=viewChanged)
    def searchText(self) -> str:
        return self._search_text

    @Slot(str)
    def setSearchText(self, text: str) -> None:
        text = str(text or "")
        if text == self._search_text:
            return
        self._search_text = text
        self.viewChanged.emit()

    @Property(str, notify=viewChanged)
    def sortMode(self) -> str:
        return self._sort_mode

    @Slot(str)
    def setSortMode(self, mode: str) -> None:
        mode = str(mode or "recent")
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        if mode == "manual":
            # 首次进手动模式：按当前展示顺序播种 order，让用户看到的顺序
            # 和之前完全一致（不会突然跳成"按创建时间"的另一种排列）。
            self._manager.ensure_order()
            self.presetsChanged.emit()
        self.viewChanged.emit()

    @Property(str, notify=viewChanged)
    def scope(self) -> str:
        return self._scope

    @Slot(str)
    def setScope(self, scope: str) -> None:
        scope = str(scope or "all")
        if scope == self._scope:
            return
        self._scope = scope
        self.viewChanged.emit()

    @Property(str, notify=viewChanged)
    def category(self) -> str:
        return self._category

    @Slot(str)
    def setCategory(self, category: str) -> None:
        category = str(category or "")
        if category == self._category:
            return
        self._category = category
        self.viewChanged.emit()

    @Property("QVariantList", notify=presetsChanged)
    def categories(self):
        """左侧导航用的分类清单（含数量），按现有预设实际分类聚合。"""
        buckets: dict[str, int] = {}
        for preset in self._manager.get_all_presets():
            name = str(preset.get("category") or "未分类")
            buckets[name] = buckets.get(name, 0) + 1
        return [
            {"name": name, "count": count}
            for name, count in sorted(buckets.items(), key=lambda item: (-item[1], item[0]))
        ]

    @Property(int, notify=presetsChanged)
    def favoriteCount(self) -> int:
        return sum(
            1 for preset in self._manager.get_all_presets() if preset.get("favorite")
        )

    @Property(int, notify=presetsChanged)
    def recentCount(self) -> int:
        return sum(
            1 for preset in self._manager.get_all_presets() if preset.get("last_used_at")
        )

    def _sorted_presets(self):
        """按当前 scope / category / 搜索词 / 排序输出预设摘要列表。"""
        items = [dict(preset) for preset in self.presets]

        if self._scope == "favorite":
            items = [item for item in items if item["favorite"]]
        elif self._scope == "recent":
            items = [item for item in items if item["lastUsedAt"]]

        if self._category:
            items = [item for item in items if item["category"] == self._category]

        keyword = self._search_text.strip().casefold()
        if keyword:
            def matches(item) -> bool:
                haystack = " ".join(
                    [
                        item["name"],
                        item["description"],
                        item["category"],
                        " ".join(item["tags"]),
                        " ".join(item["canvasSizes"]),
                    ]
                ).casefold()
                return keyword in haystack

            items = [item for item in items if matches(item)]

        if self._sort_mode == "manual":
            # 手动排序：按索引里的 order。order 为 None 的（还没播种）排到最后，
            # 由 ensureOrder() 在进入该模式时统一补齐。
            items.sort(key=lambda item: item["order"])
        elif self._sort_mode == "name":
            items.sort(key=lambda item: item["name"].casefold())
        elif self._sort_mode == "layers":
            items.sort(key=lambda item: item["totalLayers"], reverse=True)
        elif self._sort_mode == "created":
            items.sort(key=lambda item: item["createdAt"], reverse=True)
        elif self._sort_mode == "used":
            items.sort(key=lambda item: item["lastUsedAt"], reverse=True)
        else:  # recent：最近使用优先，其次按修改时间
            items.sort(
                key=lambda item: (item["lastUsedAt"] or item["modifiedAt"] or item["createdAt"]),
                reverse=True,
            )
        return items

    @Property("QVariantList", notify=viewChanged)
    def visiblePresets(self):
        return self._sorted_presets()

    @Property(int, notify=viewChanged)
    def visibleCount(self) -> int:
        return len(self._sorted_presets())

    @Slot(str, result=bool)
    def toggleFavorite(self, preset_id: str) -> bool:
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False
        current = False
        for preset in self._manager.get_all_presets():
            if str(preset.get("id") or "") == preset_id:
                current = bool(preset.get("favorite"))
                break
        success = bool(self._manager.set_favorite(preset_id, not current))
        if not success:
            self._set_error("更新收藏状态失败")
            return False
        self._set_error("")
        self.presetsChanged.emit()
        self.viewChanged.emit()
        return True

    # ---- 手动排序 / 封面 / 分类删除 ----

    @Slot(result=int)
    def ensureOrder(self) -> int:
        """进入手动排序模式前调用：给未排序的预设播种 order。"""
        planted = int(self._manager.ensure_order() or 0)
        if planted:
            self.presetsChanged.emit()
            self.viewChanged.emit()
        return planted

    @Slot(str, int, result=bool)
    def movePreset(self, preset_id: str, target_index: int) -> bool:
        """把 preset_id 移到当前可见顺序的第 target_index 位。

        只在「手动排序」模式下有意义：其它排序模式下拖拽会立刻被排序规则
        覆盖，看起来像"拖了没反应"。QML 侧只在 manual 模式允许拖拽。
        """
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False

        # 以「全部预设」的手动顺序为基准重排，避免受当前筛选影响导致
        # 把不在视图里的预设顺序打乱。
        all_items = [dict(preset) for preset in self.presets]
        for item in all_items:
            item["order"] = int(item.get("order") or 0)
        all_items.sort(key=lambda item: item["order"])
        ids = [item["id"] for item in all_items]
        if preset_id not in ids:
            self._set_error("预设不存在")
            return False

        current = ids.index(preset_id)
        bounded = max(0, min(len(ids) - 1, int(target_index)))
        if current == bounded:
            return True
        ids.insert(bounded, ids.pop(current))

        if not self._manager.reorder_presets(ids):
            self._set_error("调整顺序失败")
            return False
        self._set_error("")
        self.presetsChanged.emit()
        self.viewChanged.emit()
        return True

    @Slot(str, int, result=bool)
    def setCoverDocument(self, preset_id: str, cover_index: int) -> bool:
        """指定多标签预设的封面页，并强制重生成缩略图。"""
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False
        if not self._manager.set_cover_index(preset_id, int(cover_index)):
            self._set_error("设置封面失败")
            return False
        # 封面变了，旧缩略图和缺失探测都失效
        self._missing_cache.pop(preset_id, None)
        self._set_error("")
        self._thumbnail_service().request(
            preset_id, force=True, cover_index=int(cover_index)
        )
        self.presetsChanged.emit()
        self.viewChanged.emit()
        return True

    @Slot(str, result=int)
    def deleteCategory(self, category: str) -> int:
        """删除分类：成员归回「未分类」，返回受影响数量。不删预设本身。"""
        name = str(category or "").strip()
        if not name or name == "未分类":
            self._set_error("「未分类」不能删除")
            return 0
        affected = int(self._manager.delete_category(name) or 0)
        if affected <= 0:
            self._set_error("该分类下没有预设")
            return 0
        # 正停在被删分类上时退回全部视图，否则会停在空列表
        if self._category == name:
            self._category = ""
        self._set_error("")
        self.presetsChanged.emit()
        self.viewChanged.emit()
        return affected

    # ---- 分类与标签 ----

    @Slot(str, str, result=bool)
    def setPresetCategory(self, preset_id: str, category: str) -> bool:
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False
        if not self._manager.set_category(preset_id, category):
            self._set_error("更新分类失败")
            return False
        self._set_error("")
        self.presetsChanged.emit()
        self.viewChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def setPresetTags(self, preset_id: str, tags_text: str) -> bool:
        """标签以逗号分隔的文本传入（中英文逗号都支持）。"""
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False
        raw = str(tags_text or "").replace("，", ",")
        tags = [part.strip() for part in raw.split(",") if part.strip()]
        if not self._manager.set_tags(preset_id, tags):
            self._set_error("更新标签失败")
            return False
        self._set_error("")
        self.presetsChanged.emit()
        self.viewChanged.emit()
        return True

    @Slot(str, str, result=int)
    def renameCategory(self, old_name: str, new_name: str) -> int:
        """重命名分类，返回受影响的预设数量。"""
        new_name = str(new_name or "").strip()
        if not new_name:
            self._set_error("分类名不能为空")
            return 0
        affected = int(self._manager.rename_category(old_name, new_name) or 0)
        if affected <= 0:
            self._set_error("重命名分类失败")
            return 0
        # 当前正停在旧分类上时，跟随改到新名字，否则左栏会突然「空掉」
        if self._category == str(old_name or "").strip():
            self._category = new_name
        self._set_error("")
        self.presetsChanged.emit()
        self.viewChanged.emit()
        return affected

    # ---- 缩略图 ----

    def _thumbnail_service(self):
        if self._thumb_service is None:
            self._thumb_service = get_thumbnail_service(self._manager.presets_dir)
            self._thumb_service.add_listener(self._on_thumbnail_ready)
        return self._thumb_service

    def _on_thumbnail_ready(self, preset_id: str, thumb_path: str) -> None:
        """后台渲染完成回调（在工作线程里执行）。

        不在这里碰 Qt 模型或写索引——跨线程改 QObject 状态会崩。统一投递到
        对象所属线程（主线程）再处理。

        注意：本方法可能在工作线程里被调用，而应用退出/VM 析构随时发生。
        一旦 C++ 对象已销毁，访问 ``self._pending_thumbs`` 或 invokeMethod
        都会抛 "Internal C++ object already deleted"，所以先做存活检测。
        """
        if self._shutdown_flag:
            return
        try:
            # shiboken 在对象已销毁时 isdeleted 为 True
            if shiboken6.isValid(self) is False:
                return
        except Exception:  # noqa: BLE001 - 无 shiboken 时退化为不做检测
            pass
        try:
            self._pending_thumbs[str(preset_id)] = str(thumb_path)
            QMetaObject.invokeMethod(
                self, "_applyReadyThumbnails", Qt.QueuedConnection
            )
        except RuntimeError:
            # 对象在检测与调用之间被销毁，安静退出
            return

    @Slot()
    def _applyReadyThumbnails(self) -> None:
        """主线程消费后台已生成的缩略图路径。

        判定「需要刷新」不看 ``set_thumbnail_path`` 的返回值——索引里可能早就
        记过同一路径，但缩略图文件是刚重算出来的（mtime 变了），卡片仍然要换图。
        统一用「本次事件里有任何缩略图就绪」作为刷新条件。
        """
        if not self._pending_thumbs:
            return
        pending = dict(self._pending_thumbs)
        self._pending_thumbs.clear()
        for preset_id, thumb_path in pending.items():
            try:
                self._manager.set_thumbnail_path(preset_id, thumb_path)
            except Exception:  # noqa: BLE001 - 落库失败不影响显示
                pass
            self.thumbnailReady.emit(preset_id)
        self.presetsChanged.emit()
        # visiblePresets 只监听 viewChanged；缩略图就绪后必须让卡片拿到新的
        # thumbnailUrl，否则出现「磁盘已有图、界面仍显示骨架」。
        self.viewChanged.emit()

    @Slot(str)
    def requestThumbnail(self, preset_id: str, force: bool = False) -> None:
        """请求某预设的缩略图（命中缓存立即返回，否则入后台队列）。"""
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            return
        cover = 0
        for preset in self._manager.get_all_presets():
            if str(preset.get("id") or "") == preset_id:
                cover = int(preset.get("cover_index") or 0)
                break
        self._thumbnail_service().request(preset_id, force=force, cover_index=cover)

    @Slot(result=int)
    def requestAllThumbnails(self) -> int:
        """给当前可见列表批量请求缩略图，返回本次入队数量。"""
        service = self._thumbnail_service()
        missing = [
            item["id"] for item in self._sorted_presets() if not item["thumbnailUrl"]
        ]
        return service.request_many(missing)

    @Slot(result=int)
    def pendingThumbnailCount(self) -> int:
        if self._thumb_service is None:
            return 0
        return self._thumb_service.pending_count()

    def shutdown(self) -> None:
        """断开缩略图订阅（VM 销毁或应用退出时调用）。"""
        self._shutdown_flag = True
        if self._thumb_service is not None:
            try:
                self._thumb_service.remove_listener(self._on_thumbnail_ready)
            except Exception:  # noqa: BLE001
                pass
            self._thumb_service = None
