"""
统一日志管理模块
提供全局日志记录功能

合并了以下模块的功能：
- logger.py - 日志工具类
- logging_setup.py - 日志设置模块
"""

import contextlib
import glob
import logging
import logging.handlers
import os
import sys
import threading
import time


__all__ = [
    "get_logger",
    "Logger",
    "log_suppressed",
    "swallow",
    "prune_legacy_log_files",
]

# ---------------------------------------------------------------------------
# 日志文件策略（2026-11-02）
# ---------------------------------------------------------------------------
# 历史问题：早期实现每次启动都新建 ``app_{timestamp}.log``，且没有任何轮转
# 策略。实测一个开发机累积到 1627 个文件 / 12MB，用户长期使用只会更糟，
# 排查问题时也无法按级别或时间窗口过滤。
#
# 现行策略（与主流桌面应用一致）：
#   * 单一滚动词典 ``app.log``，按大小轮转（5MB × 5 份），总量封顶约 30MB；
#   * 启动时清理历史遗留的 ``app_<timestamp>.log``（保留最近 N 个），
#     否则老用户的日志目录永远不会瘦下来。
# ---------------------------------------------------------------------------
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
LOG_FILENAME = "app.log"
# 启动时保留的历史时间戳日志个数（仅供对照上一版本，保留少量即可）
LEGACY_LOG_KEEP = 20
# 只清理超过该天数的历史日志，避免误删仍在排查用文件
LEGACY_LOG_MAX_AGE_DAYS = 30
# 单次清理上限：首次升级的用户可能有上千个历史文件，分批删避免启动久等
LEGACY_LOG_MAX_DELETE = 200

# 匹配历史遗留的带时间戳日志（app_20261102_101530.log）。
# 注意不会误伤现行的 app.log —— 后者没有下划线。
LEGACY_LOG_GLOB = "app_*.log"

# ---------------------------------------------------------------------------
# 统一日志使用规范（P0：收敛异常 swallowing / 统一日志）
# ---------------------------------------------------------------------------
# 1. 业务模块统一通过 ``get_logger(__name__)`` 获取 logger，不要散用 ``print``。
# 2. 记录错误请用 ``logger.error("...", exc_info=True)`` 或 ``Logger.error(msg, exception=e)``，
#    务必带上 ``exc_info`` 才能看到完整 traceback。
# 3. 必须吞掉（继续运行）的异常，使用 ``log_suppressed`` 上下文管理器，
#    它会以 WARNING 记录完整异常，避免“静默吞异常导致排障无据”：
#
#        with log_suppressed(logger, "加载预设失败"):
#            load_preset(path)
#
#    老的写法 ``logger.debug("静默异常已忽略: ...")`` 已统一收敛为带 ``exc_info`` 的 WARNING。
# ---------------------------------------------------------------------------


def log_suppressed(logger, context="", level=logging.WARNING):
    """上下文管理器：吞掉异常但记录完整 traceback，便于排障。

    典型用途是防御性清理/降级逻辑（关文件、清缓存、线程钩子等），
    这些异常不应中断主流程，但过去被完全静默，导致出错时无从排查。

    Args:
        logger: 任意 ``logging.Logger`` 实例。
        context: 上下文说明，会拼进日志消息。
        level: 记录级别，默认 ``logging.WARNING``；高频热路径可传 ``logging.DEBUG`` 降噪。

    用法::

        with log_suppressed(logger, "释放图层缓存"):
            cache.release(layer_id)
    """

    @contextlib.contextmanager
    def _context():
        try:
            yield
        except Exception:
            logger.log(level, "静默异常已忽略: %s", context, exc_info=sys.exc_info())

    return _context()


# 兼容别名
swallow = log_suppressed


def prune_legacy_log_files(log_dir, keep=LEGACY_LOG_KEEP,
                           max_age_days=LEGACY_LOG_MAX_AGE_DAYS,
                           max_delete=LEGACY_LOG_MAX_DELETE):
    """清理历史遗留的带时间戳日志 ``app_<timestamp>.log``。

    旧实现每次启动新建一个日志文件且从不清理，实测一台机器累积到 1627 个
    文件 / 12MB。这里做首次瘦身，之后由日志轮转接管，不再增长。

    保守策略（三个条件同时满足才删除）：
      1. 超出最近 ``keep`` 个（按修改时间倒序）；
      2. 最后修改时间早于 ``max_age_days`` 天；
      3. 单次最多删 ``max_delete`` 个（分批，避免首次启动久等）。

    ⚠️ 不要把它放回启动主路径同步执行：实测 1578 个文件逐个删除耗时 2.5 分钟，
    会把"打开软件"卡死。调用方应放到后台线程（见 ``Logger.init``）。

    现行的 ``app.log`` 及其轮转副本（``app.log.1`` …）不匹配该 glob，不受影响。

    Args:
        log_dir: 日志目录。
        keep: 保留的历史日志个数（按修改时间倒序）。
        max_age_days: 只删除超过该天数的文件。
        max_delete: 单次删除上限。

    Returns:
        实际删除的文件数。任何失败都只记 WARNING，不影响启动。
    """
    try:
        pattern = os.path.join(log_dir, LEGACY_LOG_GLOB)
        candidates = [
            path for path in glob.glob(pattern)
            if os.path.basename(path) != LOG_FILENAME
        ]
        if len(candidates) <= keep:
            return 0

        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        cutoff = time.time() - max_age_days * 86400
        removed = 0
        for path in candidates[keep:]:
            if removed >= max_delete:
                break
            try:
                if os.path.getmtime(path) > cutoff:
                    continue
                os.remove(path)
                removed += 1
            except OSError:
                # 文件被占用/权限不足：留给下次启动再试
                continue
        return removed
    except Exception:
        logging.getLogger(__name__).warning(
            "清理历史日志文件失败: %s", log_dir, exc_info=True
        )
        return 0


def _prune_legacy_logs_in_background(log_dir, keep=LEGACY_LOG_KEEP,
                                     max_age_days=LEGACY_LOG_MAX_AGE_DAYS):
    """在守护线程里清理历史日志，**不阻塞启动**。

    首次升级的用户可能有上千个历史日志，同步删除会让启动卡好几分钟。
    这里丢给 daemon 线程：失败不影响主流程，进程退出时也随之结束。
    """
    def _worker():
        try:
            removed = prune_legacy_log_files(
                log_dir, keep=keep, max_age_days=max_age_days
            )
            if removed:
                logging.getLogger(__name__).info(
                    "已清理 %d 个历史日志文件（保留最近 %d 个）: %s",
                    removed, keep, log_dir,
                )
        except Exception:
            logging.getLogger(__name__).warning(
                "后台清理历史日志失败: %s", log_dir, exc_info=True
            )

    try:
        thread = threading.Thread(
            target=_worker, name="legacy-log-prune", daemon=True
        )
        thread.start()
    except Exception:
        # 线程都起不来就放弃清理，绝不能因此影响启动
        logging.getLogger(__name__).warning(
            "无法启动历史日志清理线程: %s", log_dir, exc_info=True
        )


def get_logger(name="app", log_file="app_log.txt", level=logging.INFO):
    """
    创建并配置日志记录器（从logging_setup.py合并）

    ⚠️ 兼容保留，**新代码请改用 ``Logger.init()`` / ``Logger.get_logger()``**。
    本函数会把日志写到 ``log_file``（默认相对路径 ``app_log.txt``，随工作目录变化），
    且不做轮转，与现行 ``app.log`` 轮转策略不一致。当前仓库内已无调用点。

    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志记录级别

    Returns:
        配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 防止重复添加处理器
    if logger.handlers:
        return logger

    # 创建文件处理器（显式声明不做轮转，避免与 Logger.init 策略混淆）
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    # 创建格式化器
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 设置格式化器
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


class Logger:
    """日志工具类，提供全局日志记录功能"""
    
    # 日志级别常量
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    
    # 初始化标志
    _initialized = False
    
    # 日志实例
    _logger = None
    
    @classmethod
    def init(cls, log_dir='logs', log_level=logging.INFO, console_output=True, logger_name='app',
             max_bytes=LOG_MAX_BYTES, backup_count=LOG_BACKUP_COUNT):
        """
        初始化日志系统

        日志写入单一滚动词典 ``app.log``：超过 ``max_bytes`` 自动轮转，
        最多保留 ``backup_count`` 份，长期使用不会无限增长。

        Args:
            log_dir: 日志文件目录
            log_level: 日志级别
            console_output: 是否输出到控制台
            logger_name: 日志器名称
            max_bytes: 单个日志文件上限（字节），默认 5MB
            backup_count: 轮转保留份数，默认 5
        """
        if cls._initialized:
            return
        
        # 创建日志目录，添加异常处理
        try:
            os.makedirs(log_dir, exist_ok=True)
        except (OSError, PermissionError) as e:
            # 如果无法创建指定目录，使用临时目录
            import tempfile
            log_dir = tempfile.gettempdir()
            logging.error("[警告] 无法创建日志目录，使用临时目录: %s", log_dir)
        except Exception as e:
            # 其他异常，使用当前目录
            log_dir = '.'
            logging.error("[警告] 创建日志目录时出错，使用当前目录: %s", e)

        # 清理旧版本遗留的时间戳日志。
        # 必须放后台：首次升级的用户可能有上千个文件，同步删除实测耗时
        # 2.5 分钟，会把"打开软件"卡死。
        _prune_legacy_logs_in_background(log_dir)

        # 固定文件名 + 大小轮转，替代「每次启动新建一个文件」
        log_file = os.path.join(log_dir, LOG_FILENAME)
        
        # 创建日志器
        logger = logging.getLogger(logger_name)
        logger.setLevel(log_level)
        
        # 防止日志重复输出
        if logger.handlers:
            logger.handlers.clear()
        
        # 创建文件处理器，添加异常处理
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8',
            )
            file_handler.setLevel(log_level)
        except (OSError, PermissionError) as e:
            # 如果无法创建日志文件，使用备用方案
            logging.error("[警告] 无法创建日志文件 %s: %s", log_file, e)
            # 尝试使用临时文件
            import tempfile
            temp_log = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log', encoding='utf-8')
            temp_log.close()
            file_handler = logging.FileHandler(temp_log.name, encoding='utf-8')
            file_handler.setLevel(log_level)
            logging.error("[警告] 使用临时日志文件: %s", temp_log.name)
        except Exception as e:
            # 最后的备选方案：禁用文件日志
            logging.error("[警告] 创建文件处理器失败，禁用文件日志: %s", e)
            file_handler = None
        
        # 创建日志格式（与main.py保持一致）
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        if file_handler:
            file_handler.setFormatter(formatter)
            # 添加文件处理器到日志器
            logger.addHandler(file_handler)
        
        # 如果需要控制台输出，添加控制台处理器
        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # 保存日志器实例
        cls._logger = logger
        cls._initialized = True
        
        # 记录初始化信息
        cls.info("日志系统初始化完成")
    
    @classmethod
    def _ensure_initialized(cls):
        """确保日志系统已初始化"""
        if not cls._initialized:
            cls.init()
    
    @classmethod
    def debug(cls, message, *args, **kwargs):
        """记录调试信息"""
        cls._ensure_initialized()
        cls._logger.debug(message, *args, **kwargs)
    
    @classmethod
    def info(cls, message, *args, **kwargs):
        """记录一般信息"""
        cls._ensure_initialized()
        cls._logger.info(message, *args, **kwargs)
    
    @classmethod
    def warning(cls, message, *args, **kwargs):
        """记录警告信息"""
        cls._ensure_initialized()
        cls._logger.warning(message, *args, **kwargs)
    
    @classmethod
    def error(cls, message, exception=None, *args, **kwargs):
        """
        记录错误信息
        
        Args:
            message: 错误信息
            exception: 异常对象
            args: 其他参数
            kwargs: 其他关键字参数
        """
        cls._ensure_initialized()
        
        if exception:
            # 如果提供了异常对象，记录异常信息
            import traceback
            error_msg = f"{message}: {str(exception)}\n{traceback.format_exc()}"
            cls._logger.error(error_msg, *args, **kwargs)
        else:
            cls._logger.error(message, *args, **kwargs)
    
    @classmethod
    def critical(cls, message, *args, **kwargs):
        """记录严重错误信息"""
        cls._ensure_initialized()
        cls._logger.critical(message, *args, **kwargs)
    
    @classmethod
    def set_level(cls, level):
        """设置日志级别"""
        cls._ensure_initialized()
        cls._logger.setLevel(level)
        for handler in cls._logger.handlers:
            handler.setLevel(level)
    
    @classmethod
    def get_logger(cls):
        """获取日志实例"""
        cls._ensure_initialized()
        return cls._logger

# ---------------------------------------------------------------------------
# 降级统计：热路径上的"吞掉但必须可查"
# ---------------------------------------------------------------------------
class DegradationCounter:
    """按 key 统计降级事件，首次详细记录、后续聚合汇总。

    为什么需要它：批量导出每张图都会走素材选择 / 图层解析等热路径，
    这些地方的防御性 except 如果每次都 ``logger.warning(exc_info=True)``，
    导出 5000 张就是 5000 条堆栈，日志被冲垮；但完全静默又让"图不对"
    无从定位（这正是历史遗留 30+ 处静默 except 的成因）。

    折中做法：
      - 同一 key 第一次出现 → WARNING + 完整 traceback
      - 后续同 key        → 只累加计数，不写日志
      - 批次结束时调用 ``summary()`` → 一行汇总所有降级点及次数

    用法::

        DEGRADATION = DegradationCounter(logger)

        try:
            count = manager.get_image_usage_count(path)
        except Exception:
            DEGRADATION.note("global_avoid.usage_count", path)
            count = 0

        # 批次结束
        for line in DEGRADATION.summary():
            logger.warning(line)
    """

    def __init__(self, logger=None):
        self._logger = logger
        self._counts = {}
        self._seen = set()
        self._samples = {}

    def note(self, key, detail=None, level=logging.WARNING):
        """记录一次降级事件。

        Args:
            key: 降级点标识，建议 ``模块.动作`` 形式，稳定可聚合。
            detail: 出问题的具体对象（路径 / 图层名 / 索引），只用于日志样本。
        """
        self._counts[key] = self._counts.get(key, 0) + 1
        if key not in self._samples and detail is not None:
            self._samples[key] = detail

        if key in self._seen:
            return

        self._seen.add(key)
        if self._logger is None:
            return
        sample = f" | 首个样本: {detail}" if detail is not None else ""
        self._logger.log(
            level,
            "降级执行（结果可能不符合预期）: %s%s",
            key,
            sample,
            exc_info=True,
        )

    def count(self, key):
        """取某个降级点的累计次数。"""
        return self._counts.get(key, 0)

    @property
    def total(self):
        """所有降级事件的累计次数。"""
        return sum(self._counts.values())

    def has_any(self):
        return bool(self._counts)

    def summary(self):
        """生成汇总行（每个 key 一行，按次数降序）。"""
        if not self._counts:
            return []
        lines = [f"本次导出发生 {self.total} 次降级（{len(self._counts)} 类）："]
        for key, n in sorted(self._counts.items(), key=lambda kv: -kv[1]):
            sample = self._samples.get(key)
            suffix = f"，样本: {sample}" if sample is not None else ""
            lines.append(f"  - {key} × {n}{suffix}")
        return lines

    def reset(self):
        self._counts.clear()
        self._seen.clear()
        self._samples.clear()
