"""集成测试基线：端到端渲染 + 导出。

这条测试是“可跑的集成测试基线”的核心产物，覆盖跨模块协作：
    Document 模型 -> 图片图层 -> DocumentRenderer / FastRenderer 渲染
    -> ExportService 写盘

它不依赖任何显示环境（conftest 已强制 offscreen 并提供共享 QApplication），
可稳定运行，用于回归守卫：一旦渲染/导出/序列化任一环节断裂，这里会先亮红灯。

运行方式：
    python -m pytest tests/test_integration_baseline.py -v
    python -m pytest -m integration        # 跑全部集成测试

注：刻意使用 ``tempfile.TemporaryDirectory`` 而非 pytest 的 ``tmp_path``，
以避免本机 Windows 上 pytest 临时目录清理（reparse point）的已知问题。
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.document import Document  # noqa: E402

pytestmark = pytest.mark.integration


def _make_source_image(path: str, color=(255, 0, 0, 255), size=(120, 90)):
    img = Image.new("RGBA", size, color)
    img.save(path)
    return path


def test_end_to_end_render_and_export():
    """构建文档、加图片图层、渲染、导出 PNG，验证整条管线闭环。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        doc = Document()
        doc.canvas_width = 400
        doc.canvas_height = 300

        src = _make_source_image(os.path.join(tmp, "src.png"))
        layer = doc.add_layer(
            name="base",
            x=40,
            y=30,
            width=120,
            height=90,
            image_source=src,
            use_original_size=True,
            is_folder=False,
        )
        assert layer is not None
        assert len(doc.layers) == 1

        # 1) 渲染：应返回与画布同尺寸的 PIL 图像
        rendered = doc.render_document()
        assert rendered is not None
        assert rendered.size == (400, 300)

        # 2) 导出：应成功写盘且文件非空
        out = os.path.join(tmp, "out.png")
        ok = doc.export_image(out)
        assert ok is True
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0

        # 3) 导出的文件可重新被 Pillow 打开，尺寸正确
        with Image.open(out) as reopened:
            assert reopened.size == (400, 300)


def test_render_returns_none_for_invalid_canvas():
    """画布尺寸非法时渲染应安全返回 None，而不是抛异常（容错基线）。"""
    doc = Document()
    doc.canvas_width = 0
    doc.canvas_height = 0
    assert doc.render_document() is None
