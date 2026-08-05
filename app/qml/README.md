# 批图王 QML 工作台

这是批图王的下一代 Qt Quick/QML 工作台，现已接入真实业务模型和渲染导出链。当前 QML 入口可完成多标签文档编辑、图层编排、画布与项目预设、绑定与尺寸匹配、单图导出、单文档批量导出和多标签批量导出。现有 QWidget 主程序仍由根目录 `main.py` 启动，QML 入口暂不自动替换它。

![QML 工作台预览](preview.png)

## 启动

在项目根目录运行：

```powershell
python -m app.qml.qml_main
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
- 画布：常用/自定义尺寸、缩放、标尺、参考线、吸附和用户预设。
- 图层：图片、素材文件夹、文字、异形/矢量图层，以及复制、排序、多选、分组、批量对齐和分布。
- 编辑：拖动、缩放、旋转、适配、五向/自由裁剪、翻转、路径节点和随机变换。
- 外观：不透明度、混合、描边、圆角、颜色/渐变叠加，以及完整文字排版、背景、阴影、发光和局部颜色。
- 数据：项目预设、绑定组组合预览、尺寸匹配和自动遮罩参数。
- 导出：真实预览、单图导出、高级单文档批量导出和多标签队列导出。

## 截图验收

`--screenshot` 会在界面稳定后保存 PNG 并退出，`--width` 和 `--height` 用于指定窗口尺寸：

```powershell
python -m app.qml.qml_main --show-guides --screenshot qml-workbench.png --width 1600 --height 960
```

其他可视验收参数包括 `--show-new-canvas`、`--show-close-confirm`、`--show-effects --demo-effects`、`--show-random-transform`、`--show-text-typography`、`--show-text-appearance`、`--show-text-effects` 和 `--select-layer`。

画布产品摄影来自 [Unsplash](https://images.unsplash.com/photo-1523275335684-37898b6baf30)，仅作为本地演示素材。
