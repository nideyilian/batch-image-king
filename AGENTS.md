# AGENTS.md

## 项目概览

本项目是一个 Windows 桌面端图像批量合成与批量导出工具，应用名称主要使用「批图王」，部分旧代码和窗口标题仍使用「图像批量合成工具」或「模块批量出图工具」。

核心能力包括：

- 多标签文档编辑。
- 画布创建、缩放、参考线、预设管理。
- 图片图层、文字图层、异形/矢量图层。
- 图层变换、随机变换、复制粘贴、对齐、混合模式、描边、圆角、颜色/渐变叠加等效果。
- 图层绑定、尺寸匹配、批量随机取图/取文案。
- 单图导出、单文档批量导出、多标签页批量导出。
- 统一预览与导出的高质量渲染管线，目标是所见即所得。
- PyInstaller 单文件打包为 `批图王.exe`。

## 技术栈

- 语言：Python。
- GUI：PySide6。
- 图像处理：Pillow、NumPy、SciPy、OpenCV。
- 性能/监控：psutil，自研智能缓存、线程池、内存管理模块。
- 打包：PyInstaller。
- 可选导出加速：`app/utils/vips_export_engine.py` 会尝试使用 `pyvips`，不可用时自动回退。

依赖声明在 `requirements.txt`：

- `PySide6>=6.9.0`
- `Pillow>=11.1.0`
- `numpy>=2.2.0`
- `scipy>=1.15.0`
- `opencv-python>=4.12.0`
- `psutil>=7.0.0`
- `PyInstaller>=6.14.1`

## 常用命令

建议在项目根目录执行。

```powershell
# 安装依赖
pip install -r requirements.txt

# 开发运行
python main.py

# 重新打包
python build.py

# 或使用 spec 文件打包
pyinstaller 批图王.spec
```

当前没有发现统一的测试套件或固定测试命令。仓库里曾出现过一些临时测试脚本，但当前根目录文件列表中没有保留正式测试入口。修改渲染、导出、图层序列化相关代码后，至少应手动运行 `python main.py`，并验证新建文档、添加图层、保存/加载、预览、导出和批量导出。

## 入口与启动流程

主要入口是根目录 `main.py`。

启动流程大致为：

1. 先调用 `app.utils.stream_redirector.setup_streams()`，避免控制台编码或流对象异常影响后续导入。
2. 初始化日志，日志目录默认位于用户配置目录下的 `批图王/logs`。
3. 快速检查关键依赖：Pillow、NumPy。
4. 延迟或完整检查混合模式、图像质量等功能。
5. 创建 `QApplication`，应用固定暗色主题 `CursorDarkTheme`。
6. 创建并显示 `app.main_window.MainWindow`。
7. 程序退出时关闭智能线程池、高级图像缓存和任务队列。

`app/application.py` 也是一个入口样式文件，但更像旧版/备用入口；维护时优先以根目录 `main.py` 为准。

## 主要目录结构

```text
.
├── main.py                    # 当前主要启动入口
├── build.py                   # PyInstaller 自动打包脚本
├── 批图王.spec                # PyInstaller 配置
├── requirements.txt           # Python 依赖
├── 打包说明.md                # 打包说明与发布备注
├── 更新日志.md                # 项目更新说明
├── presets                    # 初始预设文件，内容为 pickle 二进制
├── app/
│   ├── main_window.py         # 主窗口、菜单、工具栏、多标签文档协调
│   ├── application.py         # 旧版/备用应用入口
│   ├── constants.py           # 常量
│   ├── controllers/           # 文档与图层控制器
│   ├── models/                # 文档、图层、文字、异形、序列化、历史、导出协调等模型
│   ├── ui/                    # 各类 Qt 窗口、面板、对话框和画布
│   ├── utils/                 # 渲染、导出、缓存、线程池、日志、预设、图像质量等工具
│   ├── engines/               # 高级合成、Alpha 合成、Photoshop 风格混合、质量引擎
│   └── resources/             # 图标与内置图片资源
├── build/                     # PyInstaller 构建产物，应视为生成目录
├── dist/                      # 打包输出目录，应视为生成目录
├── benchmark_outputs/         # 基准测试输出
└── benchmark_probe/           # 基准测试探针/数据
```

## 核心模块职责

### `app/main_window.py`

`MainWindow` 是应用层协调中心，负责：

- 创建主界面、菜单、工具栏、状态栏和停靠面板。
- 管理多标签文档。
- 创建并持有 `DocumentManager`、`DocumentController`、`LayerController`。
- 调用新建、打开、保存、另存为、导出、批量导出、多标签页导出、预设管理等流程。
- 为每个文档隔离批量导出窗口和多标签导出窗口，避免跨文档共享状态。

### `app/models/document.py`

`Document` 是核心文档模型，包含：

- 画布尺寸。
- 图层列表与当前选中图层。
- 文件路径与修改状态。
- 导出设置。
- 视图设置。
- 历史记录、序列化、渲染、批量导出协调器。
- 绑定管理器和图层尺寸匹配管理器。

`Document` 仍保留大量兼容旧接口的代码。新增功能时要注意不要只改新拆分模块而遗漏旧调用路径。

### `app/models/layer.py` 与 `app/models/layer_new.py`

图片图层模型，包含：

- 基础位置、尺寸、可见性、不透明度、锁定状态。
- 图片来源：单文件或文件夹。
- 适配模式、裁剪方向、圆角、描边。
- 颜色叠加、渐变叠加、混合模式。
- 克隆/分身。
- 绑定策略。
- 旋转、翻转、比例锁定。
- 随机位置、随机缩放、随机旋转。
- 缓存与脏状态标记。

`document.py` 中有向后兼容别名：`Layer = NewLayer`。维护时要确认实际被引用的是哪个类。

### `app/models/text_layer.py`

文字图层模型，包含：

- 多行文字与随机文案模式。
- 文字绑定模式：可以把换行拆成候选文案，也可以把整体文本当作一条文案。
- 字体扫描与 `fonts_cache.json` 缓存。
- 字号、字重/斜体、对齐、行距、字距、内边距、自动适配文本框、竖排。
- 渐变文字、描边、背景、超采样渲染。
- 渲染锁，避免预览和批量导出并发时污染临时渲染参数。

### `app/models/shaped_layer.py` 与 `app/models/shaped_layer_new.py`

异形图层，基于普通图层扩展形状能力。相关属性和通用操作集中在 `app/models/layer_properties.py`，包括 `ShapeType`、属性通知、通用图层操作等。

### `app/models/document_serializer.py`

负责文档保存/加载的数据准备和 pickle 序列化。

项目文件和预设主要是 `.cmp`，底层是 pickle 二进制格式，不是 JSON。处理 `.cmp` 时不要用文本方式读写。

序列化会保存：

- 画布尺寸。
- 图层数据。
- 当前选中图层。
- 导出设置。
- 视图设置。
- 图层尺寸匹配配置。
- 绑定组数据。

### `app/models/document_renderer.py`

较通用的文档渲染器，负责将图层合成到画布。普通模式优先使用 `app.utils.unified_alpha_compositor` 的 sRGB Alpha 合成，其他混合模式回退到专业混合器。

注意：更新日志说明当前预览和导出更偏向统一使用 `FastRenderer` 管线；改渲染行为时要同时核对 `DocumentRenderer` 与 `FastRenderer` 的调用关系。

### `app/utils/fast_renderer.py`

高性能渲染核心之一，职责包括：

- 智能缓存。
- 预览模式缓存。
- 批量模式禁用某些缓存，避免随机图重复。
- 图层级 surface 缓存。
- 导出层缓存。
- 交互式增量预览缓存。
- 批量导出会话读盘/处理缓存。
- 与智能内存管理系统集成。

环境变量：

- `BTPW_FAST_RENDERER_DEBUG=1`：开启快速渲染器调试输出。
- `BTPW_BATCH_RENDER_VERBOSE=1`：开启批量渲染高频日志。

### `app/utils/optimized_batch_executor.py`

优化批量导出执行器，负责高性能批量导出、预计算和导出报告。`export_batch_with_precomputation_v2()` 是一个重要外部入口。

批量导出相关修改要重点关注：

- 随机图/随机文案是否每张都正确变化。
- 绑定组合是否保持一致。
- 缓存是否会导致重复输出。
- 失败率、连续失败、内存保护和停滞超时等安全设置是否生效。

### `app/models/batch_export_coordinator.py`

批量导出流程协调器，做参数验证、进度信号、取消标记、时间估算等，不直接承载复杂导出逻辑。

支持格式包括：`png`、`jpg`、`jpeg`、`bmp`、`tiff`、`webp`。

### `app/utils/preset_manager.py`

预设管理器。开发环境会从根目录 `presets` 复制初始预设；运行时用户预设保存在用户数据目录：

- Windows：`%APPDATA%\批图王\presets`
- Linux/macOS：`~/.config/批图王/presets`

预设索引是 JSON：`presets_index.json`。预设内容本身仍是 `.cmp` pickle 文件。

## 渲染与导出数据流

常见数据流：

```text
MainWindow/UI
  -> Document / Controllers
  -> Layer、TextLayer、ShapedLayer
  -> FastRenderer 或 DocumentRenderer
  -> UnifiedAlphaCompositor / blend engines
  -> export_image 或 batch_export
  -> 文件写盘
```

批量导出时需要特别小心缓存边界。代码里已经明确区分预览模式和批量模式：预览可以缓存以提升交互性能，批量导出通常要避免复用会导致随机结果重复的画面缓存。

## 文件与数据格式

- `.cmp`：项目/预设文件，pickle 二进制格式。
- `presets`：根目录初始预设文件，也是二进制内容。
- `fonts_cache.json`：字体扫描缓存。
- `version_info.txt`：PyInstaller 版本信息。
- `app/resources/*`：打包时需要包含的资源。
- `build/`、`dist/`：生成产物，不应作为源码维护重点。

## 打包说明

推荐使用：

```powershell
python build.py
```

`build.py` 会：

- 清理旧 `dist/` 和 `build/`。
- 检查 `app/resources`。
- 使用 PyInstaller 单文件窗口模式打包。
- 程序名为 `批图王`。
- 图标使用 `app/resources/app_icon.ico`。
- 添加 `app/resources` 和 `presets`。
- 添加隐藏导入：PySide6、PIL、cv2、numpy、scipy。
- 如果存在 `version_info.txt`，会传入版本信息。

也可以直接使用：

```powershell
pyinstaller 批图王.spec
```

## 维护注意事项

- 仓库当前有大量未提交或已生成文件，修改前后都要避免误删用户已有改动。
- 不要手动编辑 `build/`、`dist/`、`__pycache__/` 等生成产物。
- 不要把 `.cmp` 或根目录 `presets` 当文本文件处理。
- 修改渲染逻辑时，同时检查预览、单图导出、批量导出和多标签批量导出。
- 修改图层属性时，同步检查序列化/反序列化、历史记录、属性面板、画布刷新和导出快照。
- 修改文字图层时，特别注意字体缓存、自动文本框、竖排、换行绑定和批量导出并发渲染。
- 修改随机/绑定/尺寸匹配逻辑时，优先验证批量导出的去重、组合一致性和性能。
- UI 使用 PySide6 信号槽，更新模型属性后通常需要发出对应 `changed`、`layer_changed`、`layers_changed` 或 UI 刷新信号。
- 日志与调试输出较多，性能敏感路径中不要增加高频 `print`。
- 主程序退出时会清理线程池、图片缓存和任务队列；新增全局资源时也应接入退出清理。

## 建议验证清单

在涉及核心功能变更后，建议按下面顺序手动验证：

1. `python main.py` 能正常启动。
2. 新建画布，添加普通图片图层。
3. 添加文字图层，验证字体、换行、竖排、描边或渐变。
4. 添加异形图层，验证形状参数和旋转/缩放。
5. 保存为 `.cmp`，关闭后重新打开。
6. 单图导出 PNG/JPG。
7. 批量导出多张，确认随机图片/文案没有异常重复。
8. 多标签页批量导出。
9. 打包后运行 `dist/批图王.exe`，确认资源和预设可用。

## 给后续代理的工作建议

- 先用 `rg` 定位调用链，再改代码；这个项目存在新旧模块并存的兼容层。
- 改动尽量小而集中，尤其不要顺手重构大文件。
- 优先复用已有工具类：`DocumentSerializer`、`FastRenderer`、`PresetManager`、`LayerSerializer`、缓存/线程池管理器等。
- 遇到图像效果差异时，先确认是预览管线、导出管线还是文件编码阶段造成的。
- 遇到批量导出重复问题时，优先检查缓存键、随机状态刷新、绑定组合和批量模式缓存禁用逻辑。
