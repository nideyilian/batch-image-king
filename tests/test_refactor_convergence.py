"""R5–R8 收敛重构的回归测试（纯逻辑，无 GUI）。

覆盖：
- R5：``DocumentRenderer`` 已删除，渲染唯一出口为 ``RenderService``。
- R6：死代码 ``advanced_blending`` 已删除，``app.utils.image`` 仍可被通配导入。
- R7：``safe_print`` 是内置 ``print`` 的 drop-in（支持 file=/sep=/end=/flush=）。
- R8：``Layer = NewLayer`` 别名已从 ``document`` 移除，规范来源为 ``layer_new.Layer``。
"""
import io
import sys

import pytest


@pytest.mark.unit
def test_r5_document_renderer_deleted():
    """R5：旧渲染器模块应已删除，不再可导入。"""
    with pytest.raises(ImportError):
        import app.models.document_renderer  # noqa: F401
    # 渲染唯一出口仍可用
    from app.services.render_service import RenderService
    assert RenderService is not None


@pytest.mark.unit
def test_r6_advanced_blending_deleted():
    """R6：死代码 advanced_blending 已删除，image 包仍可通配导入。"""
    with pytest.raises(ImportError):
        import app.utils.advanced_blending  # noqa: F401
    # 删除通配重导出行后，image 包仍应可正常导入
    import app.utils.image  # noqa: F401


@pytest.mark.unit
def test_r7_safe_print_is_print_dropin():
    """R7：safe_print 支持与内置 print 一致的 *args / file / sep / end / flush。"""
    from app.utils.print_utils import safe_print

    buf = io.StringIO()
    # 含关键字「失败」-> 默认会输出；验证 file=/sep=/end=/flush= 都生效
    safe_print("失败a", "失败b", sep="-", end="!", file=buf, flush=True)
    assert buf.getvalue() == "失败a-失败b!"

    # 普通调试信息（无关键字）默认被抑制
    buf2 = io.StringIO()
    safe_print("普通调试信息", file=buf2)
    assert buf2.getvalue() == ""

    # 与内置 print 一样支持 file=sys.stderr 而不抛 TypeError（修复 export_worker 回归）
    err = io.StringIO()
    safe_print("渲染失败: boom", file=err)
    assert "渲染失败: boom" in err.getvalue()

    # 无参数调用不应抛异常
    safe_print()


@pytest.mark.unit
def test_r8_layer_alias_removed():
    """R8：document 的 Layer 别名已移除，规范来源为 layer_new.Layer。"""
    # 规范来源仍可用，且为图层类
    from app.models.layer_new import Layer as CanonicalLayer
    assert CanonicalLayer is not None

    # document 仍导出 NewLayer（其工作名）
    from app.models.document import NewLayer
    assert NewLayer is CanonicalLayer

    # document 不再暴露 Layer 别名
    with pytest.raises(ImportError):
        from app.models.document import Layer  # noqa: F401


@pytest.mark.unit
def test_r8_ui_consumers_redirected_to_layer_new():
    """R8：两个 UI 消费者已重定向到 layer_new.Layer，导入不报错。"""
    import app.ui.add_layer_dialog  # noqa: F401
    import app.ui.layer_properties_attr  # noqa: F401
