# 批图王

> Windows 桌面端图像批量合成与批量导出工具 — 多图层 + 随机/绑定素材 + 高质量导出，所见即所得。

批图王是面向"批量出图"工作流的桌面应用：你可以用多图层（图片、文字、矢量）拼出一张模板，
然后用"文件夹图层 + 绑定组合 + 随机"等机制一次性批量生成成百上千张差异化结果，
最终通过统一的渲染管线导出为 PNG / JPG / WebP / TIFF。

旧窗口标题和部分旧代码里还能看到「图像批量合成工具」「模块批量出图工具」，
都是这个项目的历史名称。

---

## ✨ 核心能力

- 🖼 **多图层文档**：图片图层 / 文字图层 / 矢量异形图层，多标签编辑。
- 🎨 **图层效果**：变换、随机变换、复制对齐、混合模式、描边、圆角、颜色叠加、渐变叠加。
- 🔗 **绑定 / 尺寸匹配 / 随机**：素材文件夹随机抽取、文案随机抽行、绑定组一致性组合。
- 📦 **批量导出**：单图导出、单文档批量导出、多标签页批量导出。
- 🎯 **所见即所得**：预览与导出走同一条 `FastRenderer` 管线。
- 🪟 **打包发布**：PyInstaller 单文件打包为 `批图王.exe`，无需 Python 环境。

---

## 🚀 快速开始

### 直接运行（开发者）

需要 Python 3.11+。

```powershell
# 1. 克隆仓库
git clone <repo-url>
cd 批图王极速版20260520

# 2. 安装运行时依赖
pip install -r requirements.txt

# 3. 启动主程序
python main.py
```

### 直接运行（终端用户）

下载发布页的 `批图王.exe`，双击即可，无需任何安装。

### 跑测试

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

### 打包为单文件

```powershell
python build.py
# 产物位于 dist/批图王.exe
```

详细打包参数见 [`打包说明.md`](./打包说明.md)。

---

## 🧱 技术栈

| 类别 | 依赖 | 用途 |
|---|---|---|
| 语言 | Python 3.11 | 主开发语言 |
| GUI | PySide6 ≥ 6.9 | 主窗口 / 画布 / 面板 / 信号槽 |
| 图像处理 | Pillow ≥ 11.1 | 加载、缩放、文字渲染、编码保存 |
| 数值计算 | NumPy ≥ 2.2 | 像素数组、Alpha 合成、混合模式 |
| 科学计算 | SciPy ≥ 1.15 | 部分高级图像算法 |
| 高级图像处理 | OpenCV ≥ 4.12 | 几何、检测、图像质量 |
| 性能/监控 | psutil ≥ 7.0 | 内存保护、资源监控 |
| 打包 | PyInstaller ≥ 6.14 | Windows 单文件发布 |
| 可选加速 | pyvips ≥ 2.2 | 大图编码/写盘加速（不可用时回退 Pillow） |

完整依赖见 [`requirements.txt`](./requirements.txt)，开发依赖见 [`requirements-dev.txt`](./requirements-dev.txt)。

---

## 📂 目录速查

```text
.
├── main.py                       # 当前主要启动入口
├── build.py                      # PyInstaller 打包脚本
├── 批图王.spec                    # PyInstaller 配置
├── requirements.txt              # 运行时依赖
├── requirements-dev.txt          # 测试/开发依赖
├── pytest.ini / conftest.py      # pytest 测试配置
├── presets/                      # 初始预设（pickle 二进制）
├── docs/
│   ├── code-wiki/                # 8 份模块级深度文档
│   ├── plans/                    # 历史修复计划
│   └── superpowers/              # 计划与执行记录
├── tests/                        # 全部测试（pytest + unittest 混用）
└── app/
    ├── main_window.py            # 主窗口、菜单、工具栏、多标签协调
    ├── controllers/              # 文档/图层控制器
    ├── models/                   # 文档、图层、文字、异形、序列化、历史
    ├── ui/                       # Qt 窗口、面板、对话框、画布
    ├── services/                 # 渲染/导出服务门面
    ├── utils/                    # 渲染、导出、缓存、线程池、日志、预设
    ├── engines/                  # 高级合成、Alpha 合成、Photoshop 风格混合
    └── resources/                # 图标与内置图片资源
```

更深入的分层、入口、关键模块职责请阅读 [`AGENTS.md`](./AGENTS.md) 和
[`docs/code-wiki/`](./docs/code-wiki/)。

---

## 🧭 推荐阅读顺序（给贡献者）

1. `main.py` — 启动流程 / 日志 / 依赖检查 / 退出清理
2. `app/main_window.py` — 主界面 / 多标签 / 导出入口
3. `app/models/document.py` — 核心状态 / 图层列表 / 保存加载
4. `app/models/layer_new.py` / `app/models/text_layer.py` / `app/models/shaped_layer_new.py` — 三类核心图层
5. `app/utils/fast_renderer.py` — 预览与导出主渲染路径
6. `app/utils/batch_export_precomputer.py` / `optimized_batch_executor.py` — 批量导出主路径
7. `app/models/binding_manager.py` — 绑定 / 分类 / 随机组合
8. `app/models/document_serializer.py` / `app/utils/preset_manager.py` — 持久化与预设

---

## 🤝 贡献

- 阅读 [`AGENTS.md`](./AGENTS.md) 了解项目维护约定（不要静默吞异常、改动要小而集中、复用现有工具类）。
- 阅读 [`CONTRIBUTING.md`](./.github/CONTRIBUTING.md) 了解开发工作流（Issue → 分支 → 测试 → PR → CI）。
- 提交 PR 前确保 `python -m pytest` 全部通过、`python main.py` 能正常启动。

CI 自动跑 pytest + main.py 冒烟，PR 上能看到 ✅/❌。

---

## 🩹 排错速查

| 症状 | 可能原因 | 解决 |
|---|---|---|
| 启动报 `ImportError: libvips...` | pyvips 不可用 | 正常现象，代码已自动回退 Pillow；如需 pyvips 加速请安装系统 libvips 后 `pip install pyvips` |
| 控制台中文乱码 | Windows GBK 默认编码 | 应用已通过 `app/utils/stream_redirector.py` 重定向流，**不要**自己改 `print` |
| 批量导出某张卡住 | 单图过大或绑定组合爆炸 | 菜单 → 高级 → 调整 `_export_safety_stall_timeout_seconds`（默认 180s） |
| 撤销/重做丢图层 | 旧版本遗留 | 已修复（见 commit `b3af7e6`），升级到最新版本 |
| 找不到预设 | 用户数据目录 | Windows: `%APPDATA%\批图王\presets`；开发模式也会回退读 `presets/` |

更多排错见 [`docs/code-wiki/03-runtime-and-packaging.md`](./docs/code-wiki/03-runtime-and-packaging.md) 与 `批图王/logs/` 下的日志。

---

## 📜 文档索引

- 项目维护与模块职责 → [`AGENTS.md`](./AGENTS.md)
- 贡献工作流 → [`.github/CONTRIBUTING.md`](./.github/CONTRIBUTING.md)
- 打包说明 → [`打包说明.md`](./打包说明.md)
- 更新日志 → [`更新日志.md`](./更新日志.md)
- 模块深度文档 → [`docs/code-wiki/`](./docs/code-wiki/)（8 篇）
- 修复计划归档 → [`docs/plans/`](./docs/plans/) / [`docs/superpowers/`](./docs/superpowers/)

---

## 📄 License

本项目以"批图王"为名称分发；如需二次发布请联系作者。
