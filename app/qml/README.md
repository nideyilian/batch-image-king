# 批图王 QML 工作台

这是批图王的 Qt Quick/QML 工作台，现已接入真实业务模型和渲染导出链。除 AI 功能外，旧版 QWidget 的生产功能均已通过 QML 原生界面或兼容桥接接入。高频编辑保留在 QML 中，高级图层属性、完整批量导出、多标签高级导出、预设中心、绑定和尺寸匹配等成熟工具复用旧窗口，并与 QML 共享同一批 `Document` 实例。

![QML 工作台预览](preview.png)

## 启动

正式入口默认启动 QML：

```powershell
python main.py
```

旧版界面仍可用于回退：

```powershell
python main.py --classic
```

常用启动参数：

```powershell
# 空白画布或直接打开项目
python -m app.qml.qml_main --blank
python -m app.qml.qml_main --open project.cmp

# 多标签与核心编排
python -m app.qml.qml_main --demo-tabs
python -m app.qml.qml_main --show-multi-select
python -m app.qml.qml_main --show-grouped-layers

# 裁剪、路径、参考线和预设
python -m app.qml.qml_main --show-crop-tools
python -m app.qml.qml_main --show-vector-path
python -m app.qml.qml_main --show-guides
python -m app.qml.qml_main --show-canvas-presets
python -m app.qml.qml_main --show-project-presets

# 数据关系
python -m app.qml.qml_main --show-data-relations
python -m app.qml.qml_main --show-size-match

# 批量导出
python -m app.qml.qml_main --show-batch-advanced
python -m app.qml.qml_main --show-multi-tab-export --demo-tabs
```

## 当前能力

- 文档：多标签、新建、打开、保存、另存、关闭确认、撤销和重做。
- 菜单：文件、编辑、图层、画布、视图均为真实动作，支持旧版常用快捷键和标签页右键操作。
- 画布：常用/自定义尺寸、缩放、标尺、参考线、吸附和用户预设。
- 图层：图片、素材文件夹、文字、异形/矢量图层，以及复制、排序、多选、分组、批量对齐和分布。
- 编辑：拖动、缩放、旋转、适配、五向/自由裁剪、翻转、路径节点和随机变换。
- 外观：不透明度、混合、描边、圆角、颜色/渐变叠加，以及完整文字排版、背景、阴影、发光和局部颜色。
- 数据：项目预设、绑定组组合预览、尺寸匹配和自动遮罩参数。
- 导出：真实预览、单图导出、高级单文档批量导出和多标签队列导出。
- 兼容工具：高级属性、完整预设中心、绑定、尺寸匹配及四种画布调整策略。

AI 接口设置和 AI 生图入口暂不在 QML 工作台显示。

## 截图验收

`--screenshot` 会在界面稳定后保存 PNG 并退出，`--width` 和 `--height` 用于指定窗口尺寸：

```powershell
python -m app.qml.qml_main --show-guides --screenshot qml-workbench.png --width 1600 --height 960
```

其他可视验收参数包括 `--show-new-canvas`、`--show-close-confirm`、`--show-effects --demo-effects`、`--show-random-transform`、`--show-text-typography`、`--show-text-appearance`、`--show-text-effects` 和 `--select-layer`。

画布产品摄影来自 [Unsplash](https://images.unsplash.com/photo-1523275335684-37898b6baf30)，仅作为本地演示素材。
