# QML Production Console Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 建立完整的 QML 生产控制台设计系统，统一图标和基础组件，并将现有 QML 工作台迁移到该系统。

**Architecture:** `Theme.qml` 提供设计令牌，`AppIcons.qml` 提供语义图标名称，`AppIcon.qml` 负责 SVG 渲染，公共控件负责交互状态。`Main.qml` 只组合组件并连接既有 ViewModel，不改变文档和导出业务。

**Tech Stack:** Python 3、PySide6、Qt Quick/QML、Lucide SVG、pytest、PyInstaller。

---

### Task 1: 建立设计系统契约测试

**Files:**
- Create: `tests/test_qml_design_system.py`
- Read: `app/qml/components/Theme.qml`
- Read: `app/qml/Main.qml`

**Steps:**
1. 添加主题令牌、语义图标角色、组件 API 和禁止裸图标码点的断言。
2. 运行 `python -m pytest tests/test_qml_design_system.py -v`，确认测试先失败。
3. 后续任务完成后重跑并确认通过。

### Task 2: 引入 Lucide 资源和语义图标注册表

**Files:**
- Create: `app/qml/icons/*.svg`
- Create: `app/qml/components/AppIcons.qml`
- Modify: `app/qml/components/AppIcon.qml`
- Modify: `build.py`
- Modify: `批图王.spec`

**Steps:**
1. 从官方 `lucide-static` 包提取界面实际使用的 SVG。
2. 在 `AppIcons.qml` 建立语义名称与文件名映射。
3. 用 `AppIcon` 统一 SVG 尺寸、着色和兼容回退。
4. 把图标目录加入开发与 PyInstaller 数据文件。
5. 运行设计系统契约测试。

### Task 3: 扩展主题与基础组件

**Files:**
- Modify: `app/qml/components/Theme.qml`
- Modify: `app/qml/components/IconButton.qml`
- Modify: `app/qml/components/SelectBox.qml`
- Modify: `app/qml/components/FontSelectBox.qml`
- Modify: `app/qml/components/PropertySection.qml`
- Modify: `app/qml/components/ToggleSwitch.qml`
- Modify: `app/qml/components/ValueBox.qml`
- Create: `app/qml/components/AppButton.qml`
- Create: `app/qml/components/AppTextField.qml`
- Create: `app/qml/components/AppTextArea.qml`
- Create: `app/qml/components/SegmentedControl.qml`

**Steps:**
1. 补齐表面、文字、状态、字体、尺寸、焦点和动效令牌。
2. 让公共控件覆盖 normal、hover、pressed、focus、active、disabled。
3. 保留 `ValueBox` 和 `FontSelectBox` 的聚焦绑定保护。
4. 运行 QML 原生编辑测试和设计系统契约测试。

### Task 4: 迁移图层模型和主工作台图标

**Files:**
- Modify: `app/qml/viewmodels/layer_list_model.py`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_document_bridge.py`

**Steps:**
1. 在图层模型增加 `iconName` 角色并保持 `glyph` 兼容。
2. 将 `Main.qml` 的图标调用替换为语义 `iconName`。
3. 将主栏、工具轨、图层行、属性区、抽屉和状态栏对齐生产控制台令牌。
4. 运行 QML 图层、工作区和设计系统测试。

### Task 5: 统一输入、下拉、弹窗和导出界面

**Files:**
- Modify: `app/qml/Main.qml`

**Steps:**
1. 用公共输入组件替换可安全迁移的裸 `TextField` / `TextArea`。
2. 统一 Dialog、Drawer、Menu、状态提示与进度条表面。
3. 确认批量导出与多标签导出的高级设置和运行状态仍可见。
4. 运行 QML 批量导出、预设、绑定和尺寸匹配测试。

### Task 6: 视觉与全量回归

**Files:**
- Create: `.impeccable/mocks/qml-production-console-final-*.png`
- Modify: `DESIGN.md`

**Steps:**
1. 运行 `python -m pytest tests/test_qml_*.py -v`。
2. 运行 `python -m pytest`。
3. 使用 `qml_main.py --screenshot` 生成 1600 × 960、1280 × 760、1180 × 720 截图。
4. 运行 Impeccable 检测器一次，批量修复可确认问题。
5. 记录最终设计系统到 `DESIGN.md`，只提交本轮修改文件。

## 完成记录

- [x] 设计系统契约测试已建立并通过。
- [x] 86 个 Lucide SVG、语义注册表和 PyInstaller 资源路径已落地。
- [x] 主题、按钮、输入、菜单、弹窗、抽屉、进度和状态组件已统一。
- [x] `Main.qml` 已迁移到语义图标和公共组件，ViewModel 与业务契约保持不变。
- [x] 1180 × 720、1280 × 760、1600 × 960 的 100% 缩放截图已验收。
- [x] QML 测试：`165 passed`；Impeccable 检测：零发现。
- [x] 全量测试：`342 passed, 4 failed`。3 项失败来自 Python 3.8 不支持 `TemporaryDirectory(ignore_cleanup_errors=...)`，1 项来自既有 `app/ui/layer_size_match_dialog.py` 直接导入 `FastRenderer`，均不在本轮 QML 改动范围。
- [x] 根目录 `DESIGN.md` 与 `.impeccable/design.json` 已生成。
