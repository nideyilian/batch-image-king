# 归档文档

这里存放的是**历史文档**。保留是为了回答"当初为什么这么定"，**不是现状说明**。

当前的界面规范只有两份：

| 文档 | 管什么 |
|---|---|
| 根目录 `DESIGN.md` | 概览、视觉规则、布局、边界、取值依据 |
| `docs/hermes-desktop-design-system.md` | 详细契约：逐个令牌、组件、工作台结构 |

`app/ui` 残留的 QWidget 弹窗走 `app/ui/tokens_v2.py`，见 `DESIGN.md` 附录 A。

---

## 为什么这些被归档

项目在三个月内换过三次视觉方向，每次都留下一份规范，于是 `docs/` 攒了九份，
新人无法判断该看哪份。归档不是否定它们，是给它们定一个位置。

| 文档 | 时期 | 描述的方向 | 为什么不再有效 |
|---|---|---|---|
| `UI_SPEC.md` | 经典版 | Qt Widgets 主窗口、QSS 样式表 | 经典版主界面已下线；含 `main_window` / `QSS` 全部失效 |
| `DESIGN_SYSTEM_SHADCN.md` | 经典版 | 深色工作台、shadcn 命名 | 同上下线；皮肤契约基于 QSS |
| `UI设计规范.md` | 经典版 | 全局 QSS 统一、属性面板一致性 | 同上下线；还含已删除的 AI 生图模块 |
| `设计规范覆盖审计.md` | 经典版 | 深色规范的覆盖率统计 | 审计对象已不存在 |
| `qml-design-system.md` | QML 第一代 | 深色生产控制台 | 检查器 336px、标准控件高 30px，与现状（320px / 24-28px）不符；已被 `hermes-desktop-design-system.md` 取代 |
| `ui-parameter-layout-guidelines.md` | 通用 | 参数行布局原则 | **原则仍成立**，但全部示例是 `QHBoxLayout` / `QGridLayout`，QML 用不上；原则已被 `hermes-desktop-design-system.md` §5 以更精确的令牌形式吸收 |
| `THEMES.md` | 选型期 | 10 个视觉方案对照与推荐 | 决策已结束（选中 Hermes 浅色）；留作"当时还考虑过什么" |
| `UI_REFACTOR_PLAN.md` | 选型期 | 重构方案评估与路线 | 路线已执行完毕 |

## 三条注意

1. **不要照着这里的色值改代码**。文中的主色经历过 `#2F9CF4` → `#2378C4` → `INDIGO_600`
   三次变化，全部已过期。现行色值只看 `app/qml/components/Theme.qml`。
2. **不要往这里新增文件当"暂存区"**。归档是终态；新文档要么进 `docs/`，要么别写。
3. `THEMES.md` 与 `UI_REFACTOR_PLAN.md` 记录了当时的取舍理由，改视觉方向前值得读一遍
   —— 避免重新论证已经论证过的事。
