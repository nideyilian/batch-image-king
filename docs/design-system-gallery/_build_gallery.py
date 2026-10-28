"""生成组件与图标展示页（单文件 HTML，离线可用）。

2026-10-28 第二版：架构调整后重写。
  - 弃用 app/ui/components（shadcn 组件库）
  - 图标统一到 app/qml/icons/*.svg（Lucide，98 个）

数据全部来自真实源码与真实渲染：
  - 经典界面截图：_gallery_assets/classic_*.png（真实 MainWindow 离屏渲染）
  - 图标：app/qml/icons/*.svg 的实际 path 数据
  - 语义映射：app/ui/icon_library.py 的 IconName + 别名表
  - 令牌：app/ui/tokens_v2.py / design_spec.py 的实际取值
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
ASSETS = os.path.join(ROOT, "_gallery_assets")
OUT = os.path.join(ROOT, "组件库与图标库.html")

svg_map = json.load(open(os.path.join(ASSETS, "icons_svg.json"), encoding="utf-8"))

# ── 语义表：从源码解析，不手抄 ──────────────────────────────────
from app.ui.icon_library import AVAILABLE, IconName, _ALIAS

semantic = {
    k: v for k, v in vars(IconName).items()
    if k.isupper() and isinstance(v, str)
}


def svg_icon(body, cls="ico", stroke="2"):
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


# ── 图标网格：98 个 Lucide ───────────────────────────────────────
lucide_cards = "\n".join(
    f'<button class="icell" data-name="{n}" title="点击复制图标名">'
    f'{svg_icon(b)}<span>{n}</span></button>'
    for n, b in svg_map.items())

# ── 语义映射按源码分组 ──────────────────────────────────────────
src = open(os.path.join(ROOT, "app/ui/icon_library.py"), encoding="utf-8").read()
block = src.split("class IconName:")[1].split("#: 旧业务名")[0]
groups, cur = [], "图层与可见性"
for line in block.splitlines():
    c = line.strip()
    if c.startswith("# ") and not re.match(r"# [A-Z_]+", c):
        cur = c[2:].strip()
    m = re.match(r'([A-Z_0-9]+)\s*=\s*"([^"]+)"', c)
    if m:
        groups.append((cur, m.group(1), m.group(2)))

sem_html = ""
last, opened = None, False
for g, k, v in groups:
    if g != last:
        if opened:
            sem_html += "</div></div>"
        sem_html += f'<div class="mgroup"><span class="mgroup-t">{g}</span><div class="mgrid">'
        opened = True
        last = g
    sem_html += (f'<span class="mtag"><b>{k.lower().replace("_", "")}</b>'
                 f'<i>{v}</i></span>')
if opened:
    sem_html += "</div></div>"

# ── 别名表 ──────────────────────────────────────────────────────
alias_rows = "\n".join(
    f'<tr><td class="mono">{old}</td><td class="mono dim">{new}</td>'
    f'<td>{"✓" if new in AVAILABLE else "✗ 缺失"}</td></tr>'
    for old, new in sorted(_ALIAS.items()))

# ── 真实界面截图 ────────────────────────────────────────────────
SHOTS = [
    ("classic_main.png", "经典界面 · 主窗口",
     "真实 MainWindow 离屏渲染（1600×1000）。画布区为空文档，所以中间是黑的 —— 这是真实启动状态。"
     "图标全部为 Lucide SVG；主工具栏用纯文字模式以容纳右侧对齐栏。", " wide"),
    ("classic_icons_board.png", "界面里的纯图标按钮",
     "从真实主窗口提取的 8 个纯图标按钮（40px 位图，2 倍显示）。"
     "这是「图标已真实应用」的直接证据：全部 24×24 按钮、16px 图标、同一套 Lucide。", " wide"),
    ("classic_layerbar.png", "图层面板底部工具条",
     "2 倍放大。新增 / 删除 / 上移 / 下移 / 随机 / 绑定 / 尺寸匹配，同一套 Lucide、同一尺寸。", ""),
]
shots_html = "\n".join(
    f'''<figure class="shot{wide}">
      <img src="_gallery_assets/{f}" alt="{t}" loading="lazy">
      <figcaption><strong>{t}</strong><span>{d}</span></figcaption>
    </figure>''' for f, t, d, wide in SHOTS)

# ── 统计 ────────────────────────────────────────────────────────
STATS = [
    (str(len(AVAILABLE)), "Lucide SVG 图标", "app/qml/icons/，stroke 2px 统一"),
    (str(len(semantic)), "语义图标名", "icon_library.IconName"),
    (str(len(_ALIAS)), "旧名兼容映射", "别名表，迁移零改动"),
    ("0", "字符图标残留", "旧 42 个字符图标已移除"),
]

# ── 改动清单 ────────────────────────────────────────────────────
CHANGES = [
    ("图标真源", "icon_manager.py 内嵌 51 个手写 path + 42 个字符图标",
     "app/qml/icons/*.svg（Lucide 98 个），QWidget 与 QML 共用"),
    ("图标渲染", "QPainter 画手写 path；缺图标时降级画字符",
     "QSvgRenderer 渲染真实 SVG，currentColor 替换为目标色"),
    ("icon_manager", "图标实现本体",
     "退化为兼容层，64 个既有调用点零改动转调新库"),
    ("shadcn 组件库", "app/ui/components/ 被 3 个业务文件引用",
     "弃用。业务依赖已全部解除，仅剩演示页自身"),
    ("FlowLayout", "放在组件库 layout.py 里",
     "迁到 app/ui/flow_layout.py —— 布局原语，不是视觉组件"),
    ("状态指示器", "把字符（✎ ● ○）拼进 QLabel 文字",
     "QLabel 贴真实 SVG 位图，颜色随状态语义"),
    ("Toast", "QLabel 子类 + 字符图标 + QSS 背景",
     "QWidget 组合 + SVG 图标 + paintEvent 自绘背景"),
    ("绑定对话框", "标题与分析结果里拼字符（∞ ✗ ✓）",
     "标题用 SVG 图标行；纯文本改用 [无效]/[完成] 语义前缀"),
]

changes_html = "\n".join(
    f'<tr><td><span class="cat">{a}</span></td><td class="dim">{b}</td><td>{c}</td></tr>'
    for a, b, c in CHANGES)

# ── 令牌 ────────────────────────────────────────────────────────
from app.ui.tokens_v2 import Color as C2

TOKENS_COLOR = [
    ("canvas", C2.canvas, "画布工作区，全站最深"),
    ("surface_base", C2.surface_base, "应用底，比画布略亮"),
    ("surface_1", C2.surface_1, "侧栏 / 面板"),
    ("surface_2", C2.surface_2, "卡片 / 分组"),
    ("surface_3", C2.surface_3, "输入框 / 下拉"),
    ("surface_4", C2.surface_4, "弹层 / 悬浮"),
    ("surface_selected", C2.surface_selected, "选中行，靛蓝低饱和底"),
    ("border_subtle", C2.border_subtle, "分割线，亮度差仅 3"),
    ("text_primary", C2.text_primary, "主文字"),
    ("text_secondary", C2.text_secondary, "次级文字"),
    ("text_muted", C2.text_muted, "提示文字"),
    ("text_disabled", C2.text_disabled, "禁用"),
    ("accent", C2.accent, "品牌靛蓝，Linear 同色系"),
    ("accent_hover", C2.accent_hover, "hover 更深"),
    ("success", C2.success, "成功"),
    ("warning", C2.warning, "警告"),
    ("danger", C2.danger, "危险填充（压白字达标）"),
    ("danger_emphasis", C2.danger_emphasis, "危险图形 / 文字（暗底够亮）"),
    ("info", C2.info, "信息"),
]
color_html = "\n".join(
    f'<div class="sw"><span class="chip" style="background:{v}"></span>'
    f'<div><code>{k}</code><b>{v}</b><i>{d}</i></div></div>'
    for k, v, d in TOKENS_COLOR)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>批图王 · 组件与图标</title>
<style>
:root{{
  --canvas:#08090A; --base:#0A0B0D; --s1:#0F1011; --s2:#161719; --s3:#1D1F21; --s4:#23252A;
  --sel:#1F2437; --line:#141619; --t1:#F7F8F8; --t2:#B4BCC6; --t3:#949CA6; --tm:#8E97A1;
  --accent:#5E6AD2; --accent-h:#4F5ABF; --ok:#3DD68C; --warn:#FF8A3D; --danger:#E5484D;
  --mono:"Cascadia Mono","Consolas",monospace;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--base);color:var(--t1);
  font:13px/1.65 "Microsoft YaHei UI","Microsoft YaHei",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;}}
a{{color:inherit;text-decoration:none}}
code,.mono{{font-family:var(--mono)}}

.wrap{{display:grid;grid-template-columns:232px minmax(0,1fr);max-width:1520px;margin:0 auto}}
aside{{position:sticky;top:0;height:100vh;padding:26px 18px;border-right:1px solid var(--line);
  background:var(--s1);overflow-y:auto}}
aside .brand{{font-size:14px;font-weight:700;margin-bottom:3px}}
aside .ver{{font-size:11px;color:var(--tm);margin-bottom:22px;font-family:var(--mono)}}
nav a{{display:block;padding:6px 9px;border-radius:5px;color:var(--t2);font-size:12px;
  margin-bottom:1px;transition:.12s}}
nav a:hover{{background:var(--s3);color:var(--t1)}}
nav a.active{{background:var(--sel);color:#E4E7FF}}
nav .grp{{font-size:10px;color:#6B7079;letter-spacing:1px;text-transform:uppercase;
  margin:16px 0 6px;padding-left:9px}}
main{{padding:0 46px 100px;min-width:0}}

.hero{{padding:60px 0 38px;border-bottom:1px solid var(--line)}}
.hero h1{{font-size:30px;font-weight:700;letter-spacing:-.4px;margin-bottom:12px}}
.hero p{{color:var(--t2);max-width:680px;font-size:13.5px}}
.hero .meta{{margin-top:18px;display:flex;gap:8px;flex-wrap:wrap}}
.pill{{font-size:11px;padding:3px 10px;border-radius:999px;background:var(--s3);
  color:var(--t2);font-family:var(--mono)}}
.pill.on{{background:var(--sel);color:#C9CEFF}}
.pill.good{{background:#14321f;color:#7BE8B0}}

.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);
  margin:32px 0 0;border-radius:8px;overflow:hidden}}
.stat{{background:var(--s1);padding:18px 20px}}
.stat b{{display:block;font-size:26px;font-weight:700;letter-spacing:-.5px;
  font-family:var(--mono)}}
.stat span{{display:block;font-size:12px;color:var(--t2);margin-top:2px}}
.stat i{{display:block;font-size:10.5px;color:#6B7079;margin-top:5px;font-style:normal;
  font-family:var(--mono)}}

section{{padding-top:58px;scroll-margin-top:10px}}
section>h2{{font-size:19px;font-weight:700;letter-spacing:-.2px;margin-bottom:6px;
  display:flex;align-items:baseline;gap:10px}}
section>h2 em{{font-size:11px;font-weight:400;color:var(--tm);font-style:normal;
  font-family:var(--mono)}}
.lead{{color:var(--t2);font-size:13px;max-width:740px;margin-bottom:22px}}
h3{{font-size:14px;font-weight:600;margin:32px 0 12px;display:flex;align-items:center;gap:8px}}
h3::before{{content:"";width:3px;height:13px;background:var(--accent);border-radius:2px}}

.note{{border-left:2px solid var(--accent);background:var(--s1);padding:11px 15px;
  border-radius:0 6px 6px 0;font-size:12.5px;color:var(--t2);margin:14px 0}}
.note b{{color:var(--t1)}}
.note.ok{{border-color:var(--ok)}}
.note.warn{{border-color:var(--warn)}}
.note.danger{{border-color:var(--danger)}}

.shots{{display:flex;flex-direction:column;gap:16px}}
.shots .row{{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}}
.shot{{background:var(--s1);border-radius:8px;overflow:hidden;
  display:block;width:fit-content;max-width:100%}}
.shot img{{display:block;width:auto;height:auto;background:var(--canvas);max-width:100%}}
.shot.wide{{width:100%}}
.shot.wide img{{width:100%;max-width:100%}}
.shot figcaption{{padding:11px 14px;border-top:1px solid var(--line);max-width:420px}}
.shot strong{{display:block;font-size:12.5px;font-weight:600;margin-bottom:2px}}
.shot span{{font-size:11.5px;color:var(--tm);line-height:1.55}}

table{{width:100%;border-collapse:collapse;font-size:12.5px}}
thead th{{text-align:left;font-size:10.5px;letter-spacing:.8px;text-transform:uppercase;
  color:#6B7079;font-weight:500;padding:0 12px 9px;border-bottom:1px solid var(--line)}}
tbody td{{padding:10px 12px;border-bottom:1px solid #101113;vertical-align:top;color:var(--t2)}}
tbody tr:hover td{{background:var(--s1)}}
.cat{{display:inline-block;font-size:11px;color:var(--t1);background:var(--s3);
  padding:2px 8px;border-radius:4px;white-space:nowrap}}
td.mono{{font-family:var(--mono);font-size:11.5px;color:var(--t1)}}
td.dim{{color:#8A9099;font-size:11.5px}}

.swgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:10px}}
.sw{{display:flex;gap:10px;align-items:center;background:var(--s1);border-radius:6px;padding:9px 11px}}
.chip{{width:30px;height:30px;border-radius:5px;flex:0 0 30px;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.07)}}
.sw code{{display:block;font-size:11px;color:var(--t1)}}
.sw b{{font-size:10.5px;color:var(--tm);font-family:var(--mono);font-weight:400}}
.sw i{{display:block;font-size:10.5px;color:#6B7079;font-style:normal;margin-top:1px}}

.scale{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}
.spec{{background:var(--s1);border-radius:6px;padding:12px 14px}}
.spec h5{{font-size:11px;color:var(--tm);font-weight:400;margin-bottom:8px;
  font-family:var(--mono)}}
.spec .line{{display:flex;justify-content:space-between;font-size:11.5px;
  padding:3px 0;color:var(--t2)}}
.spec .line span:last-child{{font-family:var(--mono);color:var(--t1)}}

.toolbar{{display:flex;gap:10px;align-items:center;margin-bottom:14px}}
#q{{flex:1;max-width:340px;background:var(--s3);border:none;border-radius:6px;
  padding:8px 12px;color:var(--t1);font-size:12.5px;outline:none}}
#q:focus{{box-shadow:inset 0 0 0 1px var(--accent)}}
#cnt{{font-size:11px;color:var(--tm);font-family:var(--mono)}}
.icogrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:6px}}
.icell{{display:flex;flex-direction:column;align-items:center;gap:7px;padding:13px 6px 10px;
  background:var(--s1);border:none;border-radius:6px;cursor:pointer;color:var(--t2);
  transition:.12s;font-family:inherit}}
.icell:hover{{background:var(--s3);color:var(--t1);transform:translateY(-1px)}}
.icell.copied{{box-shadow:inset 0 0 0 1px var(--accent)}}
.icell svg{{width:22px;height:22px;display:block}}
.icell span{{font-size:9.5px;color:#7B828C;font-family:var(--mono);text-align:center;
  line-height:1.3;overflow-wrap:anywhere}}

.mgroup{{margin-bottom:16px}}
.mgroup-t{{display:block;font-size:10.5px;color:#6B7079;letter-spacing:.6px;
  margin-bottom:7px;font-family:var(--mono)}}
.mgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:5px}}
.mtag{{display:flex;flex-direction:column;gap:1px;background:var(--s1);border-radius:5px;
  padding:7px 10px;font-size:11px}}
.mtag b{{font-weight:400;color:var(--t1);font-family:var(--mono);font-size:11px}}
.mtag i{{color:#6B7079;font-style:normal;font-family:var(--mono);font-size:10px}}

footer{{margin-top:70px;padding-top:22px;border-top:1px solid var(--line);
  font-size:11px;color:#6B7079;font-family:var(--mono);line-height:1.9}}

@media(max-width:1080px){{
  .wrap{{grid-template-columns:1fr}}
  aside{{display:none}}
  main{{padding:0 20px 60px}}
  .stats{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="wrap">
<aside>
  <div class="brand">批图王 · 界面资产</div>
  <div class="ver">v1.2.0 / 2026-10-28 改版</div>
  <nav id="nav">
    <div class="grp">总览</div>
    <a href="#overview" class="active">这次改了什么</a>
    <a href="#live">真实界面</a>
    <div class="grp">图标库</div>
    <a href="#icons">Lucide SVG · {len(AVAILABLE)}</a>
    <a href="#semantic">语义名与映射</a>
    <a href="#alias">旧名兼容表 · {len(_ALIAS)}</a>
    <div class="grp">设计规范</div>
    <a href="#tokens">设计令牌</a>
    <a href="#usage">怎么用</a>
  </nav>
</aside>

<main>
<div class="hero">
  <h1>组件与图标</h1>
  <p>2026-10-28 改版：不再使用 shadcn 组件库，图标统一到 Lucide SVG 并<b>真实接入经典界面</b>。
     本页所有界面截图都由真实 <code>MainWindow</code> 离屏渲染生成，所有图标都来自仓库里的真实 SVG 文件。</p>
  <div class="meta">
    <span class="pill">Python + PySide6</span>
    <span class="pill good">Lucide SVG 单一真源</span>
    <span class="pill">shadcn 组件库已弃用</span>
    <span class="pill">offscreen 真实渲染</span>
  </div>
  <div class="stats">
    {"".join(f'<div class="stat"><b>{n}</b><span>{t}</span><i>{s}</i></div>' for n, t, s in STATS)}
  </div>
</div>

<section id="overview">
  <h2>这次改了什么 <em>changelog</em></h2>
  <p class="lead">两件事：<b>图标换成 Lucide SVG 真源</b>、<b>弃用 shadcn 组件库</b>。下面每一行都是实际改了代码的位置。</p>
  <table>
    <thead><tr><th>项目</th><th>改之前</th><th>改之后</th></tr></thead>
    <tbody>{changes_html}</tbody>
  </table>

  <div class="note ok">
    <b>怎么确认「真实应用」而不是「改了代码没生效」：</b>
    启动真实 <code>MainWindow</code>，遍历界面上全部 102 个按钮 —— 35 个带图标，
    逐个取位图检查像素，<b>0 个空白</b>；图标尺寸落在 16 / 18 / 20 三档。
    下面「真实界面」一栏就是那次运行截的图。
  </div>

  <div class="note">
    <b>保留了什么：</b><code>icon_manager.py</code> 没有删，它退化成兼容层，
    让 64 个既有调用点零改动拿到新图标。<code>FlowLayout</code> 从组件库里<b>择出来</b>
    迁到 <code>app/ui/flow_layout.py</code> —— 它解决的是真实的按钮换行缺陷，不是视觉组件。
  </div>
</section>

<section id="live">
  <h2>真实界面 <em>real render</em></h2>
  <p class="lead">下面不是设计稿，是运行起来的主窗口截图。图标来自 <code>app/qml/icons/*.svg</code>。</p>
  <div class="shots">{shots_html}</div>
</section>

<section id="icons">
  <h2>Lucide SVG 图标 <em>app/qml/icons · {len(AVAILABLE)} 个</em></h2>
  <p class="lead">
    全部来自 <code>lucide-static v1.28.0</code>（ISC 许可）。24×24 视图、<code>stroke-width="2"</code>、
    圆角端点 —— 98 个文件的几何规范完全一致（有契约测试守着）。
    <b>QWidget 与 QML 共用同一批文件</b>，一个图标只有一份定义。点击图标名可复制。
  </p>
  <div class="toolbar">
    <input id="q" placeholder="搜索图标名…" autocomplete="off">
    <span id="cnt">{len(AVAILABLE)} 个</span>
  </div>
  <div class="icogrid" id="lucideGrid">{lucide_cards}</div>
</section>

<section id="semantic">
  <h2>语义名与映射 <em>IconName · {len(semantic)} 个</em></h2>
  <p class="lead">
    <code>IconName</code> 用<b>功能语义</b>（save / delete）而非形状（floppy / trash）命名。
    换图标集时只改这张表，业务代码不动 —— 这是「不再出现两套图标混用」的结构保证。
  </p>
  {sem_html}
</section>

<section id="alias">
  <h2>旧名兼容表 <em>_ALIAS · {len(_ALIAS)} 条</em></h2>
  <p class="lead">
    旧代码传 <code>icon('delete')</code>、<code>icon('zoom_in')</code> 仍然有效 —— 别名表把它们
    映射到 Lucide 名。这张表覆盖了 <code>icon_manager</code> 时代全部业务名，所以 64 个调用点
    一行都不用改。右侧 ✓ 表示目标文件真实存在。
  </p>
  <div class="note warn">
    <b>顺带修掉两个历史 bug：</b><code>blend</code> 和 <code>opacity</code> 在旧
    <code>icon_manager</code> 里<b>根本没有对应图标</b>，<code>get_icon_text()</code> 直接返回
    <code>?</code>（状态栏里一直显示问号）。现在分别映射到 <code>layers-3</code> 和
    <code>circle-dot</code>。
  </div>
  <table>
    <thead><tr><th>旧业务名</th><th>Lucide 图标</th><th>文件存在</th></tr></thead>
    <tbody>{alias_rows}</tbody>
  </table>
</section>

<section id="tokens">
  <h2>设计令牌 <em>tokens_v2 + design_spec</em></h2>
  <p class="lead">唯一事实来源：<code>app/ui/tokens_v2.py</code>（语义色）与
     <code>app/ui/design_spec.py</code>（强制尺寸档位）。组件库弃用后，这两处是<b>唯一</b>该去查规范的地方。</p>

  <h3>语义色板（实际取值）</h3>
  <div class="swgrid">{color_html}</div>

  <h3>强制档位</h3>
  <div class="scale">
    <div class="spec"><h5>Scale · 控件高度</h5>
      <div class="line"><span>SM 工具条 / 底栏</span><span>24</span></div>
      <div class="line"><span>MD 默认</span><span>28</span></div>
      <div class="line"><span>LG 主操作</span><span>36</span></div>
    </div>
    <div class="spec"><h5>Space · 间距（4px 栅格）</h5>
      <div class="line"><span>XS</span><span>4</span></div>
      <div class="line"><span>SM</span><span>8</span></div>
      <div class="line"><span>MD</span><span>12</span></div>
      <div class="line"><span>LG</span><span>16</span></div>
      <div class="line"><span>XL</span><span>24</span></div>
    </div>
    <div class="spec"><h5>Radius · 圆角</h5>
      <div class="line"><span>SM 色块 / 标签</span><span>4</span></div>
      <div class="line"><span>MD 按钮 / 输入</span><span>6</span></div>
      <div class="line"><span>LG 面板</span><span>8</span></div>
      <div class="line"><span>XL 对话框</span><span>12</span></div>
    </div>
    <div class="spec"><h5>FontSize · 字号</h5>
      <div class="line"><span>CAPTION 角标</span><span>11</span></div>
      <div class="line"><span>SMALL 次要</span><span>12</span></div>
      <div class="line"><span>BASE 正文</span><span>13</span></div>
      <div class="line"><span>MD 小标题</span><span>15</span></div>
      <div class="line"><span>LG 区块</span><span>18</span></div>
      <div class="line"><span>XL 大标题</span><span>24</span></div>
    </div>
    <div class="spec"><h5>IconSize · 图标（3 档）</h5>
      <div class="line"><span>SM 内联文字旁</span><span>16</span></div>
      <div class="line"><span>MD 工具栏默认</span><span>20</span></div>
      <div class="line"><span>LG 面板头</span><span>24</span></div>
    </div>
    <div class="spec"><h5>Opacity / Motion</h5>
      <div class="line"><span>DISABLED</span><span>0.38</span></div>
      <div class="line"><span>HOVER</span><span>0.08</span></div>
      <div class="line"><span>FAST 状态切换</span><span>120ms</span></div>
      <div class="line"><span>BASE 展开收起</span><span>180ms</span></div>
    </div>
  </div>
</section>

<section id="usage">
  <h2>怎么用 <em>usage</em></h2>
  <p class="lead">新代码只走下面这一套。不要再用 <code>app/ui/components/</code>，也不要用字符图标。</p>

  <h3>图标</h3>
  <div class="note">
    <code>from app.ui.icon_library import icon, icon_pixmap, icon_button, IconName</code><br><br>
    <code>btn.setIcon(icon("delete"))</code> 　　业务名，走别名表<br>
    <code>btn.setIcon(icon(IconName.DELETE, color=Color.danger))</code> 　　语义常量 + 语义色<br>
    <code>label.setPixmap(icon_pixmap("link", 16, Color.accent))</code> 　　贴到 QLabel<br>
    <code>icon_button("zoom_in", size="md", tooltip="放大")</code> 　　尺寸受 design_spec 约束
  </div>

  <h3>尺寸与颜色</h3>
  <div class="note">
    <code>from app.ui.design_spec import Scale, Space, Radius, FontSize, IconSize</code><br>
    <code>from app.ui.tokens_v2 import Color, Typography</code><br><br>
    控件高度只准取 <code>Scale.PX</code> 的 24 / 28 / 36；间距只准取 <code>Space</code> 的 4/8/12/16/24；
    图标只准取 <code>IconSize</code> 的 16/20/24。写死像素会被 <code>test_ui_rules.py</code> 拦下来。
  </div>

  <h3>不要做的事</h3>
  <div class="note danger">
    ✗ <code>from app.ui.components import ...</code> —— 组件库已弃用，有契约测试拦截<br>
    ✗ <code>IconManager.get_icon_text()</code> —— 已废弃，字符图标已彻底移除<br>
    ✗ 自己写 <code>&lt;path d="..."&gt;</code> 手绘图标 —— 与 Lucide 的几何规范对不上<br>
    ✗ 在 <code>app/qml/icons/</code> 放非 Lucide 来源的 SVG —— 有来源校验测试
  </div>
</section>

<footer>
  数据来源：app/qml/icons/（{len(AVAILABLE)} 个 SVG）、app/ui/icon_library.py（{len(semantic)} 语义名 + {len(_ALIAS)} 别名）、
  app/ui/tokens_v2.py、app/ui/design_spec.py<br>
  界面截图由真实 MainWindow 离屏渲染生成（_gallery_classic.py），非样式复刻。
</footer>
</main>
</div>

<script>
function bindGrid(gridId, inputId, cntId, total){{
  var grid = document.getElementById(gridId);
  var input = document.getElementById(inputId);
  var cnt = document.getElementById(cntId);
  var cells = [].slice.call(grid.querySelectorAll('.icell'));
  input.addEventListener('input', function(){{
    var q = input.value.trim().toLowerCase();
    var shown = 0;
    cells.forEach(function(c){{
      var hit = !q || c.dataset.name.toLowerCase().indexOf(q) > -1;
      c.style.display = hit ? '' : 'none';
      if (hit) shown++;
    }});
    cnt.textContent = q ? (shown + ' / ' + total + ' 个') : (total + ' 个');
  }});
  cells.forEach(function(c){{
    c.addEventListener('click', function(){{
      var name = c.dataset.name;
      if (navigator.clipboard) navigator.clipboard.writeText(name);
      c.classList.add('copied');
      var label = c.querySelector('span');
      var old = label.textContent;
      label.textContent = '已复制';
      setTimeout(function(){{ label.textContent = old; c.classList.remove('copied'); }}, 700);
    }});
  }});
}}
bindGrid('lucideGrid', 'q', 'cnt', {len(AVAILABLE)});

var links = [].slice.call(document.querySelectorAll('#nav a'));
var secs = links.map(function(a){{ return document.querySelector(a.getAttribute('href')); }});
function sync(){{
  var y = window.scrollY + 120, idx = 0;
  secs.forEach(function(s, i){{ if (s && s.offsetTop <= y) idx = i; }});
  links.forEach(function(a, i){{ a.classList.toggle('active', i === idx); }});
}}
window.addEventListener('scroll', sync, {{ passive: true }});
sync();
</script>
</body>
</html>
"""

open(OUT, "w", encoding="utf-8").write(html)
print("written:", OUT, len(html), "chars")
