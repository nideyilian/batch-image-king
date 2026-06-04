# 01. 项目概览

## 项目定位

批图王是一个 Windows 桌面端图像批量合成与批量导出工具。它围绕“画布 + 多图层 + 随机/绑定素材 + 高质量导出”组织功能，目标是在预览、单图导出、批量导出之间尽量做到所见即所得。

应用名称主要使用“批图王”。部分旧窗口标题、旧文档和旧代码仍可能出现“图像批量合成工具”或“模块批量出图工具”。

## 核心能力

- 多标签文档编辑。
- 画布创建、缩放、参考线、预设管理。
- 图片图层、文字图层、异形/矢量图层。
- 图层变换、随机变换、复制粘贴、对齐、混合模式、描边、圆角、颜色叠加、渐变叠加。
- 图层绑定、尺寸匹配、批量随机取图、批量随机取文案。
- 单图导出、单文档批量导出、多标签页批量导出。
- 统一预览与导出的高质量渲染管线。
- PyInstaller 单文件打包为 `批图王.exe`。

## 技术栈

| 类别 | 依赖/技术 | 用途 |
| --- | --- | --- |
| 语言 | Python 3 | 主开发语言 |
| GUI | PySide6 | 主窗口、画布、面板、对话框、信号槽 |
| 图像处理 | Pillow | 图像加载、缩放、裁剪、文字渲染、编码保存 |
| 数值计算 | NumPy | 像素数组、Alpha 合成、遮罩与混合模式 |
| 科学计算 | SciPy | 部分高级图像算法 |
| 高级图像处理 | OpenCV | 几何、检测、图像质量相关处理 |
| 性能/监控 | psutil | 内存保护、资源监控 |
| 打包 | PyInstaller | Windows 单文件发布 |

依赖声明位于根目录 `requirements.txt`。

## 目录结构

```text
.
├── main.py                         # 当前主要启动入口
├── app/application.py              # 旧版/备用入口
├── build.py                        # PyInstaller 自动打包脚本
├── 批图王.spec                     # PyInstaller spec
├── requirements.txt                # Python 依赖
├── presets                         # 初始预设，pickle 二进制
├── docs/                           # 项目文档和本 Wiki
├── tests/                          # 当前已有少量 unittest 回归测试
├── app/
│   ├── main_window.py              # 主窗口、多标签页、菜单、工具栏协调
│   ├── controllers/                # 文档/图层控制器
│   ├── models/                     # 文档、图层、历史、序列化、绑定等核心模型
│   ├── ui/                         # Qt 画布、面板、对话框
│   ├── services/                   # 渲染/导出服务门面与质量策略
│   ├── utils/                      # 渲染、批导、缓存、预设、性能工具
│   ├── engines/                    # 高级合成与混合引擎
│   └── resources/                  # 图标与内置资源
├── build/                          # PyInstaller 中间产物，生成目录
└── dist/                           # 打包输出，生成目录
```

## 推荐阅读顺序

1. `main.py`：启动流程、日志、依赖检查、退出清理。
2. `app/main_window.py`：主界面、多标签文档、菜单工具栏、导出入口。
3. `app/models/document.py`：核心状态、图层列表、保存加载、导出入口。
4. `app/models/layer_new.py`、`app/models/text_layer.py`、`app/models/shaped_layer_new.py`：三类核心图层。
5. `app/ui/canvas.py`：预览绘制、交互、异步渲染。
6. `app/utils/fast_renderer.py`：预览和导出主渲染路径。
7. `app/utils/batch_export_precomputer.py`、`app/utils/optimized_batch_executor.py`：批量导出主路径。
8. `app/models/binding_manager.py`：绑定、分类和随机组合一致性。
9. `app/models/document_serializer.py`、`app/utils/preset_manager.py`：持久化和预设。

## 新旧代码并存

项目仍保留大量兼容层：

- `app/models/layer.py` 与 `app/models/layer_new.py` 都存在，当前 `document.py` 中有 `Layer = NewLayer` 的兼容别名。
- `DocumentRenderer` 仍是通用渲染器，但预览和导出更偏向 `FastRenderer`。
- `Document` 中保留旧导出、旧合成、旧历史相关接口，部分 UI 或回退路径仍会调用。

维护时不要只按文件名判断“新旧”，应使用 `rg` 追实际调用链。
