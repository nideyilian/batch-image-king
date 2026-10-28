"""ndops 算子契约测试。

背景：项目移除了 scipy 依赖（110MB 安装 / 18.8MB 打包），改用
``app.utils.image.ndops`` 的 numpy 实现。这些算子出现在边缘检测、抗锯齿、
描边生成等渲染路径上，直接影响出图结果，必须有回归保护。

断言的是**与 scipy 的历史行为一致**，不是「结果看起来对」：
scipy 未安装时跳过对照项，但纯 numpy 的自洽性断言始终执行。
"""

from __future__ import annotations

import numpy as np
import pytest

from app.utils.image import ndops

try:
    import scipy.ndimage as ndimage

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


@pytest.fixture(scope="module")
def alpha_field() -> np.ndarray:
    """模拟 alpha 通道：**平坦背景 + 一个硬边矩形**。

    刻意不用随机噪声做背景 —— 噪声会让「平坦区」也充满梯度，
    使方向性断言失去意义。这里用常数 0.2 作背景，矩形内部 1.0，
    再做轻微高斯平滑使边缘过渡自然。
    """
    field = np.full((96, 128), 0.2, dtype=np.float32)
    field[24:72, 32:96] = 1.0
    if HAS_SCIPY:
        field = ndimage.gaussian_filter(field, 2.0)
    return field


@pytest.fixture(scope="module")
def noisy_field() -> np.ndarray:
    """平坦场 + 两个孤立的椒盐噪声点，用于中值滤波测试。"""
    field = np.full((32, 32), 0.5, dtype=np.float32)
    field[10, 10] = 0.0
    field[20, 20] = 1.0
    return field


def test_sobel_shape_and_dtype(alpha_field):
    got = ndops.sobel(alpha_field, axis=1)
    assert got.shape == alpha_field.shape
    assert got.dtype == np.float64


def test_sobel_detects_horizontal_edge(alpha_field):
    """竖直边界处 axis=1 方向梯度显著；平坦内部区域梯度应接近 0。

    基准取画面中部远离矩形的平坦区（常数 0.2 区域），不取画面最外圈 ——
    reflect 边界填充会让边界行梯度偏大，那是模式约定而非缺陷。
    """
    grad_x = ndops.sobel(alpha_field, axis=1)
    edge_strength = np.abs(grad_x[24:72, 30:34]).max()
    flat_strength = np.abs(grad_x[5:20, 105:125]).max()
    assert edge_strength > 0.1
    assert flat_strength < 0.01, f"平坦区不应有明显梯度，实测 {flat_strength}"
    assert edge_strength > flat_strength * 10


def test_sobel_axis_swap_matches_transpose(alpha_field):
    """沿 axis=1 的梯度，应等于转置后沿 axis=0 的梯度再转置回来。"""
    grad_cols = ndops.sobel(alpha_field, axis=1)
    grad_rows_transposed = ndops.sobel(alpha_field.T, axis=0).T
    np.testing.assert_allclose(grad_cols, grad_rows_transposed, atol=1e-12)


def test_laplace_sums_to_zero_kernel(alpha_field):
    """拉普拉斯核权重和为 0：常数场应得到 0。"""
    constant = np.full((16, 16), 0.37)
    np.testing.assert_allclose(ndops.laplace(constant), 0.0, atol=1e-12)


def test_median_filter_removes_salt_noise(noisy_field):
    """孤立噪声点应被邻域中值取代。

    背景是常数 0.5，邻域中值为 0.5，因此注入的 0.0 / 1.0 必须被抹平。
    这比「介于极值之间」更强，也更容易定位回归。
    """
    cleaned = ndops.median_filter(noisy_field, size=3)
    assert cleaned[10, 10] == pytest.approx(0.5), "0.0 噪声点未被中值取代"
    assert cleaned[20, 20] == pytest.approx(0.5), "1.0 噪声点未被中值取代"
    # 其余位置保持不变
    mask = np.ones_like(noisy_field, dtype=bool)
    mask[10, 10] = mask[20, 20] = False
    np.testing.assert_allclose(cleaned[mask], 0.5)


def test_median_filter_rejects_even_size(alpha_field):
    with pytest.raises(ValueError):
        ndops.median_filter(alpha_field, size=4)


def test_gaussian_filter_preserves_constant(alpha_field):
    constant = np.full((32, 32), 0.5)
    blurred = ndops.gaussian_filter(constant, sigma=2.0)
    np.testing.assert_allclose(blurred, 0.5, atol=1e-9)


def test_gaussian_filter_smooths_and_is_symmetric(alpha_field):
    blurred = ndops.gaussian_filter(alpha_field, sigma=3.0)
    # 模糊必然降低极值
    assert blurred.max() <= alpha_field.max() + 1e-9
    assert blurred.min() >= alpha_field.min() - 1e-9
    # 可分离实现必须保持轴对称对称性
    np.testing.assert_allclose(blurred, ndops.gaussian_filter(alpha_field[::-1, ::-1], 3.0)[::-1, ::-1], atol=1e-9)


def test_gaussian_filter_non_positive_sigma_is_noop(alpha_field):
    np.testing.assert_allclose(ndops.gaussian_filter(alpha_field, sigma=0), alpha_field)


def test_binary_erosion_shrinks_mask():
    mask = np.zeros((32, 32), dtype=bool)
    mask[8:24, 8:24] = True
    eroded = ndops.binary_morphology(mask, np.ones((3, 3), bool), iterations=1, operation="erosion")
    assert eroded.sum() < mask.sum()
    # 中心仍为 True
    assert eroded[16, 16]


def test_binary_dilation_grows_mask():
    mask = np.zeros((32, 32), dtype=bool)
    mask[8:24, 8:24] = True
    dilated = ndops.binary_morphology(mask, np.ones((3, 3), bool), iterations=1, operation="dilation")
    assert dilated.sum() > mask.sum()
    # 原边界外一像素被填充
    assert dilated[7, 16]


def test_binary_morphology_rejects_unknown_operation():
    with pytest.raises(ValueError):
        ndops.binary_morphology(np.ones((4, 4), bool), operation="open")


def test_binary_morphology_respects_structure_extent():
    """结构元中 False 的位置必须真正不参与判定。

    用 1D 形状（单行/单列）来证明：结构元形状决定侵蚀方向。
    单行横条 mask + 3x3 方核，竖直方向邻居为 False → 整条被腐蚀掉；
    用「只有横向」的结构元则横条完整保留。
    若实现错误地把 False 位当成「参与且为 True」，两者会得到相同结果。
    """
    mask = np.zeros((16, 16), dtype=bool)
    mask[8, 4:12] = True  # 单行横条

    square = np.ones((3, 3), dtype=bool)
    horizontal_only = np.array([[1, 1, 1], [0, 0, 0], [0, 0, 0]], dtype=bool)

    eroded_square = ndops.binary_morphology(mask, square, 1, "erosion")
    eroded_horizontal = ndops.binary_morphology(mask, horizontal_only, 1, "erosion")

    assert eroded_square.sum() == 0, "3x3 方核应把单行横条完全腐蚀（竖直邻居为 False）"
    assert eroded_horizontal.sum() == 6, "仅横向结构元不应吃掉横条，只缩两端各 1 像素"


def test_binary_morphology_cross_matches_square_on_rectangle():
    """矩形边界上十字核与方核腐蚀结果相同 —— 这是几何事实，作为一致性锚点。

    记录这个结论是为了防止后续误以为两者应有差异而改坏实现。
    """
    mask = np.zeros((16, 16), dtype=bool)
    mask[4:12, 4:12] = True
    cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
    square = np.ones((3, 3), dtype=bool)
    np.testing.assert_array_equal(
        ndops.binary_morphology(mask, cross, 1, "erosion"),
        ndops.binary_morphology(mask, square, 1, "erosion"),
    )


# --- 与 scipy 的对照（仅当环境仍有 scipy 时执行） ---------------------------

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy 未安装，跳过历史行为对照")
@pytest.mark.parametrize("axis", [0, 1])
def test_matches_scipy_sobel(alpha_field, axis):
    expected = ndimage.sobel(alpha_field, axis=axis)
    got = ndops.sobel(alpha_field, axis=axis)
    # float32 输入下 scipy 以 float32 累加，本实现用 float64，容差取 1e-7
    np.testing.assert_allclose(got, expected, atol=1e-7)


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy 未安装，跳过历史行为对照")
def test_matches_scipy_laplace(alpha_field):
    np.testing.assert_allclose(ndops.laplace(alpha_field), ndimage.laplace(alpha_field), atol=1e-7)


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy 未安装，跳过历史行为对照")
@pytest.mark.parametrize("size", [3, 5])
def test_matches_scipy_median_filter(alpha_field, size):
    np.testing.assert_allclose(
        ndops.median_filter(alpha_field, size=size),
        ndimage.median_filter(alpha_field, size=size),
        atol=1e-7,
    )


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy 未安装，跳过历史行为对照")
@pytest.mark.parametrize("sigma", [0.8, 2.0, 5.0])
def test_matches_scipy_gaussian_filter(alpha_field, sigma):
    np.testing.assert_allclose(
        ndops.gaussian_filter(alpha_field, sigma=sigma),
        ndimage.gaussian_filter(alpha_field, sigma=sigma),
        atol=1e-6,
    )


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy 未安装，跳过历史行为对照")
@pytest.mark.parametrize("operation", ["erosion", "dilation"])
@pytest.mark.parametrize("iterations", [1, 2, 3])
def test_matches_scipy_binary_morphology(alpha_field, operation, iterations):
    mask = alpha_field > 0.5
    structure = np.ones((3, 3), dtype=bool)
    func = ndimage.binary_erosion if operation == "erosion" else ndimage.binary_dilation
    expected = func(mask, structure=structure, iterations=iterations, border_value=0)
    got = ndops.binary_morphology(mask, structure, iterations=iterations, operation=operation)
    np.testing.assert_array_equal(got, expected)


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy 未安装，跳过历史行为对照")
def test_matches_scipy_binary_morphology_cross_structure(alpha_field):
    """十字结构元是 vector_layer_effects 描边生成的实际用法。"""
    mask = alpha_field > 0.5
    cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
    for operation, func in (("erosion", ndimage.binary_erosion), ("dilation", ndimage.binary_dilation)):
        expected = func(mask, structure=cross, iterations=1, border_value=0)
        got = ndops.binary_morphology(mask, cross, iterations=1, operation=operation)
        np.testing.assert_array_equal(got, expected, err_msg=f"{operation} 与 scipy 不一致")
