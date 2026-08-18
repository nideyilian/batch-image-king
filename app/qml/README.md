# 批图王 QML 工作台

这是批图王的 Qt Quick/QML 工作台，现已接入真实业务模型和渲染导出链。除 AI 功能外，旧版 QWidget 的生产功能均已通过 QML 原生界面或兼容桥接接入。所有单图层属性都在右侧 QML 检查器中直接编辑；完整批量导出、多标签高级导出、预设中心、绑定和尺寸匹配等独立工作流复用旧窗口，并与 QML 共享同一批 `Document` 实例。

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
# 默认空白画布、显式演示或直接打开项目
python -m app.qml.qml_main
python -m app.qml.qml_main --demo
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

- 文档：多标签、新建、打开、保存、另存、关闭确认、撤销和重做；相同路径允许重复打开，关闭最后标签不会擅自新建文档。
- 菜单：文件、编辑、图层、画布、视图均为真实动作，`Ctrl+D` 复制标签页、`Ctrl+L` 新建空图层。
- 画布：实际倍率 `10%-1000%`、100% 重置、平移、标尺、参考线、吸附和用户预设。
- 图层：空图片图层可在创建后独立切换单图/文件夹模式；文字和异形使用完整旧版创建参数。
- 编辑：允许负坐标和越出画布，支持八控制点、旋转图层、组/多选缩放、精确命中和穿透选择。
- 外观：不透明度、混合、完整描边线条、统一/四角圆角、颜色/渐变叠加，以及完整文字排版、背景、阴影、发光和局部颜色。
- 高级属性：智能裁剪、图层分身、自定义分身尺寸、镜像、元素铺排及其间距、边距和角度均原生内嵌在右侧检查器。
- 数据：项目预设、绑定组组合预览、尺寸匹配和自动遮罩参数。
- 导出：真实预览、单图导出、高级单文档批量导出和多标签队列导出。
- 兼容工具：新建画布、文字/异形创建、完整预设中心、批量导出、绑定和尺寸匹配仍以旧版业务流程为权威实现。

QML 自研预设、数据关系和导出抽屉只用于显式开发验收参数，不替代主界面的旧版生产流程。

AI 接口设置和 AI 生图入口暂不在 QML 工作台显示。

## 截图验收

`--screenshot` 会在界面稳定后保存 PNG 并退出，`--width` 和 `--height` 用于指定窗口尺寸：

```powershell
python -m app.qml.qml_main --show-guides --screenshot qml-workbench.png --width 1600 --height 960
```

其他可视验收参数包括 `--show-new-canvas`、`--show-close-confirm`、`--show-effects --demo-effects`、`--show-advanced-properties`、`--show-random-transform`、`--show-text-typography`、`--show-text-appearance`、`--show-text-effects` 和 `--select-layer`。

画布产品摄影来自 [Unsplash](https://images.unsplash.com/photo-1523275335684-37898b6baf30)，仅作为本地演示素材。
