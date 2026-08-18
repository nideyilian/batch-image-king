# 批图王 Code Wiki

这是一套面向维护者、协作者和后续代码代理的项目 Wiki。它描述当前仓库的整体架构、关键模块职责、核心类与函数、依赖关系、运行与打包方式，以及修改高风险模块时的验证重点。

## 阅读入口

| 文档 | 内容 |
| --- | --- |
| [01. 项目概览](code-wiki/01-project-overview.md) | 项目定位、技术栈、目录结构、代码阅读顺序 |
| [02. 整体架构](code-wiki/02-architecture.md) | 分层架构、主数据流、模块依赖图、信号与状态同步 |
| [03. 运行与打包](code-wiki/03-runtime-and-packaging.md) | 启动流程、开发运行、测试现状、PyInstaller 打包 |
| [04. 核心模型](code-wiki/04-core-models.md) | `Document`、图层、文字图层、异形图层、绑定与尺寸匹配 |
| [05. UI 与控制器](code-wiki/05-ui-and-controllers.md) | 主窗口、多标签页、画布、图层面板、属性面板、导出窗口 |
| [06. 渲染与导出](code-wiki/06-rendering-and-export.md) | `FastRenderer`、合成引擎、单图导出、批量导出、多标签导出 |
| [07. 持久化与预设](code-wiki/07-persistence-and-presets.md) | `.cmp`、pickle 序列化、预设目录、缩略图与用户数据 |
| [08. 依赖与维护指南](code-wiki/08-dependencies-and-maintenance.md) | 依赖矩阵、缓存/线程/内存、维护风险点、验证清单 |

## 快速事实

- 主入口：`main.py`
- 主窗口：`app/main_window.py`
- 核心文档模型：`app/models/document.py`
- 当前主要图片图层：`app/models/layer_new.py`
- 文字图层：`app/models/text_layer.py`
- 异形图层：`app/models/shaped_layer_new.py`
- 预览/导出主渲染器：`app/utils/fast_renderer.py`
- 批量导出主链路：`Document.batch_export()` -> `export_batch_with_precomputation_v2()`
- 项目/预设格式：`.cmp`，底层是 pickle 二进制，不是 JSON
- 推荐开发运行：`python main.py`
- 推荐打包：`python build.py`

## 关键维护提醒

- 仓库存在新旧模块并存：例如 `layer.py` 与 `layer_new.py`，`DocumentRenderer` 与 `FastRenderer`，修改时要确认真实调用链。
- 渲染相关改动必须同时考虑预览、单图导出、批量导出和多标签批量导出。
- 批量导出必须严格区分预览缓存与批量会话缓存，避免随机图/随机文案重复。
- `.cmp` 和根目录 `presets` 都是二进制内容，不要用文本方式读写。
- `build/`、`dist/`、`__pycache__/` 是生成目录，不作为源码维护重点。
