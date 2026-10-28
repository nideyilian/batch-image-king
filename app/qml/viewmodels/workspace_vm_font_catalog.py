"""WorkspaceViewModel 字体目录与最近字体基础设施 mixin（P1-4 拆分）。

从 ``workspace_view_model.py`` 原样迁出的字体目录扫描/回退/最近字体持久化方法组，
语义不变。QML 侧的 ``@Property`` getter（textFontOptions 等）留在主类，
经 ``self`` 调用本 mixin 方法。
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication

logger = logging.getLogger(__name__)


def _is_alive(obj) -> bool:
    """判断 QObject 的 C++ 侧是否仍存活。

    后台线程收尾时应用程序可能已经在退出，此时对象已被销毁；
    对销毁后的对象 emit 信号会抛 RuntimeError。
    """
    try:
        from shiboken6 import isValid

        return bool(isValid(obj))
    except Exception:
        # 拿不到 shiboken 就宁可直接发：漏掉一次保护好过吞掉正常信号
        return True


class WorkspaceFontCatalogMixin:
    def _load_text_font_names(self, layer):
        try:
            categories = layer.get_categorized_fonts()
            font_names = []
            seen = set()
            for category in ("chinese", "english", "monospace", "decorative", "other"):
                for name in categories.get(category, []) or []:
                    key = str(name or "").strip().casefold()
                    if key and key not in seen:
                        seen.add(key)
                        font_names.append(name)
            if font_names:
                return font_names
        except Exception:
            logger.debug("加载文字图层中文字体目录失败，回退 Qt 字体库", exc_info=True)
        if QGuiApplication.instance() is not None:
            try:
                writing_system = QFontDatabase.WritingSystem
                font_names = []
                seen = set()
                for name in QFontDatabase.families():
                    key = str(name or "").strip().casefold()
                    if key and key not in seen:
                        seen.add(key)
                        font_names.append(name)
                return font_names
            except Exception:
                logger.debug("从 Qt 字体库加载中文字体失败", exc_info=True)
        return []

    def _font_catalog_layer(self):
        if self.selectedIsTextLayer:
            return self._selected_layer()
        from app.models.text_layer import TextLayer

        return TextLayer()

    def _load_text_font_options(self, layer=None):
        if layer is None:
            layer = self._font_catalog_layer()
        try:
            font_names = self._load_text_font_names(layer)
        except Exception:
            logger.debug("构建本地字体选项失败", exc_info=True)
            font_names = []
        try:
            chinese_names = layer.get_font_cn_names()
        except Exception:
            logger.debug("读取本地字体中文名映射失败", exc_info=True)
            chinese_names = {}
        fallbacks = [
            "Microsoft YaHei",
            "SimHei",
            "SimSun",
            "KaiTi",
            "FangSong",
        ]
        options = [{"label": "sans-serif", "value": "sans-serif"}]
        seen = {"sans-serif"}
        current_family = str(getattr(layer, "font_family", "") or "").strip()
        names = list(font_names or []) or fallbacks
        if current_family and current_family.casefold() not in {
            str(name or "").strip().casefold() for name in names
        }:
            names.insert(0, current_family)
        for name in names:
            family = str(name or "").strip()
            key = family.casefold()
            if not family or key in seen:
                continue
            seen.add(key)
            chinese_name = str(chinese_names.get(family, "") or "").strip()
            label = f"{chinese_name} ({family})" if chinese_name and chinese_name != family else family
            options.append({"label": label, "value": family})
        return options

    @staticmethod
    def _font_face_label(style: str) -> str:
        normalized = str(style or "Regular").strip()
        key = normalized.casefold().replace("-", " ").replace("_", " ")
        italic = "italic" in key or "oblique" in key or "slanted" in key
        if "extra light" in key or "extralight" in key or "ultra light" in key:
            label = "特细"
        elif "thin" in key or "hairline" in key:
            label = "极细"
        elif "light" in key:
            label = "细体"
        elif "medium" in key:
            label = "中等"
        elif "semi bold" in key or "semibold" in key or "demi bold" in key:
            label = "半粗体"
        elif "extra bold" in key or "extrabold" in key or "ultra bold" in key:
            label = "特粗"
        elif "black" in key or "heavy" in key:
            label = "黑体"
        elif "bold" in key:
            label = "粗体"
        else:
            label = "常规"
        return f"{label} 斜体" if italic and "italic" not in label else label

    def _load_text_font_tree_options(self, layer=None):
        if layer is None:
            layer = self._font_catalog_layer()
        try:
            faces_by_family = layer.get_font_faces()
        except Exception:
            logger.debug("构建字体字重目录失败", exc_info=True)
            faces_by_family = {}
        chinese_names = {}
        try:
            chinese_names = layer.get_font_cn_names()
        except Exception:
            logger.debug("读取字体中文名失败", exc_info=True)

        options = self._load_text_font_options(layer)
        groups = []
        for family_option in options:
            family = str(family_option.get("value", "") or "").strip()
            if not family:
                continue
            resolved_family = (
                layer._resolve_font_family(family)
                if hasattr(layer, "_resolve_font_family")
                else family
            )
            faces = []
            for face in faces_by_family.get(resolved_family, []) or []:
                style = str(face.get("style", "Regular") or "Regular").strip()
                faces.append({
                    "label": self._font_face_label(style),
                    "value": style,
                    "face": style,
                    "family": family,
                    "weight": int(face.get("weight", 400) or 400),
                    "italic": bool(face.get("italic", False)),
                    "synthetic": False,
                })
            if not faces:
                faces = [{
                    "label": "常规",
                    "value": "Regular",
                    "face": "Regular",
                    "family": family,
                    "weight": 400,
                    "italic": False,
                    "synthetic": True,
                }]
            faces.sort(key=lambda item: (item["weight"], item["italic"], item["value"].casefold()))
            groups.append({
                "label": str(chinese_names.get(family, "") or family),
                "value": family,
                "family": family,
                "children": faces,
            })
        return groups

    def _font_catalog_fallback_options(self):
        current = str(getattr(self._selected_layer(), "font_family", "") or "").strip()
        families = [
            current,
            "sans-serif",
            "Microsoft YaHei",
            "SimHei",
            "SimSun",
            "KaiTi",
            "FangSong",
        ]
        options = []
        seen = set()
        for family in families:
            family = str(family or "").strip()
            key = family.casefold()
            if not family or key in seen:
                continue
            seen.add(key)
            options.append({"label": family, "value": family})
        return options

    def _font_catalog_fallback_tree(self):
        current_family = str(getattr(self._selected_layer(), "font_family", "") or "").strip()
        current_face = str(getattr(self._selected_layer(), "font_face", "") or "Regular").strip()
        groups = []
        for option in self._font_catalog_fallback_options():
            family = option["value"]
            face = current_face if family.casefold() == current_family.casefold() else "Regular"
            groups.append(
                {
                    "label": option["label"],
                    "value": family,
                    "family": family,
                    "children": [
                        {
                            "label": self._font_face_label(face),
                            "value": face,
                            "face": face,
                            "family": family,
                            "weight": 400,
                            "italic": False,
                            "synthetic": True,
                        }
                    ],
                }
            )
        return groups

    def startFontCatalogPreload(self):
        if self._font_catalog_loading or self._text_font_tree_options_cache is not None:
            return
        self._font_catalog_loading = True
        threading.Thread(
            target=self._font_catalog_worker,
            name="QmlFontCatalog",
            daemon=True,
        ).start()

    @Slot()
    def enableDeferredFontCatalogPreload(self) -> None:
        """允许首屏完成后启动字体目录预加载。"""
        self._defer_font_catalog_preload = False
        self.startFontCatalogPreload()

    def _font_catalog_worker(self):
        options = []
        tree = []
        try:
            from app.models.text_layer import TextLayer

            # 直接用 TextLayer：其 _fonts_cache_file 已通过 property 默认指向用户数据目录，
            # 且具备字体扫描、文件缓存读写、跨实例全局缓存等完整能力。
            try:
                scanner = TextLayer()
            except Exception:
                # TextLayer 初始化需要 QObject 环境；极端失败时退回到 mixin 手动构造
                from app.models.text_layer_font import TextLayerFontMixin
                scanner = TextLayerFontMixin()

            options = self._load_text_font_options(scanner)
            tree = self._load_text_font_tree_options(scanner)

            # 若 mixin 扫描结果为空（例如文件缓存+全局缓存都失效且扫描异常），
            # 尝试回退到 Qt 自带 QFontDatabase 作为兜底，保证 UI 至少有一套系统字体列表
            # （避免 fallback 只有 6~7 个字体，让用户误以为"程序识别不到字体"）。
            if not options:
                try:
                    from PySide6.QtGui import QGuiApplication, QFontDatabase
                    if QGuiApplication.instance() is not None:
                        families = list(QFontDatabase.families())
                        if families:
                            layer_obj = scanner
                            names = list(dict.fromkeys(families))  # 保序去重
                            current_family = ""
                            try:
                                current_family = str(
                                    getattr(self._selected_layer(), "font_family", "") or ""
                                ).strip()
                            except Exception:
                                current_family = ""
                            if current_family and current_family.casefold() not in {
                                str(n or "").strip().casefold() for n in names
                            }:
                                names.insert(0, current_family)
                            opts_qt = [{"label": "sans-serif", "value": "sans-serif"}]
                            seen_qt = {"sans-serif"}
                            chinese_names = {}
                            try:
                                chinese_names = layer_obj.get_font_cn_names()
                            except Exception:
                                chinese_names = {}
                            for name in names:
                                family = str(name or "").strip()
                                key = family.casefold()
                                if not family or key in seen_qt:
                                    continue
                                seen_qt.add(key)
                                cn = str(chinese_names.get(family, "") or "").strip()
                                label = (
                                    f"{cn} ({family})"
                                    if cn and cn != family
                                    else family
                                )
                                opts_qt.append({"label": label, "value": family})
                            if opts_qt:
                                options = opts_qt
                                # tree 重算基于新 options
                                tree_qt = []
                                try:
                                    faces_by_family = layer_obj.get_font_faces()
                                except Exception:
                                    faces_by_family = {}
                                for opt in options:
                                    fam = str(opt.get("value", "") or "").strip()
                                    if not fam:
                                        continue
                                    faces = []
                                    for face in faces_by_family.get(fam, []) or []:
                                        style = str(face.get("style", "Regular") or "Regular").strip()
                                        faces.append({
                                            "label": self._font_face_label(style),
                                            "value": style,
                                            "face": style,
                                            "family": fam,
                                            "weight": int(face.get("weight", 400) or 400),
                                            "italic": bool(face.get("italic", False)),
                                            "synthetic": False,
                                        })
                                    if not faces:
                                        faces.append({
                                            "label": "常规",
                                            "value": "Regular",
                                            "face": "Regular",
                                            "family": fam,
                                            "weight": 400,
                                            "italic": False,
                                            "synthetic": True,
                                        })
                                    faces.sort(key=lambda it: (it["weight"], it["italic"], it["value"].casefold()))
                                    cn = str(chinese_names.get(fam, "") or fam or fam)
                                    tree_qt.append({
                                        "label": cn,
                                        "value": fam,
                                        "family": fam,
                                        "children": faces,
                                    })
                                if tree_qt:
                                    tree = tree_qt
                except Exception:
                    logger.debug("字体 catalog Qt 兜底失败", exc_info=True)
        except Exception:
            logger.debug("后台预加载字体目录失败", exc_info=True)
        # 线程是 daemon，进程退出时不会等它；如果此时 C++ 对象已经销毁，
        # emit 会抛 `RuntimeError: Signal source has been deleted`。
        # 每次退出都往日志里打两段红色 traceback，看起来像严重故障，
        # 实际只是收尾竞态。这里先确认对象还活着。
        if not _is_alive(self):
            return
        self._fontCatalogLoaded.emit(options, tree)

    @Slot(object, object)
    def _on_font_catalog_loaded(self, options, tree):
        self._font_catalog_loading = False
        # 即使为空也要写缓存，避免"每次访问 textFontOptions 都重新启动扫描线程
        # → 每次都失败又不填 cache → 永陷 fallback"的循环。
        if options is not None:
            self._text_font_options_cache = list(options)
        if tree is not None:
            self._text_font_tree_options_cache = list(tree)
        # 最近字体变更会影响 textFontTreeOptions 顶端"最近使用"分组，这里清 token
        self._text_font_tree_with_recent_cache_token = None
        self.fontCatalogChanged.emit()

    # ----------------------------- 最近使用字体 -----------------------------

    def _recent_fonts_file_path(self) -> Path:
        """与经典 UI（integrated_text_panel_content._recent_fonts_file）一致的存储位置。"""
        try:
            base_dir = Path.home()
        except Exception:
            import tempfile
            base_dir = Path(tempfile.gettempdir())
        config_dir = base_dir / ".config" / "批图王"
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return config_dir / "recent_fonts.json"

    def _load_recent_text_fonts(self) -> list:
        if self._recent_text_fonts_cache is not None:
            return list(self._recent_text_fonts_cache)
        entries: list = []
        try:
            file_path = self._recent_fonts_file_path()
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = None
                raw = data.get("recent", []) if isinstance(data, dict) else []
                seen_keys: set = set()
                for item in raw:
                    # 兼容经典 UI 纯 family 字符串条目；兼容新版 {family, face} dict
                    if isinstance(item, str):
                        fam = item.strip()
                        face = ""
                    elif isinstance(item, dict):
                        fam = str(item.get("family", "") or "").strip()
                        face = str(item.get("face", "") or "").strip()
                    else:
                        continue
                    if not fam:
                        continue
                    key = (fam.casefold(), face.casefold())
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    entries.append({"family": fam, "face": face})
                    if len(entries) >= self._recent_text_font_limit:
                        break
        except Exception:
            logger.debug("读取最近字体失败", exc_info=True)
            entries = []
        self._recent_text_fonts_cache = list(entries)
        return list(entries)

    def _save_recent_text_fonts(self, entries: list) -> None:
        try:
            file_path = self._recent_fonts_file_path()
            out = []
            for item in entries:
                if isinstance(item, dict):
                    fam = str(item.get("family", "") or "").strip()
                    face = str(item.get("face", "") or "").strip()
                elif isinstance(item, str):
                    fam = item.strip()
                    face = ""
                else:
                    continue
                if not fam:
                    continue
                # 经典 UI 读 recent_fonts.json 的 data.get("recent", []) 只取字符串 str；
                # 为兼容两端，没有 face 时写纯字符串，有 face 时写 dict（经典 UI 会过滤 dict 条目
                # 但不会崩溃；后续经典 UI 若要支持字重，再升级读取逻辑）。
                if face:
                    out.append({"family": fam, "face": face})
                else:
                    out.append(fam)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"recent": out}, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.debug("写入最近字体失败", exc_info=True)

    def _push_recent_text_font(self, family: str, face: str = "") -> None:
        family = str(family or "").strip()
        face = str(face or "").strip()
        if not family:
            return
        entries = self._load_recent_text_fonts()
        key_match = (family.casefold(), face.casefold())
        new_entries = [e for e in entries if (e["family"].casefold(), e["face"].casefold()) != key_match]
        new_entries.insert(0, {"family": family, "face": face})
        new_entries = new_entries[: self._recent_text_font_limit]
        if new_entries == entries:
            return
        self._recent_text_fonts_cache = list(new_entries)
        # 清树缓存 token 并触发 UI 刷新
        self._text_font_tree_with_recent_cache_token = None
        self._save_recent_text_fonts(new_entries)
        self.recentTextFontsChanged.emit()
        self.fontCatalogChanged.emit()

    def _build_recent_font_tree_group(self) -> list:
        entries = self._load_recent_text_fonts()
        if not entries:
            return []
        # 建立 family→faces 索引；按 entries 顺序为 family 排序
        family_order = []
        families: dict = {}
        for entry in entries:
            fam = str(entry.get("family", "") or "").strip()
            face = str(entry.get("face", "") or "").strip()
            if not fam:
                continue
            key = fam.casefold()
            if key not in families:
                families[key] = {"family": fam, "faces": []}
                family_order.append(key)
            if face and face.casefold() not in {f.casefold() for f in families[key]["faces"]}:
                families[key]["faces"].append(face)

        # 查 family→label 的映射（走字体目录树）
        group_label_lookup: dict = {}
        for group in list(self._text_font_tree_options_cache or []) or []:
            fam = str(group.get("family", "") or group.get("value", "") or "").strip()
            label = str(group.get("label", "") or fam).strip()
            if fam:
                group_label_lookup[fam.casefold()] = label

        # 查 family→face item 的映射，用于复用真实字重 label/weight
        face_lookup: dict = {}
        for group in list(self._text_font_tree_options_cache or []) or []:
            fam = str(group.get("family", "") or group.get("value", "") or "").strip()
            if not fam:
                continue
            for child in group.get("children", []) or []:
                f = str(child.get("face", "") or child.get("value", "") or "").strip()
                if f:
                    face_lookup[(fam.casefold(), f.casefold())] = child

        children = []
        for key in family_order:
            fam_info = families[key]
            fam = fam_info["family"]
            faces = fam_info["faces"] or [""]
            label = group_label_lookup.get(fam.casefold()) or fam
            normalized_children = []
            for face in faces:
                if face:
                    found = face_lookup.get((fam.casefold(), face.casefold()))
                    if found is not None:
                        normalized_children.append(dict(found))
                    else:
                        normalized_children.append({
                            "label": self._font_face_label(face) or face,
                            "value": face,
                            "face": face,
                            "family": fam,
                            "weight": 400,
                            "italic": False,
                            "synthetic": True,
                        })
                else:
                    # 没有 face 信息的条目（经典 UI 字符串），填一个默认 Regular 占位
                    normalized_children.append({
                        "label": self._font_face_label("Regular") or "常规",
                        "value": "Regular",
                        "face": "Regular",
                        "family": fam,
                        "weight": 400,
                        "italic": False,
                        "synthetic": True,
                    })
            if normalized_children:
                children.append({
                    "label": label,
                    "value": fam,
                    "family": fam,
                    "group": "recent",
                    "children": normalized_children,
                })
        if not children:
            return []
        return [{
            "label": "最近使用",
            "value": "__recent__",
            "family": "",
            "group": "__recent_header__",
            "children": [],
            "__recent_block__": True,
        }] + children

    def _selected_font_face(self, family: str = "", face: str = ""):
        family = family or self.selectedTextFontFamily
        face = face or self.selectedTextFontFace
        for group in self.textFontTreeOptions:
            # 跳过最近使用区块：它是真实字体族的"截断副本"（只含用户最近用的 face），
            # 不应用于字重/字重选项/最近 face 查找；否则 Bold-only 的 recent 会让 selectedTextBold
            # / selectedTextFontWeightOptions 只能看到 700，看不到 Light/Regular 等真实字重。
            if bool(group.get("__recent_block__")) or group.get("group") in ("recent", "__recent_header__"):
                continue
            if str(group.get("family", "")).casefold() != str(family).casefold():
                continue
            for item in group.get("children", []) or []:
                if str(item.get("face", "")).casefold() == str(face).casefold():
                    return item
        return None

    def _nearest_font_face(self, bold: bool, italic: bool):
        return self._nearest_font_face_for_weight(700 if bold else 400, italic)

    def _nearest_font_face_for_weight(self, weight: int, italic: bool):
        family = self.selectedTextFontFamily
        candidates = []
        for group in self.textFontTreeOptions:
            if bool(group.get("__recent_block__")) or group.get("group") in ("recent", "__recent_header__"):
                continue
            if str(group.get("family", "")).casefold() == family.casefold():
                candidates = [
                    item for item in (group.get("children", []) or [])
                    if not bool(item.get("synthetic", False))
                ]
                break
        if not candidates:
            return None
        same_italic = [item for item in candidates if bool(item.get("italic")) == bool(italic)]
        if same_italic:
            candidates = same_italic
        target_weight = max(100, min(900, int(weight)))
        return min(candidates, key=lambda item: abs(int(item.get("weight", 400)) - target_weight))

    def _canonical_text_font_family(self, family: str) -> str:
        requested = str(family or "").strip()
        requested_key = requested.casefold()
        for option in self.textFontOptions:
            value = str(option.get("value", "") or "").strip()
            label = str(option.get("label", value) or value).strip()
            aliases = {value.casefold(), label.casefold()}
            suffix = f" ({value})"
            if value and label.endswith(suffix):
                aliases.add(label[:-len(suffix)].strip().casefold())
            if requested_key in aliases:
                return value
        return requested

    def _selected_text_style_name(self) -> str:
        if not self.selectedIsTextLayer:
            return "NORMAL"
        return str(getattr(self._selected_layer(), "font_style", "NORMAL") or "NORMAL").upper()
