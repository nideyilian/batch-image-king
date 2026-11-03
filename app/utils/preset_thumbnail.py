"""预设缩略图生成与磁盘缓存。

预设中心升级为工作台后，卡片必须显示真实预览图（Figma / Canva / Eagle
的共识：纯文字列表无法快速识别，见 docs/preset-workbench-design.md）。

本模块负责：

- 由预设的 ``.cmp`` 数据还原出 ``Document``（复用 ``documents_from_preset_data``，
  与打开项目的恢复路径完全一致，避免字段漂移）。
- 经唯一渲染出口 ``render_document_to_image`` 渲染成 PIL 图。
- 按长边缩放到卡片需要的尺寸，写盘到 ``presets/thumbs/<preset_id>.png``。
- 以「源 .cmp 的 mtime + 缩略图长边」判断缓存是否仍有效，避免重复渲染。

线程模型：渲染是 CPU 密集的，绝不能在 UI 线程做。``PresetThumbnailService``
持有一条后台工作线程串行消费任务；串行而非并发是有意为之——渲染器内部已有
全局缓存和内存预算，多预设并发渲染会互相驱逐对方的图层 surface 缓存。
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Callable, Optional

from PIL import Image
from PySide6.QtCore import QObject

logger = logging.getLogger(__name__)

# 卡片缩略图长边。工作台卡片宽度约 180-260px，2x 屏需要 ~520。
# 取 512 兼顾清晰度与磁盘占用（20 个预设约 3-6MB）。
DEFAULT_THUMB_MAX_EDGE = 512

# 缓存目录名（位于 presets/ 下）
THUMB_DIR_NAME = "thumbs"

# 判定「太旧」的容差：文件系统 mtime 精度在不同平台不一致，
# 1 秒内的差异视为同一版本，避免界面上反复重渲染。
_MTIME_TOLERANCE = 1.0


def thumb_path_for(presets_dir: str, preset_id: str, page: int = 0) -> str:
    """返回某预设（某一页）缩略图的标准磁盘路径。

    命名规则：
      - 第 0 页沿用 ``<id>.png``（兼容已有缓存，不用全量重算）
      - 其余页 ``<id>__p1.png``、``<id>__p2.png`` …
    这样加多页支持不会让旧缓存失效。
    """
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    if page <= 0:
        return os.path.join(presets_dir, THUMB_DIR_NAME, f"{preset_id}.png")
    return os.path.join(presets_dir, THUMB_DIR_NAME, f"{preset_id}__p{page}.png")


def _ensure_thumb_dir(presets_dir: str) -> str:
    directory = os.path.join(presets_dir, THUMB_DIR_NAME)
    os.makedirs(directory, exist_ok=True)
    return directory


def is_cache_valid(thumb_path: str, source_path: str) -> bool:
    """缩略图是否存在且不旧于源文件。

    缩略图缺失、尺寸为 0、或源 .cmp 更新过，都算失效。
    """
    try:
        if not os.path.isfile(thumb_path) or not os.path.isfile(source_path):
            return False
        if os.path.getsize(thumb_path) <= 0:
            return False
        thumb_mtime = os.path.getmtime(thumb_path)
        source_mtime = os.path.getmtime(source_path)
        return thumb_mtime + _MTIME_TOLERANCE >= source_mtime
    except OSError:
        return False


def render_preset_thumbnail(
    preset_id: str,
    presets_dir: str,
    max_edge: int = DEFAULT_THUMB_MAX_EDGE,
    *,
    source_path: Optional[str] = None,
    cover_index: int = 0,
) -> Optional[str]:
    """渲染指定页的缩略图，返回路径（失败 None）。向后兼容的旧入口。"""
    paths = render_preset_thumbnails(
        preset_id,
        presets_dir,
        max_edge,
        source_path=source_path,
        cover_index=cover_index,
    )
    if not paths:
        return None
    try:
        index = int(cover_index)
    except (TypeError, ValueError):
        index = 0
    return paths.get(index) or paths.get(0)


def render_preset_thumbnails(
    preset_id: str,
    presets_dir: str,
    max_edge: int = DEFAULT_THUMB_MAX_EDGE,
    *,
    source_path: Optional[str] = None,
    cover_index: int = 0,
    max_pages: int = 0,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> dict:
    """渲染预设各页的缩略图，返回 ``{页号: 路径}``。

    为什么一次渲染多页而不是按需渲染：
    卡片悬停轮播会在几秒内连续切页，按需渲染会让每切一次都卡一下。
    一次性把整页封面集算好落盘，之后轮播纯粹是换图片源。

    ``max_pages`` 限制渲染页数（0 表示不限）。多标签预设最多 9 页，
    全渲染的代价可接受（实测单页约 0.3s）。

    ``should_cancel`` 是**逐页**取消检查钩子，返回真则立刻放弃整批
    （返回 ``{}``，已渲染的页也不返回）。用它而不是「渲染完再丢弃结果」，
    是因为取消场景（清空标签页 / 删除预设）紧接着就会删掉缩略图文件，
    若渲染完再落盘，会把刚删掉的文件又写回来 —— 于是下次读到的是
    「旧内容的缩略图」，表现为「清空后卡片还显示原来的图」。

    已落盘的历史页不会被清理（那是调用方 ``_drop_thumbnails`` 的职责）。
    """
    preset_id = str(preset_id or "").strip()
    if not preset_id:
        return {}

    source_path = source_path or os.path.join(presets_dir, f"{preset_id}.cmp")
    if not os.path.isfile(source_path):
        logger.warning("预设缩略图跳过：源文件不存在 %s", source_path)
        return {}

    try:
        # ---- 1) 先挑出「需要渲染」的页，命中缓存的直接复用 ----
        from app.utils.preset_document_loader import documents_from_preset_data
        from app.utils.trusted_pickle import load_trusted_pickle

        with open(source_path, "rb") as handle:
            preset_data = load_trusted_pickle(handle, source_path)

        # 给文档挂一个 C++ 父对象：Document 是 QObject，parent=None 时其 C++
        # 对象生命周期由 Python 引用计数决定。本函数在工作线程里跑，渲染链路
        # 可能持有跨线程的临时引用，GC 在错误的时刻回收会触发
        # "libshiboken: Internal C++ object (Document) already deleted"。
        holder = QObject()
        documents = documents_from_preset_data(preset_data, parent=holder)
        if not documents:
            logger.warning("预设缩略图跳过：%s 中没有可用文档", preset_id)
            return {}

        total = len(documents)
        if max_pages and max_pages > 0:
            total = min(total, int(max_pages))

        wanted = list(range(total))
        # 当前封面页必须包含在内（哪怕它超出 max_pages）
        try:
            cover = int(cover_index)
        except (TypeError, ValueError):
            cover = 0
        if 0 <= cover < len(documents) and cover not in wanted:
            wanted.append(cover)

        result: dict = {}
        pending: list = []
        for page in wanted:
            path = thumb_path_for(presets_dir, preset_id, page)
            if is_cache_valid(path, source_path):
                result[page] = path
            else:
                pending.append(page)

        if not pending:
            return result

        # ---- 2) 逐页渲染缺失的部分 ----
        from app.services.render_service import render_document_to_image

        _ensure_thumb_dir(presets_dir)
        for page in pending:
            # 每页开始前检查一次：取消后不再白跑后续页（每页约 0.3s）。
            if should_cancel is not None and should_cancel():
                logger.debug("预设缩略图渲染已取消 %s（第 %d 页前）", preset_id, page)
                return {}
            document = documents[page]
            page_path = thumb_path_for(presets_dir, preset_id, page)
            try:
                rendered = render_document_to_image(
                    document,
                    mode="preview",
                    quality_profile="speed",
                    batch_mode=False,
                    force_refresh=False,
                )
                image = getattr(rendered, "image", None)
                if image is None:
                    logger.warning(
                        "预设缩略图渲染失败 %s 第 %d 页：%s",
                        preset_id,
                        page,
                        getattr(rendered, "error", ""),
                    )
                    continue

                thumb = image.convert("RGBA") if image.mode != "RGBA" else image
                longest = max(thumb.width, thumb.height)
                if longest > max_edge > 0:
                    scale = max_edge / float(longest)
                    new_size = (
                        max(1, round(thumb.width * scale)),
                        max(1, round(thumb.height * scale)),
                    )
                    thumb = thumb.resize(new_size, Image.LANCZOS)

                # 落盘前再检查一次。渲染一页要几百毫秒，这段时间里很可能
                # 正好发生「清空标签页」——文件已被调用方删掉，此时写回
                # 会让卡片继续显示旧图。这是本函数唯一必须守住的窗口。
                if should_cancel is not None and should_cancel():
                    logger.debug("预设缩略图渲染已取消 %s（第 %d 页落盘前）", preset_id, page)
                    return {}

                # 先写临时文件再原子替换，避免并发读到半张图
                tmp_path = f"{page_path}.{os.getpid()}.{threading.get_ident()}.tmp"
                thumb.save(tmp_path, format="PNG", optimize=True)
                os.replace(tmp_path, page_path)
                result[page] = page_path
            except Exception as exc:  # noqa: BLE001 - 单页失败不影响其余页
                logger.warning("预设缩略图第 %d 页失败 %s: %s", page, preset_id, exc)

        return result
    except Exception as exc:  # noqa: BLE001 - 缩略图失败不能影响主流程
        logger.warning("预设缩略图生成失败 %s: %s", preset_id, exc, exc_info=True)
        return {}


def check_missing_sources(preset_id: str, presets_dir: str) -> list[str]:
    """检查预设封面页有多少图层的素材路径已失效。

    用户删掉源素材文件夹后，预设仍能打开，只是部分图层渲染为空——
    缩略图会看起来"莫名其妙地空"。工作台需要在卡片上明确提示，
    否则用户会以为是程序坏了。

    只检查封面页：封面才是卡片上展示的内容，其它页缺素材不影响识别。
    """
    preset_id = str(preset_id or "").strip()
    if not preset_id:
        return []
    source_path = os.path.join(presets_dir, f"{preset_id}.cmp")
    if not os.path.isfile(source_path):
        return []
    try:
        from app.utils.preset_document_loader import documents_from_preset_data
        from app.utils.trusted_pickle import load_trusted_pickle

        with open(source_path, "rb") as handle:
            preset_data = load_trusted_pickle(handle, source_path)
        documents = documents_from_preset_data(preset_data)
        if not documents:
            return []

        missing = []
        for layer in documents[0].layers:
            source = getattr(layer, "image_source", None)
            if isinstance(source, str) and source and not os.path.exists(source):
                missing.append(str(getattr(layer, "name", "") or "未命名图层"))
        return missing
    except Exception as exc:  # noqa: BLE001 - 探测失败不该影响工作台
        logger.debug("素材缺失探测失败 %s: %s", preset_id, exc)
        return []


class PresetThumbnailService:
    """后台并发生成预设缩略图。

    并发度取 4：实测 6 个预设串行 4.58s、并发(4) 1.76s（2.6x）。
    再往上收益递减且会互相挤压渲染器的图层 surface 缓存（默认预算 512MB），
    所以固定 4 而不是按 CPU 核数放大。
    """

    MAX_WORKERS = 4

    def __init__(self, presets_dir: str, max_edge: int = DEFAULT_THUMB_MAX_EDGE) -> None:
        self._presets_dir = presets_dir
        self._max_edge = int(max_edge)
        self._queue: "queue.Queue[tuple[str, str, int, int]]" = queue.Queue()
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._pending: set[str] = set()
        self._listeners: list[Callable[[str, str], None]] = []
        # preset_id -> 代数。每次 cancel 递增，队列项带着入队时的代数进工作线程，
        # 代数对不上即视为「已被取消」。
        #
        # 为什么不用一个 cancelled 布尔集合：取消后用户往往会立刻重新请求
        # （比如清空后又点撤销）。旧队列项还会被消费一次，若用布尔集合判断，
        # 新请求也会被这个集合误伤（表现为「撤销后缩略图再也不出来」）。
        # 布尔集合也无法区分「这个旧任务」和「同 id 的新任务」，
        # 旧任务结束时会把新任务的 _pending 一起 discard 掉。
        self._epochs: dict[str, int] = {}

    # ---- 生命周期 ----

    def start(self) -> None:
        with self._lock:
            alive = [t for t in self._workers if t.is_alive()]
            if len(alive) >= self.MAX_WORKERS:
                self._workers = alive
                return
            self._stop.clear()
            self._workers = alive
            while len(self._workers) < self.MAX_WORKERS:
                thread = threading.Thread(
                    target=self._run,
                    name=f"PresetThumbnailWorker-{len(self._workers)}",
                    daemon=True,
                )
                self._workers.append(thread)
                thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        with self._lock:
            workers = list(self._workers)
            self._workers = []
        for thread in workers:
            if thread.is_alive():
                thread.join(timeout=timeout)

    # ---- 订阅 ----

    def add_listener(self, callback: Callable[[str, str], None]) -> None:
        """注册完成回调：``callback(preset_id, thumb_path)``。

        回调在工作线程里执行；Qt 侧必须自行切回主线程再改模型。
        """
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, str], None]) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    # ---- 任务 ----

    def request(
        self, preset_id: str, *, force: bool = False, cover_index: int = 0
    ) -> Optional[str]:
        """请求生成缩略图。

        缓存有效时直接返回路径（不排队）；否则入队并返回 ``None``。
        ``cover_index`` 决定多标签预设用哪一页当封面。
        """
        preset_id = str(preset_id or "").strip()
        if not preset_id:
            return None

        source_path = os.path.join(self._presets_dir, f"{preset_id}.cmp")
        target_path = thumb_path_for(self._presets_dir, preset_id)
        # 只检查「当前封面页」是否有效：其余页会由后台按需补齐。
        # 这里返回路径意味着卡片可以立刻显示，不必等队列。
        if not force and is_cache_valid(target_path, source_path):
            return target_path

        with self._lock:
            if preset_id in self._pending:
                return None
            self._pending.add(preset_id)
            epoch = self._epochs.get(preset_id, 0)
        self.start()
        self._queue.put((preset_id, source_path, int(cover_index or 0), epoch))
        return None

    def request_many(self, preset_ids, *, force: bool = False) -> int:
        """批量请求，返回本次新入队的数量（命中缓存或已在队列中的不计）。"""
        queued = 0
        for preset_id in list(preset_ids or []):
            preset_id = str(preset_id or "").strip()
            if not preset_id:
                continue
            before = self.pending_count()
            if self.request(preset_id, force=force) is None and self.pending_count() > before:
                queued += 1
        return queued

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def cancel(self, preset_id: str) -> bool:
        """取消该预设尚未完成的缩略图任务，返回是否确实有待处理任务。

        幂等：没有待处理任务时也安全（只递增代数，让可能正在跑的旧任务失效）。

        调用方（清空标签页 / 删除预设）在删完缩略图文件后必须调它，否则
        几百毫秒后工作线程会把旧图重新写回磁盘 —— 卡片于是继续显示
        已经不存在的内容。

        已出队并正在渲染的那一页无法从外部打断（渲染是单个同步调用），
        但它会在下一个检查点看到代数变化而停下，不会把结果写回。
        """
        preset_id = str(preset_id or "").strip()
        if not preset_id:
            return False
        with self._lock:
            self._epochs[preset_id] = self._epochs.get(preset_id, 0) + 1
            was_pending = preset_id in self._pending
            self._pending.discard(preset_id)
        return was_pending

    def cancel_all(self) -> int:
        """取消所有待处理任务，返回取消数量。"""
        with self._lock:
            ids = list(self._pending)
        for preset_id in ids:
            self.cancel(preset_id)
        return len(ids)

    # ---- 工作线程 ----

    def _is_stale(self, preset_id: str, epoch: int) -> bool:
        """该任务是否已被取消（代数对不上）。"""
        with self._lock:
            return self._epochs.get(preset_id, 0) != epoch

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                preset_id, source_path, cover_index, epoch = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                # 出队后先看一眼是不是已被取消。取消的任务往往还有好几页，
                # 全渲染一遍要 1-2 秒，纯属浪费 CPU（会挤占画布预览）。
                if self._is_stale(preset_id, epoch):
                    continue
                # 一次把该预设各页都渲染好：卡片悬停轮播切页时就不必再排队，
                # 否则每次切页都要等 0.3s，体验上就是"卡一下"。
                page_paths = render_preset_thumbnails(
                    preset_id,
                    self._presets_dir,
                    self._max_edge,
                    source_path=source_path,
                    cover_index=cover_index,
                    should_cancel=lambda: self._is_stale(preset_id, epoch),
                )
                # 渲染途中被取消时不通知 UI：否则界面会拿到一个刚被删掉的路径。
                if page_paths and not self._is_stale(preset_id, epoch):
                    primary = page_paths.get(cover_index) or page_paths.get(0)
                    if primary:
                        self._notify(preset_id, primary)
            except Exception as exc:  # noqa: BLE001
                logger.warning("缩略图后台任务异常 %s: %s", preset_id, exc)
            finally:
                # ⚠️ 只有代数仍是自己的那一代才清 _pending。
                # 旧任务结束时若直接 discard，会把「取消后重新请求」的新任务
                # 状态一起清掉 —— 新任务还在队列里，pending 却是空，
                # 界面就此永远等不到通知。
                with self._lock:
                    if self._epochs.get(preset_id, 0) == epoch:
                        self._pending.discard(preset_id)
                self._queue.task_done()

    def _notify(self, preset_id: str, thumb_path: str) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for callback in listeners:
            try:
                callback(preset_id, thumb_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("缩略图回调异常: %s", exc)


_service_lock = threading.RLock()
_services: dict[tuple[str, int], PresetThumbnailService] = {}


def get_thumbnail_service(
    presets_dir: str, max_edge: int = DEFAULT_THUMB_MAX_EDGE
) -> PresetThumbnailService:
    """按预设目录取单例服务（同目录复用一个工作线程）。"""
    key = (os.path.abspath(presets_dir), int(max_edge))
    with _service_lock:
        service = _services.get(key)
        if service is None:
            service = PresetThumbnailService(presets_dir, max_edge)
            _services[key] = service
        return service


def shutdown_thumbnail_services() -> None:
    """退出时停掉所有后台线程（main.py 的事件循环结束后调用）。"""
    with _service_lock:
        services = list(_services.values())
        _services.clear()
    for service in services:
        try:
            service.stop()
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "DEFAULT_THUMB_MAX_EDGE",
    "check_missing_sources",
    "PresetThumbnailService",
    "get_thumbnail_service",
    "is_cache_valid",
    "render_preset_thumbnail",
    "shutdown_thumbnail_services",
    "thumb_path_for",
]
