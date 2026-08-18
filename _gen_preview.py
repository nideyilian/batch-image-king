"""一次性脚本：把 Icons / Typography 两个分区注入 design_system_preview.html。"""
import sys, os
sys.path.insert(0, r"d:\AAA\批图王极速版20260520")
from app.ui.icon_manager import ICON_SVGS

BASE = r"d:\AAA\批图王极速版20260520\docs\design_system_preview.html"
with open(BASE, encoding="utf-8") as f:
    html = f.read()

# ---------- CSS ----------
CSS = """
  /* ---- Icons ---- */
  .icon-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 10px; }
  .icon-cell { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 4px; border: 1px solid var(--border); border-radius: var(--radius); }
  .icon-cell svg { width: 22px; height: 22px; stroke: var(--foreground); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .icon-cell .inm { font-size: 10px; color: var(--muted-foreground); }
  .icon-colors { display: flex; gap: 24px; margin-bottom: 14px; flex-wrap: wrap; }
  .icon-color { display: flex; flex-direction: column; align-items: center; gap: 4px; }
  .icon-color svg { width: 22px; height: 22px; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .icon-color .inm { font-size: 10px; color: var(--muted-foreground); }

  /* ---- Typography ---- */
  .typo { display: flex; flex-direction: column; gap: 8px; }
  .typo .h1 { font-size: 22px; font-weight: 700; color: var(--foreground); }
  .typo .h2 { font-size: 18px; font-weight: 700; color: var(--foreground); }
  .typo .h3 { font-size: 15px; font-weight: 500; color: var(--foreground); }
  .typo .lead { font-size: 15px; color: var(--muted-foreground); }
  .typo .text { color: var(--foreground); font-size: 13px; }
  .typo .muted { color: var(--muted-foreground); font-size: 13px; }
  .typo .small { color: var(--muted-foreground); font-size: 10px; }
  .typo .code { background: var(--muted); color: var(--foreground); border-radius: 4px; padding: 2px 6px; font-family: "Cascadia Code","Consolas",monospace; font-size: 11px; align-self: flex-start; }
  .typo .bq { border-left: 3px solid var(--border); color: var(--muted-foreground); padding: 2px 0 2px 12px; font-size: 13px; }
  .typo .kbd { background: var(--secondary); color: var(--foreground); border: 1px solid var(--border); border-radius: 4px; padding: 1px 7px; font-family: "Cascadia Code","Consolas",monospace; font-size: 10px; }
  .kbd-row { display: flex; gap: 6px; align-items: center; }
  .kbd-row .lbl { color: var(--muted-foreground); font-size: 11px; }
"""

if ".icon-grid" not in html:
    html = html.replace("</style>", CSS + "</style>", 1)

# ---------- Icons 分区 ----------
svg_tpl = '<svg viewBox="0 0 24 24"><path d="{d}"/></svg>'
names = sorted(ICON_SVGS.keys())

color_row = '<div class="icon-colors">'
for tok, var in (("foreground", "var(--foreground)"), ("primary", "var(--primary)"),
                 ("muted", "var(--muted-foreground)"), ("success", "var(--success)"),
                 ("destructive", "var(--destructive)")):
    inner = f'<svg viewBox="0 0 24 24" style="stroke:{var}"><path d="{ICON_SVGS["settings"]}"/></svg>'
    color_row += f'<div class="icon-color">{inner}<div class="inm">{tok}</div></div>'
color_row += "</div>"

grid = '<div class="icon-grid">'
for n in names:
    grid += (f'<div class="icon-cell"><svg viewBox="0 0 24 24"><path d="{ICON_SVGS[n]}"/></svg>'
             f'<div class="inm">{n}</div></div>')
grid += "</div>"

icons_section = f"""
    <!-- Icons -->
    <div class="section">
      <div class="sec-head"><div class="sec-title">Icons 图标</div><div class="sec-desc">lucide 风格内嵌 SVG，颜色取自主题令牌，主题切换实时生效；封装于 app/ui/components/icon</div></div>
      {color_row}
      <div class="sep"></div>
      {grid}
    </div>
"""

# ---------- Typography 分区 ----------
typo_section = """
    <!-- Typography -->
    <div class="section">
      <div class="sec-head"><div class="sec-title">Typography 排版</div><div class="sec-desc">Heading(H1/H2/H3) / Text / Lead / Muted / Small / Code / Blockquote / Kbd，由全局 QSS 的 role 驱动</div></div>
      <div class="typo">
        <div class="h1">一级标题 Heading 1</div>
        <div class="h2">二级标题 Heading 2</div>
        <div class="h3">三级标题 Heading 3</div>
        <div class="lead">引导段落 Lead：用于页面或区块开头，字号更大、颜色更弱，引导用户阅读。</div>
        <div class="text">正文 Text：常规阅读文本，使用前景色与基础字号，支持长段落自动换行，行高舒适。</div>
        <div class="muted">次要文本 Muted：用于辅助说明、注释、字段备注等弱信息。</div>
        <div class="small">小字 Small：用于极小的辅助信息，如脚注、版本号。</div>
        <div class="code">pip install -r requirements.txt</div>
        <div class="bq">引用 Blockquote：用于引用他人观点或文档摘录，左侧强调线，颜色更弱。</div>
        <div class="kbd-row"><span class="lbl">快捷键示例：</span><span class="kbd">Ctrl</span><span class="kbd">Shift</span><span class="kbd">S</span></div>
      </div>
    </div>
"""

if "<!-- Icons -->" not in html:
    html = html.replace("    <!-- Colors -->", icons_section + typo_section + "    <!-- Colors -->", 1)

with open(BASE, "w", encoding="utf-8") as f:
    f.write(html)
print("OK: sections injected; icons =", len(names))
