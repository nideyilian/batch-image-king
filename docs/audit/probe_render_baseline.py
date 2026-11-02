# -*- coding: utf-8 -*-
"""render_composition 行为基线：重构前后必须逐像素一致。

拆 734 行大函数最大的风险是"拆完行为变了"。这里把各种场景的输出
存成指纹（尺寸 + 像素哈希），重构前后各跑一次比对。

覆盖：
  - 空文档 / 单图层 / 多图层叠加
  - 混合模式、透明度、可见性
  - 文字图层（含范围色）
  - 高级合成路径（use_advanced_quality=True）
  - 分身效果 grid / border 两种布局
  - random_mode（固定种子保证可复现）
  - optimize_memory
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

BASELINE_PATH = os.path.join(REPO, "docs", "audit", "render_composition_baseline.json")


def _fingerprint(image) -> dict:
    if image is None:
        return {"null": True}
    rgba = image.convert("RGBA")
    data = rgba.tobytes()
    # 采样若干行做稳定性校验（避免整图哈希掩盖局部差异）
    return {
        "size": list(rgba.size),
        "md5": hashlib.md5(data).hexdigest(),
        "nontransparent": sum(1 for a in rgba.getchannel("A").getdata() if a > 8),
    }


def _make_source(tmpdir: str) -> str:
    from PIL import Image

    path = os.path.join(tmpdir, "src.png")
    if not os.path.exists(path):
        image = Image.new("RGBA", (240, 180))
        px = image.load()
        for y in range(180):
            for x in range(240):
                px[x, y] = (200, 40 + (y % 100), 60, 255 if x < 200 else 120)
        image.save(path)
    return path


def build_scenarios(tmpdir: str):
    """返回 [(名称, 构造函数)]，构造函数返回 (document, 调用参数)。"""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from app.models.document import Document
    from app.models.text_layer import TextLayer

    src = _make_source(tmpdir)

    def scenario_empty():
        doc = Document()
        doc.create_new(400, 300)
        return doc, {}

    def scenario_single():
        doc = Document()
        doc.create_new(400, 300)
        doc.add_layer("a", 40, 30, 240, 180, image_source=src, is_folder=False)
        return doc, {}

    def scenario_overlap_blend():
        doc = Document()
        doc.create_new(400, 300)
        doc.add_layer("a", 20, 20, 240, 180, image_source=src, is_folder=False)
        doc.add_layer("b", 100, 80, 240, 180, image_source=src, is_folder=False)
        doc.layers[1].opacity = 60
        doc.layers[1].blend_mode = 3
        return doc, {}

    def scenario_hidden():
        doc = Document()
        doc.create_new(400, 300)
        doc.add_layer("a", 20, 20, 240, 180, image_source=src, is_folder=False)
        doc.add_layer("b", 100, 80, 240, 180, image_source=src, is_folder=False)
        doc.layers[1].visible = False
        return doc, {}

    def scenario_text():
        doc = Document()
        doc.create_new(400, 300)
        doc.add_layer("a", 0, 0, 400, 300, image_source=src, is_folder=False)
        text = TextLayer(name="标题")
        text.set_current_text("测试文字", force=True)
        text.font_size = 40
        text.x = 40
        text.y = 100
        text.width = 300
        text.height = 80
        doc.add_text_layer(text)
        return doc, {}

    def scenario_advanced():
        doc = Document()
        doc.create_new(400, 300)
        doc.add_layer("a", 20, 20, 240, 180, image_source=src, is_folder=False)
        doc.add_layer("b", 100, 80, 240, 180, image_source=src, is_folder=False)
        return doc, {"use_advanced_quality": True}

    def scenario_clone_grid():
        doc = Document()
        doc.create_new(600, 500)
        doc.add_layer("a", 0, 0, 200, 150, image_source=src, is_folder=False)
        layer = doc.layers[0]
        for attr, value in (
            ("clone_enabled", True),
            ("clone_mode", "grid"),
            ("clone_rows", 2),
            ("clone_cols", 3),
            ("clone_spacing_x", 10),
            ("clone_spacing_y", 10),
        ):
            if hasattr(layer, attr):
                setattr(layer, attr, value)
        return doc, {}

    def scenario_clone_border():
        doc = Document()
        doc.create_new(600, 500)
        doc.add_layer("a", 0, 0, 160, 120, image_source=src, is_folder=False)
        layer = doc.layers[0]
        for attr, value in (
            ("clone_enabled", True),
            ("clone_mode", "border"),
            ("clone_margin", 20),
        ):
            if hasattr(layer, attr):
                setattr(layer, attr, value)
        return doc, {}

    def scenario_random_mode():
        import random

        doc = Document()
        doc.create_new(400, 300)
        doc.add_layer("a", 20, 20, 240, 180, image_source=src, is_folder=False)
        random.seed(12345)
        return doc, {"random_mode": True}

    def scenario_batch_mode():
        doc = Document()
        doc.create_new(400, 300)
        doc.add_layer("a", 20, 20, 240, 180, image_source=src, is_folder=False)
        doc.add_layer("b", 100, 80, 240, 180, image_source=src, is_folder=False)
        return doc, {"is_batch_mode": True}

    def scenario_optimize_memory():
        doc = Document()
        doc.create_new(400, 300)
        doc.add_layer("a", 20, 20, 240, 180, image_source=src, is_folder=False)
        return doc, {"optimize_memory": True}

    return [
        ("empty", scenario_empty),
        ("single", scenario_single),
        ("overlap_blend", scenario_overlap_blend),
        ("hidden", scenario_hidden),
        ("text", scenario_text),
        ("advanced", scenario_advanced),
        ("clone_grid", scenario_clone_grid),
        ("clone_border", scenario_clone_border),
        ("random_mode", scenario_random_mode),
        ("batch_mode", scenario_batch_mode),
        ("optimize_memory", scenario_optimize_memory),
    ]


def run() -> dict:
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix="rcbase_")
    results = {}
    for name, build in build_scenarios(tmpdir):
        try:
            doc, kwargs = build()
            image = doc.render_composition(**kwargs)
            results[name] = _fingerprint(image)
        except Exception as error:  # noqa: BLE001
            results[name] = {"error": f"{type(error).__name__}: {error}"}
    return results


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "record"
    current = run()

    if mode == "record":
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
            json.dump(current, handle, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"已记录 {len(current)} 个场景的基线 → {BASELINE_PATH}")
        for name, info in sorted(current.items()):
            if "error" in info:
                print(f"  {name:<18} ERROR {info['error'][:60]}")
            elif info.get("null"):
                print(f"  {name:<18} None")
            else:
                print(f"  {name:<18} {info['size']}  非透明={info['nontransparent']:6d}  md5={info['md5'][:12]}")
        return 0

    with open(BASELINE_PATH, encoding="utf-8") as handle:
        saved = json.load(handle)

    ok = True
    for name in sorted(saved):
        want = saved[name]
        got = current.get(name, {})
        if want == got:
            print(f"  OK   {name}")
            continue
        ok = False
        print(f"  DIFF {name}")
        print(f"       基线: {want}")
        print(f"       现在: {got}")
    print()
    print("结论:", "全部一致" if ok else "存在差异，重构改变了行为")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
