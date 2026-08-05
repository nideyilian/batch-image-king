# QML Content Sources Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 QML 工作台加入图片素材文件夹和多行文字变量编辑，使新建项目可直接产生批量变化。

**Architecture:** `WorkspaceViewModel` 作为 QML 与真实图层模型之间的唯一写入边界，负责路径校验、历史记录、缓存失效与预览刷新。`Main.qml` 根据图层类型显示图片或文字内容区块，并通过文件/文件夹对话框调用 ViewModel 命令。

**Tech Stack:** Python 3、PySide6 QObject/QML、Qt Quick、Pillow、pytest。

---

### Task 1: 内容源 ViewModel 合约

**Files:**
- Create: `tests/test_qml_content_sources.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1:** 编写图片源属性、文件夹计数、创建文件夹图层、替换源和随机预览的失败测试。

**Step 2:** 编写文字内容、绑定模式、候选数量、字号及撤销恢复的失败测试。

**Step 3:** 运行 `python -m pytest tests/test_qml_content_sources.py -v`，确认新合约尚未实现。

**Step 4:** 实现只读属性和专用 Slot，统一调用历史记录、缓存清理和预览刷新。

**Step 5:** 再次运行测试并确认通过。

### Task 2: QML 上下文属性面板

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1:** 增加图片文件夹对话框和顶部添加素材文件夹按钮。

**Step 2:** 在右侧属性栏加入图片“内容源”和文字“文字内容”区块。

**Step 3:** 实现多行编辑提交、模式分段控件、路径省略、素材计数和随机预览命令。

**Step 4:** 扩充 QML 源码合约和离屏烟雾测试。

### Task 3: 保存往返与回归

**Files:**
- Modify: `tests/test_qml_content_sources.py`
- Modify: `app/qml/README.md`

**Step 1:** 保存包含文件夹图片源和多行文字变量的 `.cmp`，重新加载并断言配置保持。

**Step 2:** 更新 QML 工作台能力说明和启动参数。

**Step 3:** 运行内容源、文档桥接、批量导出和 QML 烟雾测试。

### Task 4: 视觉验收与提交

**Files:**
- Modify: `app/qml/preview.png`

**Step 1:** 在 1280x760 和 1600x960 下检查图片与文字内容面板。

**Step 2:** 运行 `python -m compileall -q app/qml tests` 与 `python -m pytest -m unit`。

**Step 3:** 精确暂存本阶段文件并提交 `feat(qml): add content source editing`。

**Step 4:** 重启可见 QML 工作台并确认窗口标题。
