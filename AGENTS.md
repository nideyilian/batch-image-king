# AGENTS.md

## 项目概览

本项目是一个 Windows 桌面端图像批量合成与批量导出工具，应用名称主要使用「批图王」，部分旧代码和窗口标题仍使用「图像批量合成工具」或「模块批量出图工具」。

界面只有一套：**QML（Qt Quick）工作台**，入口 `main.py`。经典 Qt Widgets 主界面已于 2026-10-28 下线。

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
- 界面：**QML（Qt Quick）工作台**为主界面；少量 QWidget 弹窗（颜色选择器、新建画布等）
  仍走 Qt Widgets，与 QML 共用同一 `QApplication`。经典 Qt Widgets 主界面已于 2026-10-28 下线。
- 图像处理：Pillow、fontTools、NumPy、OpenCV。
- 性能/监控：psutil，自研智能缓存、线程池、内存管理模块。
- 打包：PyInstaller（单文件 + 目录双模式）。
- 可选导出加速：`app/utils/vips_export_engine.py` 会尝试使用 `pyvips`，不可用时自动回退。

依赖声明在 `requirements.txt`：

- `PySide6>=6.9.0`
- `Pillow>=11.1.0`
- `fonttools>=4.0.0`
- `numpy>=2.2.0`
- `opencv-python>=4.12.0`
- `psutil>=7.0.0`
- `PyInstaller>=6.14.1`

图标是 `app/qml/icons/*.svg`（Lucide，随代码分发），**不依赖第三方图标包**。

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

## 测试

```powershell
# 安装测试依赖（仅首次需要）
pip install -r requirements-dev.txt

# 运行全部测试
python -m pytest

# 只跑单元测试（最快）
python -m pytest -m unit

# 跑单个文件
python -m pytest tests/test_document_core.py -v
```

`requirements-dev.txt` 会自动继承 `requirements.txt`；开发/测试环境安装 dev 文件即可，运行或打包环境只安装 runtime 文件。

测试根目录为 `tests/`，当前 87 个测试文件、约 683 项，全量跑一次约 1 分钟。配置文件 `pytest.ini` + 根目录 `conftest.py` + `tests/__init__.py` 已就绪。

`conftest.py` 提供 **session 级 autouse 的 `qapp` fixture**，测试里不需要自己创建 `QApplication`；
要显式拿到实例时把 `qapp` 写进参数即可。

覆盖范围（按职责分组，不是全部文件）：

- 模型与序列化 — `test_document_core.py`（生命周期/往返/undo-redo）、`test_layer_serialize.py`、
  `test_text_layer_core.py`、`test_text_layer_range_colors.py`
- 渲染 — `test_fast_renderer_smoke.py`、`test_ndops.py`（与 scipy 交叉验证，scipy 缺失时自动跳过）
- 批量导出 — `test_batch_export_counts.py`、`test_batch_export_binding.py`、`test_batch_export_stress.py`、
  `test_export_worker_reliability.py`、`test_export_worker_threshold.py`
- 降级可见性 — `test_degradation_visibility.py`（计数器语义 + 预计算接线 + 界面提示文案）
- QML 工作台 — `test_qml_workbench_smoke.py`、`test_qml_design_system.py`、
  `test_qml_batch_export_view_model.py`、`test_qml_multi_tab_export.py`、以及一批
  `test_qml_*.py` 的交互/像素级回归
- 打包 — `test_packaging_modes.py`（校验 spec 与 `build_excludes.py` 的联动）

新增测试请：

- 用 `pytest` 风格（直接函数 + `assert`），旧文件维持 `unittest.TestCase`。
- 纯逻辑测试加 `@pytest.mark.unit`，需要 GUI / Qt / 真实 I/O 的加 `@pytest.mark.integration`。
- 需要 Qt 就声明 `qapp` 参数，不要自己 `QApplication(...)`，否则会和 autouse fixture 抢实例。

修改渲染、导出、图层序列化相关代码后，至少应跑一次 `python -m pytest`，并验证新建文档、添加图层、保存/加载、预览、导出和批量导出。

## 入口与启动流程

唯一入口是根目录 `main.py`。`app/application.py` 与 `app/main_window.py` 已随经典界面一并删除。

`main.py` 在**导入阶段**先做三件事，顺序不能动：

1. `app.utils.stream_redirector.setup_streams()` —— 必须早于其它业务导入，
   否则控制台编码问题会让后续 import 直接失败。
2. `--export-worker` 分流到 `app.workers.export_worker.main()`：批量导出的独立进程走这条。
3. `--apply-update` 分流到 `app.utils.updater.apply_update()`：自升级的替换进程走这条。

`main()` 的流程：

1. `setup_logging()` —— 日志目录 `~/.config/批图王/logs`（**与用户数据目录 `%APPDATA%\批图王`
   不是同一处**，这是历史遗留的不一致，别按「应该在一起」去改，改了会让老日志找不到）。
2. `install_crash_reporter()` + `begin_crash_session()` —— 崩溃上下文；
   正常退出时由 `mark_clean_exit()` 收尾。
3. `show_dependency_status()` 打印可选依赖（psutil / cv2）状态。
4. 挂 `sys.excepthook`：未捕获异常写日志并弹 `QMessageBox`。
5. `multiprocessing.freeze_support()`。
6. 创建 `QApplication`：优先走 `app/utils/core/startup_optimizer.py`
   （快速依赖检查 → `Image.MAX_IMAGE_PIXELS = None` → 完整依赖检查），
   优化器导入失败则回退到顺序执行同一组检查。
7. `setup_fixed_theme(app)` —— 名字带「经典」但**不能删**：QML 里嵌的 QWidget 弹窗
   （颜色选择器、新建画布等）靠这套 palette/QSS 上色，跳过之后实测标题栏变纯白，
   与 QML 暗色界面割裂。QSS 只作用于 QWidget，不影响 QML 主界面。
8. 设置应用名/版本/组织名，显示 `app/splash_screen.py` 的启动画面。
9. 调 `app.qml.qml_main.main(app=..., on_ready=...)` —— QML 工作台接管窗口创建与事件循环。
10. 事件循环返回后清理资源：智能线程池、高级任务队列、图片缓存、智能渲染缓存、预览渲染缓存。

⚠️ **不要在这里补第二次 `app.exec()`**：`qml_main` 内部已经跑完事件循环，
第二次 exec 会让进程永不退出（实测 `--screenshot` 截图完成后挂住，只能被 timeout 杀掉）。

`--classic` / `--qml` 仍被识别，但只做兼容：`--classic` 打印一行「经典界面已下线」后按 QML 启动，
`--qml` 直接丢弃（与默认行为一致）。

## 主要目录结构

```text
.
├── main.py                    # 唯一入口：应用级基础设施 + 启动 QML 工作台
├── build.py                   # 打包脚本：安装版 onedir + 便携版 onefile + NSIS + 更新清单
├── build_excludes.py          # 打包排除清单，build.py 与 spec 共用同一份
├── 批图王.spec                # PyInstaller 配置，BTK_BUILD_MODE 决定 onedir / onefile
├── updater_tool.py            # 安装版专用的独立更新工具（onefile）
├── requirements.txt           # 运行依赖
├── requirements-dev.txt       # 开发/测试依赖，继承 requirements.txt
├── 打包说明.md / 更新日志.md
├── presets                    # 初始预设文件，pickle 二进制
├── update/                    # update.json 自动更新清单
├── installer/                 # NSIS 安装脚本
├── docs/                      # 设计与审计文档
│   └── design-system-gallery/ # 组件与图标图库页面（含经典界面历史截图）
├── tools/                     # 开发期校验脚本
├── app/
│   ├── version.py             # APP_VERSION —— 版本号唯一来源
│   ├── constants.py
│   ├── splash_screen.py       # 启动画面（已从 app/ui 移出）
│   ├── qml/                   # 主界面，见下方展开
│   ├── controllers/           # document_controller / layer_controller
│   ├── models/                # 文档、图层、文字、异形、序列化、历史、导出协调
│   ├── services/              # render_service / preview_render_service / export_service / render_quality
│   ├── engines/               # 高级合成、Alpha 合成、Photoshop 风格混合、质量引擎
│   ├── workers/               # export_worker.py —— 批量导出的独立进程
│   ├── utils/                 # 渲染、导出、缓存、线程池、日志、预设、更新
│   ├── ui/                    # 仅剩 QWidget 弹窗 + 主题 + 设计令牌，**没有主窗口**
│   └── resources/             # 应用图标与内置资源
├── tests/                     # pytest 测试（87 个文件 / 约 683 项）
├── build/                     # PyInstaller 构建产物，生成目录
└── dist/                      # 打包输出，生成目录
```

`app/qml/` 展开：

```text
app/qml/
├── Main.qml                   # 单文件主界面，约 9000 行；对话框/抽屉多为内联 component
├── qml_main.py                # QML 启动器：建 engine、注册 context property、管理窗口生命周期
├── components/                # 47 个可复用组件（Theme / AppIcon / 各类 Inspector 控件）
├── icons/                     # 102 个 Lucide SVG
├── assets/
├── viewmodels/                # Python 侧 QObject 视图模型
├── preview_image_provider.py  # 预览图 QQuickImageProvider
└── legacy_feature_bridge.py   # 非视觉的控制器兼容桥（剪贴板等）
```

## 核心模块职责

### `app/qml/qml_main.py`

QML 工作台的启动器，负责：

- 解析命令行参数（`--screenshot`、`--width/--height`、`--theme`、`--open`、`--blank` 等，
  以及一批 `--show-*` 调试入口，用于把某个抽屉/对话框直接打开后截图）。
- 建 `QQmlApplicationEngine`、加载 `Main.qml`。
- 把 Python 侧的视图模型注册成 context property，共 11 个：`workspace`、`workspaceSessions`、
  `layerModel`、`batchExport`、`canvasPresets`、`projectPresets`、`bindingManager`、`sizeMatch`、
  `multiTabExport`、`legacyTools`、`updateManager`。QML 直接按这些名字绑定属性。
- 管理窗口尺寸/几何位置的持久化（QSettings），含一次性的旧命名空间迁移。
- 事件循环与退出清理。`main(app=..., on_ready=...)` 接受外部已建好的 `QApplication`，
  `on_ready` 在首屏对象树就绪时回调（`main.py` 用它收启动画面、弹上次崩溃提示）。

独立运行 `python -m app.qml.qml_main` 也能起界面，适合只调 QML 时避开 `main.py` 的整套初始化。

### `app/qml/viewmodels/`

QML 的 Python 侧视图模型，是界面与领域模型的唯一通道：

- `workspace_view_model.py` —— 主工作台 VM（当前文档、画布、选区、预览请求、导出运行态）。
  体量大，按职责拆成 `workspace_vm_*.py` 多个 mixin：
  `document_ops`（新建/打开/保存/标签页）、`edit_ops`（撤销/重做/剪贴板）、
  `layer_ops`（增删/排序/对齐）、`effects`（描边/圆角/混合模式）、`text_setters`、
  `font_catalog`、`preview`、`view`、`shared`。
- `workspace_session_view_model.py` —— 多标签文档会话。
- `layer_list_model.py` —— 图层面板的 `QAbstractListModel`。
- `batch_export_view_model.py` / `multi_tab_export_view_model.py` —— 两种批量导出。
- `binding_manager_view_model.py` / `size_match_view_model.py` —— 图层绑定与尺寸匹配。
- `canvas_preset_view_model.py` / `preset_manager_view_model.py` —— 画布与预设。
- `update_view_model.py` —— 检查更新，桥接 `app/utils/updater.py`。

约定：QML 只读 VM 的 `@Property`，动作走 `@Slot`；VM 内部改状态后必须 emit 对应的
`notify` 信号，否则界面不会刷新。

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

### `app/models/layer_new.py`

图片图层模型的**唯一实现**（旧 `app/models/layer.py` 已删除），类名是 `Layer`，包含：

- 基础位置、尺寸、可见性、不透明度、锁定状态。
- 图片来源：单文件或文件夹。
- 适配模式、裁剪方向、圆角、描边。
- 颜色叠加、渐变叠加、混合模式。
- 克隆/分身。
- 绑定策略。
- 旋转、翻转、比例锁定。
- 随机位置、随机缩放、随机旋转。
- 缓存与脏状态标记。

`document.py` 不再暴露 `Layer` 别名（R8 收敛），而是 `from app.models.layer_new import Layer as NewLayer`。
维护图层类时以 `layer_new.Layer` 为准；`layer_new` 里的 mixin（`layer_attrs_mixin`、
`layer_transform_mixin`、`layer_rendering_mixin`、`layer_serialize_mixin`）按职责拆分，改属性时注意同步。

### `app/models/shaped_layer_new.py`

异形图层（`ShapedLayer`，继承 `Layer`），旧 `app/models/shaped_layer.py` 已删除。
相关属性和通用操作集中在 `app/models/layer_properties.py`，包括 `ShapeType`、属性通知、通用图层操作等。

### `app/models/text_layer.py`

文字图层模型，包含：

- 多行文字与随机文案模式。
- 文字绑定模式：可以把换行拆成候选文案，也可以把整体文本当作一条文案。
- 字体扫描与 `fonts_cache.json` 缓存。
- 字号、字重/斜体、对齐、行距、字距、内边距、自动适配文本框、竖排。
- 渐变文字、描边、背景、超采样渲染。
- 渲染锁，避免预览和批量导出并发时污染临时渲染参数。

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

### `app/services/render_service.py`

渲染的唯一对外边界（旧 `app/models/document_renderer.py` 已删除）。预览与导出一律经
`RenderService` 分发到 `FastRenderer` / `document_render` 底层实现；`document_render`
的 `enable_gpu` 参数已保留为 no-op（OpenGL GPU 集成已移除）。

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

### `app/workers/export_worker.py`

批量导出的**独立子进程**入口（`main.py --export-worker <request.json>`），
由 `app/utils/export_worker_client.py` 拉起。父子进程之间只传 JSON：
请求文件进去，manifest 文件回传进度与结果。

为什么单开进程：导出是长时间、吃内存的操作，放主进程里一崩用户整个工作台就没了。
改这条链路时注意两端契约 —— `export_worker_client.py` 与 `export_worker.py` 的字段名、
状态值必须同步改，只改一边会得到「导出无声卡住」而不是报错。
Windows 下 `os.replace` 可能因文件占用失败，worker 里已有重试封装，不要绕过。

### `app/utils/preset_manager.py`

预设管理器。开发环境会从根目录 `presets` 复制初始预设；运行时用户预设保存在用户数据目录：

- Windows：`%APPDATA%\批图王\presets`
- Linux/macOS：`~/.config/批图王/presets`

预设索引是 JSON：`presets_index.json`。预设内容本身仍是 `.cmp` pickle 文件。

## 渲染与导出数据流

常见数据流：

```text
Main.qml（QML 视图）
  -> app/qml/viewmodels/*（@Property 读取、@Slot 触发）
  -> Document / Controllers
  -> Layer、TextLayer、ShapedLayer
  -> RenderService（FastRenderer / document_render）
  -> UnifiedAlphaCompositor / blend engines
  -> export_image 或 batch_export
  -> 文件写盘
```

批量导出时需要特别小心缓存边界。代码里已经明确区分预览模式和批量模式：预览可以缓存以提升交互性能，批量导出通常要避免复用会导致随机结果重复的画面缓存。

## 文件与数据格式

- `.cmp`：项目/预设文件，pickle 二进制格式。读取一律走 `app/utils/trusted_pickle.py`
  的可信加载（受限反序列化，阻止经典 RCE gadget），不要直接 `pickle.load`。
- `presets`：根目录初始预设文件，也是二进制内容。
- `fonts_cache.json`：字体扫描缓存，在用户数据目录（`app/models/text_layer_font.py`），不在仓库里。
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
- 从 `app/version.py` 读取 `APP_VERSION`（版本号唯一来源），生成 `build/version_info_generated.txt`。
- 走 `批图王.spec` 打包**两次**，模式靠环境变量 `BTK_BUILD_MODE` 切换：
  - `onedir` → `dist/批图王/`，安装版用，启动不需要解压；
  - `onefile` → `dist/批图王.exe`，便携版用，也是更新清单指向的资产。
- 额外构建 `updater_tool.exe`（安装版专用的独立更新工具），放进 `dist/批图王/`。
- 若本机装了 NSIS，编译 `dist/批图王-Setup.exe`。
- 刷新 `update/update.json`（含便携版与安装包的 SHA-256）。

spec 里的关键点：

- 资源和排除逻辑全部收敛在 spec 和 `build_excludes.py` —— PyInstaller **没有**
  `--exclude-binary` 开关，只有先在 `Analysis` 之后过滤 `a.binaries` 才拦得住
  Qt hook 整批收集的大 DLL（`Qt6WebEngineCore.dll` 单个 79.8MB）。
- datas 打包：`presets`、`app/resources`、`app/qml/{Main.qml,components,icons,assets}`。
- hiddenimports 实际是：`PySide6`、`QtQml`、`QtQuick`、`QtQuickControls2`、`QtWidgets`、
  `PIL`、`pyvips`、`app.workers.export_worker`、`cv2`、`numpy`。

也可以直接使用：

```powershell
pyinstaller 批图王.spec
```

不带 `BTK_BUILD_MODE` 时按 `onedir` 构建；要单文件就设 `BTK_BUILD_MODE=onefile`。

### 版本与自动更新

- 版本号唯一来源：`app/version.py` 的 `APP_VERSION`；发版时修改此处即可。
- 更新清单：`update/update.json`，由 `build.py` 生成，客户端通过
  `raw.githubusercontent.com/nideyilian/batch-image-king/main/update/update.json` 检测新版本。
- 更新核心逻辑在 `app/utils/updater.py`（纯 Python，可单测）；QML 桥接在
  `app/qml/viewmodels/update_view_model.py`。
- 自升级：下载 `批图王_new.exe` 到程序目录，以 `--apply-update` 启动临时实例，主进程退出后完成替换并重启。
- 发版流程：改 `app/version.py` → `python build.py` → 创建 GitHub Release 并上传
  `batch-image-king.exe`（对应本地 `dist/批图王.exe`）与 `batch-image-king-setup.exe`
  （对应本地 `dist/批图王-Setup.exe`）→ 将代码（含 `update/update.json`）推送到 `main` 分支。
- ⚠️ GitHub Release 资产名不接受非 ASCII 字符（中文名会被剥离），上传资产必须用上述两个 ASCII 名，
  `build.py` 生成清单时已按此命名。
- 测试可用环境变量覆盖更新源：`BTPW_UPDATE_URL`（可用 `file://` 指向本地 JSON）。

## 维护注意事项

- 工作区应保持干净：调试脚本、截图、临时输出不要留在仓库根目录。
- 不要手动编辑 `build/`、`dist/`、`__pycache__/` 等生成产物。
- 不要把 `.cmp` 或根目录 `presets` 当文本文件处理。
- **经典 Qt Widgets 界面已下线，不要在 `app/ui/` 里添加新的窗口/面板**。
  该目录只剩 QWidget 弹窗（颜色选择器、新建画布、文字图层等）、`dark_theme.py`
  和设计令牌（`design_spec.py` / `design_tokens.py` / `tokens_v2.py`）。
  新界面一律写在 `app/qml/`。
- 修改渲染逻辑时，同时检查预览、单图导出、批量导出和多标签批量导出。
- 修改图层属性时，同步检查序列化/反序列化、历史记录、属性面板、画布刷新和导出快照。
- 修改文字图层时，特别注意字体缓存、自动文本框、竖排、换行绑定和批量导出并发渲染。
- 修改随机/绑定/尺寸匹配逻辑时，优先验证批量导出的去重、组合一致性和性能。
- QML 与 Python 的边界：QML 读 `@Property`、调 `@Slot`；VM 内部改状态后必须 emit 对应
  `notify` 信号，否则界面不刷新。不要从 QML 直接摸 Document 的内部字段。
- 日志与调试输出较多，性能敏感路径中不要增加高频 `print`。
- 主程序退出时会清理线程池、任务队列和各类缓存；新增全局资源时也要接入退出清理。

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

只改 QML 时的快速自检（不用手点，几秒出图）：

```powershell
# 整窗截图
python -m app.qml.qml_main --screenshot out.png --width 1440 --height 920 --theme dark

# 把某个抽屉/对话框直接打开再截
python -m app.qml.qml_main --screenshot out.png --show-batch-export
# 可用的 --show-* 见 qml_main.parse_args()：--show-effects / --show-new-canvas /
# --show-color-picker / --show-multi-tab-export / --show-text-layer-dialog 等
```

## 给后续代理的工作建议

- 先用 `rg` 定位调用链再改代码。经典版已下线，`app/ui/` 只剩 QWidget 弹窗，
  找主界面请去 `app/qml/`，不要再按老路径找 `main_window.py`。
- 改动尽量小而集中，尤其不要顺手重构大文件（`Main.qml` 已近 9000 行，整体重排风险极高）。
- 优先复用已有工具类：`DocumentSerializer`、`FastRenderer`、`PresetManager`、
  `LayerSerializer`、缓存/线程池管理器等。
- 遇到图像效果差异时，先确认是预览管线、导出管线还是文件编码阶段造成的。
- 遇到批量导出重复问题时，优先检查缓存键、随机状态刷新、绑定组合和批量模式缓存禁用逻辑。
- 改 QML 属性绑定时记得对 `--screenshot` 截一张图看实际渲染 —— 纯读代码看不出
  图标重复、文字裁切、间距塌陷这类问题。

## 底层规则

- 每次对话/任务结束前，都要将本轮实际改动保存到本地 git，作为一次可回退备份；只暂存和提交本轮由代理修改的文件，避免把用户已有未提交改动或生成产物误纳入提交。
