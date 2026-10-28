"""为 10 个方案输出可量化指标，辅助选择。

指标：
  正文对比度    —— WCAG AA 要求 >= 4.5
  次要文字      —— >= 4.5
  提示文字      —— >= 4.5
  白字/主按钮   —— >= 4.5
  主色/底色     —— >= 3（可交互元素可识别）
  底色亮度      —— 越低越"暗色"，>0.5 即浅色主题
  长时间舒适度  —— 综合底色亮度与蓝光成分（估算，非医疗结论）
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "tools"))
from themes_10 import THEMES  # noqa: E402


def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def lum(h):
    r, g, b = _rgb(h)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def blue_share(h):
    """蓝光占比（粗略）：蓝通道 / 三通道总和。OLED 蓝光偏高的方案夜间更刺眼。"""
    r, g, b = _rgb(h)
    total = r + g + b
    return b / total if total else 0


rows = []
for t in THEMES:
    accent = t["accent"]
    # 浅色方案主按钮文字用白；深色也用白（07 用深字）
    on_accent = "#0B0B0B" if t["key"] == "07" else "#FFFFFF"

    body = ratio(t["text"], t["bg"])
    body_card = ratio(t["text"], t["s1"])
    sec = ratio(t["text2"], t["s1"])
    muted = ratio(t["muted"], t["s1"])
    btn = ratio(on_accent, accent)
    accent_vis = ratio(accent, t["bg"])
    bg_l = lum(t["bg"])
    bs = blue_share(t["bg"])

    # 判定
    issues = []
    if min(body, body_card) < 4.5:
        issues.append("正文")
    if sec < 4.5:
        issues.append("次要")
    if muted < 4.5:
        issues.append("提示")
    if btn < 4.5:
        issues.append("按钮字")
    if accent_vis < 3.0:
        issues.append("主色可见")

    rows.append(dict(
        key=t["key"], name=t["name"], ref=t["ref"],
        body=min(body, body_card), sec=sec, muted=muted,
        btn=btn, accent_vis=accent_vis,
        bg_l=bg_l, blue=bs,
        dark="暗" if bg_l < 0.2 else ("中" if bg_l < 0.5 else "浅"),
        issues=issues,
    ))

print("=" * 96)
print(f"{'#':3} {'方案':14} {'参考':20} {'正文':>5} {'次要':>5} {'提示':>5} {'按钮':>5} {'主色':>5}  {'底色':>5} {'明暗':>3} {'蓝光':>5}  问题")
print("-" * 96)
for r in rows:
    flag = "OK" if not r["issues"] else "/".join(r["issues"])
    print(f"{r['key']:3} {r['name']:14} {r['ref']:20} "
          f"{r['body']:5.2f} {r['sec']:5.2f} {r['muted']:5.2f} {r['btn']:5.2f} {r['accent_vis']:5.2f}  "
          f"{r['bg_l']:5.3f} {r['dark']:>3} {r['blue']*100:4.1f}%  {flag}")

print("=" * 96)
ok = [r for r in rows if not r["issues"]]
print(f"\n全部指标达标: {len(ok)}/10 → {', '.join(r['key'] + ' ' + r['name'] for r in ok)}")

print("\n【按底色明暗分组】")
for label in ("暗", "中", "浅"):
    g = [r for r in rows if r["dark"] == label]
    if g:
        print(f"  {label}色: {', '.join(r['key'] + ' ' + r['name'] for r in g)}")

print("\n【蓝光占比最低 3 个（夜间更舒适）】")
for r in sorted(rows, key=lambda x: x["blue"])[:3]:
    print(f"  {r['key']} {r['name']:14} 蓝光 {r['blue']*100:.1f}%")
