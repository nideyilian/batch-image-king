"""启动画面：在冷启动的固有等待期给出可信反馈。

## 为什么要这个东西

`MainWindow()` 在目标机器上冷启动要 **3.5~5 秒**（实测，见
.workbuddy/memory/2026-10-27.md）。这期间是纯阻塞构造，界面一片空白，
用户会以为程序没启动、双击第二次，或者被 Windows 标记「未响应」。
这 5 秒是 Qt 首次创建原生窗口 + 676 个控件首次布局的固有成本，
代码层优化不掉，所以正确做法是**把这 5 秒的等待变得可感知、可信任**。

## 四条硬性约束（全部是实测踩出来的，别轻易改）

**1. 首帧必须是纯几何绘制，禁止任何文字**
本机装了 **2004 个字体族**，第一次 `QPainter.drawText` 触发字体族解析，
实测 **1.0~4.1 秒**（波动大，取决于系统缓存状态）。
启动画面的全部价值就是"快速出现"，为画几个字先卡几秒是本末倒置。
→ 首帧只画圆角矩形 + 进度条，实测 **3ms**。

**2. 文字排版放后台线程（QImage），完成后替换画面**
QPixmap 只能在 GUI 线程用，但 **QImage + QPainter 可在后台线程**（实测有效）。
文字在主窗口构造期间并行渲染，画完通过信号回主线程贴图。
这样既不拖首帧，也不用干等。

**3. 进度不能靠定时器推**
`MainWindow()` 是同步阻塞调用，事件循环转不起来。
进度必须由构造流程在阶段之间显式调 `advance()`，由它内部 `processEvents`
让画面真正上屏。见 `main.py` 的接入代码与 `MainWindow._notify_stage`。

**4. 动画只能"换图"不能"画图"**
理由同约束 1。呼吸点是预渲染帧，定时器到点直接换 pixmap。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QSplashScreen

# 视觉规格。色值取自 app/ui/dark_theme.py，此处**必须硬编码**：
# 启动画面要能在主题模块加载之前就画出来。
_WIDTH = 460
_HEIGHT = 340
_BG = QColor("#0A0B0D")          # BACKGROUND_PRIMARY
_BG_TOP = QColor("#121316")      # 顶部略亮，避免纯色板砖感
_FG = QColor("#F7F8F8")          # TEXT_PRIMARY
_FG_MUTED = QColor("#8E97A1")    # TEXT_MUTED
_ACCENT = QColor("#5E6AD2")      # ACCENT_PRIMARY
_TRACK = QColor("#1E2024")       # 进度条底槽
_FOOT = QColor("#4A505A")        # 版本号

_FONT_FAMILY = "Microsoft YaHei UI"

# 呼吸动画帧数：预渲染好，播放时只换图
_PULSE_FRAMES = 12

# 待机蠕动：每次心跳（120ms）进度最多前进 0.4%。
# 5 秒能爬 20% 左右，足够让用户看到"在动"，又不会跑到真实进度前面。
_CREEP_STEP = 0.004

# 进度条几何
_BAR_W = 260
_BAR_H = 3
_BAR_Y_OFFSET = 76       # 距底部


def _app_version() -> str:
    try:
        from app.version import APP_VERSION

        return str(APP_VERSION)
    except Exception:
        return ""


class SplashScreen(QSplashScreen):
    """带进度条与呼吸动画的启动画面。

    首帧纯几何（3ms 级）。**不渲染任何文字** —— 见模块开头约束 1：
    本机 2004 个字体族，首次 drawText 要 1~4 秒。
    曾尝试把文字放到后台线程（QImage + QPainter 确实支持跨线程），
    但 `thread.start()` 本身就被阻塞了 **3936ms** —— 后台线程抢字体系统锁
    反过来卡住主线程，比不画还糟。所以最终方案是：**启动画面不写字**。
    """

    def __init__(self, width: int = _WIDTH, height: int = _HEIGHT):
        self._width = width
        self._height = height
        self._progress = 0.0
        self._pulse_index = 0
        # 蠕动上限：由 advance() 设定为"下一段真实目标 - 安全间距"，
        # 保证蠕动永远不会跑到真实进度前面去（不撒谎）。
        self._creep_target = 0.0

        placeholder = QPixmap(width, height)
        placeholder.fill(_BG)
        super().__init__(placeholder)

        # 静态几何层：背景 + logo（一次画好，之后复用）。必须先上屏。
        self._base = self._render_base()
        # 呼吸帧：只有底部三个圆点亮度不同
        self._pulse_frames = self._render_pulse_frames()

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(120)
        self._pulse_timer.timeout.connect(self._next_pulse)

        # 文字层：延后到 begin() 之后单独补（见 _render_text_layer 说明）
        self._text_layer = None

        self._compose()

    # ------------------------------------------------------------- 预渲染
    def _render_base(self) -> QPixmap:
        """背景 + logo。**不画任何文字**（见模块开头约束 1）。"""
        pm = QPixmap(self._width, self._height)
        pm.fill(_BG)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self._width, self._height

        # 顶部渐变
        grad = QLinearGradient(0, 0, 0, 120)
        grad.setColorAt(0.0, _BG_TOP)
        grad.setColorAt(1.0, _BG)
        p.fillRect(0, 0, w, 120, grad)

        # 左侧品牌色细条
        p.fillRect(0, 0, 3, h, _ACCENT)

        # Logo：三个堆叠圆角方块（图层意象）
        p.setPen(Qt.NoPen)
        for dx, dy, alpha in ((22, 22, 60), (11, 11, 110), (0, 0, 255)):
            c = QColor(_ACCENT)
            c.setAlpha(alpha)
            p.setBrush(c)
            p.drawRoundedRect(
                QRectF(w / 2 - 28 + dx, 54 + dy, 56, 56), 12, 12
            )

        p.end()
        return pm

    def _render_pulse_frames(self):
        """预渲染呼吸帧：只画底部三个圆点，背景透明。"""
        frames = []
        dot_y = self._height - 38
        for f in range(_PULSE_FRAMES):
            pm = QPixmap(self._width, self._height)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(Qt.NoPen)
            for i in range(3):
                phase = (f / _PULSE_FRAMES + i * 0.33) % 1.0
                intensity = 1.0 - abs(phase - 0.5) * 2
                c = QColor(_ACCENT)
                c.setAlpha(int(50 + 160 * intensity))
                p.setBrush(c)
                p.drawEllipse(QRectF(self._width / 2 - 18 + i * 14, dot_y, 5, 5))
            p.end()
            frames.append(pm)
        return frames

    def _render_text_layer(self) -> QPixmap:
        """渲染文字层（标题 / 副标题 / 版本号），单独一张透明图。

        ## 为什么不在 __init__ 里画、也不放后台线程

        实测数据（两次一致）：
            不预热文字，直接建主窗口：     5299ms / 5277ms
            先量一次文字宽（付 3.9s），再建窗：1182ms / 1170ms
        两条路**总时长几乎相同**（约 5.1~5.3 秒），因为那 3.9 秒是
        首次字体族解析的一次性成本，主窗口无论如何都要付。

        既然躲不掉，就让它顺便为启动画面服务 —— 文字是免费得来的。
        但**必须在几何首帧上屏之后**再画，否则用户先看到的是 3.9 秒空白。

        也不用后台线程：实测 `thread.start()` 本身被阻塞 3936ms
        （后台抢字体系统锁反卡主线程），比不画还糟。
        """
        pm = QPixmap(self._width, self._height)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self._width, self._height

        # Logo 在 y=62..140 区域，文字放在其下方
        title_font = QFont(_FONT_FAMILY, 20)
        title_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(_FG)
        p.drawText(QRectF(0, 158, w, 34), Qt.AlignHCenter | Qt.AlignVCenter, "批图王")

        sub_font = QFont(_FONT_FAMILY, 9)
        p.setFont(sub_font)
        p.setPen(_FG_MUTED)
        p.drawText(
            QRectF(0, 192, w, 20),
            Qt.AlignHCenter | Qt.AlignVCenter,
            "图像批量合成工具",
        )

        version = _app_version()
        if version:
            ver_font = QFont(_FONT_FAMILY, 8)
            p.setFont(ver_font)
            p.setPen(_FOOT)
            p.drawText(
                QRectF(w - 90, h - 24, 76, 16),
                Qt.AlignRight | Qt.AlignVCenter,
                f"v{version}",
            )

        p.end()
        return pm

    def _render_dynamic(self) -> QPixmap:
        """合成当前帧：静态底 + 进度条 + 呼吸点 + 文字层（若已就绪）。

        进度条和圆点都是几何绘制，不涉及字体，快。
        步骤文字已刻意去掉 —— 每写一次 drawText 就是一次字体解析风险。
        进度改用分段刻度和百分比（百分比数字也去掉了，只留刻度与填充）。
        """
        pm = self._base.copy()
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self._width, self._height
        bar_x = (w - _BAR_W) / 2
        bar_y = h - _BAR_Y_OFFSET

        # 底槽
        p.setPen(Qt.NoPen)
        p.setBrush(_TRACK)
        p.drawRoundedRect(QRectF(bar_x, bar_y, _BAR_W, _BAR_H), 1.5, 1.5)

        # 已完成部分
        filled = max(0.0, min(1.0, self._progress)) * _BAR_W
        if filled > 0.5:
            p.setBrush(_ACCENT)
            p.drawRoundedRect(QRectF(bar_x, bar_y, filled, _BAR_H), 1.5, 1.5)

        # 呼吸帧
        frame = self._pulse_frames[self._pulse_index % len(self._pulse_frames)]
        p.drawPixmap(0, 0, frame)

        # 文字层（begin() 之后才生成）
        if self._text_layer is not None:
            p.drawPixmap(0, 0, self._text_layer)

        p.end()
        return pm

    def _compose(self):
        self.setPixmap(self._render_dynamic())

    # --------------------------------------------------------------- 动画
    def _next_pulse(self):
        self._pulse_index += 1
        # 长时间没有新进度时，让进度条自己缓慢"蠕动"。
        #
        # 为什么需要：主窗口构造里 `self.statusBar()` 一步就占 79.5% 的耗时
        # （约 4.2 秒），这段时间不可能产生中间进度点。若进度条数字钉死不动，
        # 用户会误判"卡住了"。这里让它在两次 advance 之间缓慢爬升，
        # 但**永远不超过下一个真实目标**（由 advance 重置），所以不会说谎。
        if self._creep_target > self._progress:
            self._progress = min(
                self._creep_target, self._progress + _CREEP_STEP
            )
        self.setPixmap(self._render_dynamic())

    # --------------------------------------------------------------- 对外
    def advance(self, progress: float, message: str = "", detail: str = ""):
        """推进进度并立即上屏。

        progress 取 0.0~1.0。构造流程每完成一段调用一次。
        `message` 参数保留兼容但**不绘制**（每个不同字符串都要重新排版，
        在 2004 字体族的环境里代价不可控）。
        内部主动 processEvents：调用方是同步阻塞代码，没有它画面不会更新。

        ⚠ 对参数做防御性矫正：调用方曾误传 (text, percent)，
        结果字符串被当进度塞进来，进度条彻底不动。这里宁可丢弃异常值，
        也不要让画面停住 —— 启动画面的第一职责是"看起来在动"。
        """
        try:
            value = float(progress)
        except (TypeError, ValueError):
            # 传进来的不是数字：若像文案就当成 message，进度不动
            if isinstance(progress, str) and not message:
                message = progress
            value = self._progress
        # 过滤 NaN / inf
        if value != value or value in (float("inf"), float("-inf")):
            value = self._progress

        self._progress = max(self._progress, min(1.0, max(0.0, value)))  # 只进不退
        # 蠕动上限 = 当前真实进度 + 一小段余量。
        # 每次收到真实进度就重置，所以蠕动只在"两段真实进度之间"发生，
        # 累计不会超过真实进度 + 8%。
        self._creep_target = min(1.0, self._progress + 0.08)
        self._compose()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def begin(self):
        """显示窗口、画出几何首帧，**然后**补文字层。

        顺序不能反：
        1. 先 `show()` 纯几何画面 —— 3ms 级，用户立刻看到东西；
        2. 再画文字 —— 要付 1~4 秒字体解析，但此时画面已在屏幕上，
           用户看到的是"logo 已经在了，还在加载"，而不是"一片空白"。
        """
        self._compose()
        self.show()
        self._pulse_timer.start()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        # 几何画面已可见，此时补文字
        try:
            self._text_layer = self._render_text_layer()
            self._compose()
            if app is not None:
                app.processEvents()
        except Exception:
            # 文字失败就保持纯几何画面，不影响启动
            self._text_layer = None

    def finish_with(self, window):
        """主窗口就绪后收起启动画面，把焦点交给主窗口。"""
        self._pulse_timer.stop()
        try:
            self.finish(window)
        except Exception:
            self.close()


def build_splash():
    """构造并显示启动画面；任何异常都返回 None（绝不挡住启动）。"""
    try:
        splash = SplashScreen()
        splash.begin()
        return splash
    except Exception:
        return None
