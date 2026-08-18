# QML 原生弹窗迁移计划

## 目标

QML 工作台中的业务弹窗统一使用现有暗色设计系统和 QML 组件，不再通过
`LegacyFeatureBridge` 打开 Qt Widgets 旧界面。Windows 文件和文件夹选择器继续使用
系统原生对话框。

## 范围

- 菜单、快捷键、命令栏和标签页按钮统一调用窗口级路由函数。
- 复用现有 QML 抽屉：批量导出、多标签导出、项目预设、画布预设、绑定和尺寸匹配。
- 新增 QML 对话框：修改画布尺寸、重命名标签页。
- 将画布调整模式迁移到 `WorkspaceViewModel.resizeCanvas()`。
- `LegacyFeatureBridge` 只保留复制、粘贴和全选等非弹窗兼容能力。

## 验收标准

- `Main.qml` 中不存在 `legacyTools.open*` 调用。
- `legacy_feature_bridge.py` 不导入 `QtWidgets` 或 `app.ui.*`。
- 所有业务弹窗使用 `AppDialog` / `AppDrawer`、`Theme` 与统一图标。
- 菜单、快捷键和工具栏打开相同的 QML 界面。
- 画布尺寸调整的比例缩放、居中保留、左上保留行为可回归测试。
- QML 工作台可在 1180 x 720 和高 DPI 环境正常渲染。
