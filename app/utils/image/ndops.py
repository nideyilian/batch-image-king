"""numpy 图像算子：替代 scipy.ndimage 的最小实现。

为什么存在：scipy 为本项目贡献 110MB 安装体积 / 18.8MB 打包体积，
而实际只用到 sobel / laplace / binary_erosion / binary_dilation /
median_filter / gaussian_filter 六个算子。这些算子用 numpy 实现完全等价，
实测差异为 0.000000（见 .workbuddy/memory 2026-10-27 记录）。

只实现项目真实用到的算子，不做通用库。维度约定与原 scipy 调用一致：
输入 2D 数组（通常是 alpha 通道 / 掩码）。
"""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# Sobel 3x3 核。scipy.ndimage.sobel 不做归一化，与下面手写卷积同值。
_SOBEL = {
    1: np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64),
    0: np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float64),
}

# 4 邻域拉普拉斯核，与 scipy.ndimage.laplace 一致
_LAPLACE = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)


def _convolve2d(data: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """3x3 卷积。

    边界用 numpy 的 ``symmetric`` 填充。注意这不是笔误：scipy.ndimage 的
    默认 ``mode='reflect'`` 对应 numpy 的 ``symmetric``（(c b a | a b c d | d c b)），
    而 numpy 里叫 ``reflect`` 的模式是另一种（(d c b | a b c d | c b a)）。
    用错会导致仅 1px 边界出现差异。
    """
    data = np.asarray(data, dtype=np.float64)
    if data.ndim != 2:
        raise ValueError(f"只支持 2D 数组，收到 shape={data.shape}")
    padded = np.pad(data, 1, mode="symmetric")
    windows = sliding_window_view(padded, kernel.shape)
    return np.einsum("ijkl,kl->ij", windows, kernel)


def sobel(data: np.ndarray, axis: int = 1) -> np.ndarray:
    """Sobel 一阶导数。axis=1 求水平梯度，axis=0 求垂直梯度。"""
    return _convolve2d(data, _SOBEL[axis])


def laplace(data: np.ndarray) -> np.ndarray:
    """拉普拉斯算子（4 邻域）。"""
    return _convolve2d(data, _LAPLACE)


def median_filter(data: np.ndarray, size: int = 3) -> np.ndarray:
    """中值滤波，方形窗口，边界 reflect。"""
    data = np.asarray(data)
    if size % 2 == 0:
        raise ValueError("size 必须为奇数")
    pad = size // 2
    if data.ndim == 2:
        padded = np.pad(data, pad, mode="symmetric")
        windows = sliding_window_view(padded, (size, size))
        return np.median(windows.reshape(*windows.shape[:2], -1), axis=-1)
    raise ValueError(f"只支持 2D 数组，收到 shape={data.shape}")


def gaussian_filter(data: np.ndarray, sigma: float) -> np.ndarray:
    """可分离高斯滤波。sigma<=0 时原样返回（同 scipy 行为）。"""
    if sigma <= 0:
        return np.asarray(data, dtype=np.float64).copy()

    data = np.asarray(data, dtype=np.float64)
    # 截断半径取 4 sigma，与 scipy 默认 truncate=4.0 一致
    radius = int(4.0 * sigma + 0.5)
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-(offsets**2) / (2.0 * sigma**2))
    kernel /= kernel.sum()

    # 两次一维卷积等价于一次二维高斯（可分离性）
    out = _convolve1d(data, kernel, axis=1)
    return _convolve1d(out, kernel, axis=0)


def _convolve1d(data: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    """沿指定轴做一维卷积，边界 symmetric（对应 scipy 的 reflect）。"""
    radius = len(kernel) // 2
    pad_width = [(0, 0), (0, 0)]
    pad_width[axis] = (radius, radius)
    padded = np.pad(data, pad_width, mode="symmetric")
    windows = sliding_window_view(padded, len(kernel), axis=axis)
    return np.tensordot(windows, kernel, axes=([-1], [0]))


def binary_morphology(
    mask: np.ndarray,
    structure: np.ndarray | None = None,
    iterations: int = 1,
    operation: str = "erosion",
) -> np.ndarray:
    """二值腐蚀 / 膨胀，等价 scipy.ndimage.binary_erosion / binary_dilation。

    scipy 语义：
    - erosion 为 True 当且仅当结构元覆盖范围内**全部**为 True；
    - dilation 为 True 当且仅当范围内**至少一个**为 True；
    - 结构元中为 False 的位置不参与判定；
    - border_value=0 表示边界外视为 False（erosion 因此侵蚀边缘）。
    """
    if operation not in ("erosion", "dilation"):
        raise ValueError("operation 必须是 erosion 或 dilation")

    mask = np.asarray(mask, dtype=bool)
    if structure is None:
        structure = np.ones((3, 3), dtype=bool)
    structure = structure.astype(bool)
    offset = [(s // 2, s // 2) for s in structure.shape]
    flat_struct = structure.reshape(-1)
    is_erosion = operation == "erosion"

    result = mask
    for _ in range(max(1, iterations)):
        padded = np.pad(result, offset, mode="constant", constant_values=False)
        windows = sliding_window_view(padded, structure.shape)
        flat = windows.reshape(*windows.shape[:2], -1)[..., flat_struct]
        # erosion：命中全部有效位；dilation：命中任一有效位
        result = np.all(flat, axis=-1) if is_erosion else np.any(flat, axis=-1)

    return result


__all__ = [
    "sobel",
    "laplace",
    "median_filter",
    "gaussian_filter",
    "binary_morphology",
]
