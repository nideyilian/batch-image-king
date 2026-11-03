"""验证缩略图取消接口：取消后不写回、能重新请求、代数不串。

跑法：python -u docs/audit/_verify_thumb_cancel.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402

app = QCoreApplication.instance() or QCoreApplication(sys.argv)

from app.models.document import Document  # noqa: E402
from app.utils.preset_manager import PresetManager  # noqa: E402
from app.utils.preset_thumbnail import (  # noqa: E402
    PresetThumbnailService,
    thumb_path_for,
)

_passed = 0
_failed = 0


def check(name, ok, detail=""):
    global _passed, _failed
    if ok:
        _passed += 1
        print(f"PASS  {name}")
    else:
        _failed += 1
        print(f"FAIL  {name}   {detail}")


def _doc(name, color, x=10):
    doc = Document()
    doc.create_new(400, 300)
    doc.tab_name = name
    doc.original_tab_name = name
    path = os.path.join(WORK, f"{name}.png")
    Image.new("RGBA", (240, 180), color).save(path)
    doc.add_layer("L0", x, 20, 200, 150, image_source=path)
    return doc


WORK = tempfile.mkdtemp()
manager = PresetManager(app_dir=WORK, copy_initial=False)
presets_dir = manager.presets_dir

# 造一个 4 页预设（多页才能观察"取消后不再继续渲染后面几页"）
pages = [_doc(f"p{i}", (40 * i, 100, 160, 255)) for i in range(4)]
preset_id = manager.save_preset_documents("取消演示", "", pages)
assert preset_id

thumb0 = thumb_path_for(presets_dir, preset_id, 0)
print(f"预设 {preset_id}  缩略图 {thumb0}")

service = PresetThumbnailService(presets_dir)
done = threading.Event()
notified: list[str] = []


def on_done(pid, path):
    if pid == preset_id:
        notified.append(path)
        done.set()


service.add_listener(on_done)

# ---------------- 场景 1：取消一个还没跑的任务 ----------------
service.request(preset_id)
ok = service.cancel(preset_id)
check("cancel 返回 True（确实有待处理任务）", ok is True, str(ok))
check("cancel 后 pending 归零", service.pending_count() == 0, str(service.pending_count()))
check("cancel 幂等（再调一次不报错）", service.cancel(preset_id) is False)

# 等足够久，确认工作线程即使消费了队列项也不会落盘
time.sleep(2.5)
check("取消后没有写回缩略图文件", not os.path.isfile(thumb0), thumb0)
check("取消后没有回调 UI", notified == [], str(notified))

# ---------------- 场景 2：取消后重新请求仍然能正常出图 ----------------
# 这是最容易被"布尔标记"实现搞坏的地方：旧队列项还没消费完，
# 新请求进来后旧任务结束时会误清新任务的 pending。
service.request(preset_id, force=True)
check("重新请求后 pending=1", service.pending_count() == 1, str(service.pending_count()))
got = done.wait(timeout=30)
check("重新请求最终出图", got and os.path.isfile(thumb0), f"got={got} exists={os.path.isfile(thumb0)}")
if os.path.isfile(thumb0):
    with Image.open(thumb0) as im:
        check("缩略图内容有效", im.size[0] > 0, str(im.size))

# ---------------- 场景 3：渲染途中取消，落盘前被拦下 ----------------
# ⚠️ 不能靠 sleep 猜时机：纯色图层渲染可能只要 20ms，sleep 0.08s 时前几页
# 早就落盘了，会误判成"取消无效"。这里给渲染注入延迟，制造确定的窗口。
import app.services.render_service as _rs  # noqa: E402

_original_render = _rs.render_document_to_image


def _slow_render(*args, **kwargs):
    time.sleep(0.45)
    return _original_render(*args, **kwargs)


_rs.render_document_to_image = _slow_render
os.remove(thumb0)
notified.clear()
done.clear()
service.request(preset_id, force=True)
time.sleep(0.15)  # 第一页正在渲染中
service.cancel(preset_id)
time.sleep(2.5)
check("渲染途中取消 → 不落盘", not os.path.isfile(thumb0), thumb0)
check("渲染途中取消 → 不回调", notified == [], str(notified))
_rs.render_document_to_image = _original_render

# ---------------- 场景 3b：逐页中断的精确语义 ----------------
# 直接测渲染函数：传一个"第 2 次检查返回 True"的钩子，
# 确认它只渲染第 1 页就停下、且返回空（不把半批结果给调用方）。
from app.utils.preset_thumbnail import render_preset_thumbnails  # noqa: E402

for p in range(6):
    path = thumb_path_for(presets_dir, preset_id, p)
    if os.path.isfile(path):
        os.remove(path)

calls = {"n": 0}


def _cancel_after_first():
    calls["n"] += 1
    return calls["n"] > 1  # 第一次放行，之后都取消


out = render_preset_thumbnails(
    preset_id, presets_dir, source_path=os.path.join(presets_dir, f"{preset_id}.cmp"),
    should_cancel=_cancel_after_first,
)
check("逐页中断：返回空 dict（不返回半批结果）", out == {}, str(out))
check("逐页中断：确实检查了多次（不是一次就结束）", calls["n"] >= 2, str(calls["n"]))

# ---------------- 场景 4：cancel_all ----------------
notified.clear()
done.clear()
service.request(preset_id, force=True)
n = service.cancel_all()
check("cancel_all 返回取消数量", n >= 1, str(n))
check("cancel_all 后 pending 归零", service.pending_count() == 0, str(service.pending_count()))
time.sleep(2.0)

# ---------------- 场景 5：正常路径不受影响 ----------------
notified.clear()
done.clear()
service.request(preset_id, force=True)
got = done.wait(timeout=30)
check("未经取消时正常出图", got and os.path.isfile(thumb0))
check("正常路径 pending 归零", service.pending_count() == 0, str(service.pending_count()))

service.stop()

print()
print(f"总结：{_passed} passed, {_failed} failed")
sys.exit(0 if _failed == 0 else 1)
