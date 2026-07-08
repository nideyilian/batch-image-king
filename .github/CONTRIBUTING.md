# 贡献指南

感谢你愿意为批图王贡献代码 / 文档 / 反馈。本文档是给所有贡献者的"快速通道"，
详细的模块说明、目录结构、运行入口都集中在根目录 `AGENTS.md`，
**开始前请先通读 AGENTS.md**。

## 开发环境

- 操作系统：Windows 10 / 11（项目主目标平台）
- Python：3.11+
- 依赖安装：

  ```powershell
  pip install -r requirements.txt
  pip install -r requirements-dev.txt   # 测试用
  ```

## 工作流

1. **先开 Issue**：不论是 Bug 还是 Feature，都先在 Issue 讨论清楚"改什么 / 怎么改"。
2. **建分支**：`codex/<short-topic>` 或 `fix/<short-topic>`。
3. **小步提交**：一次提交只解决一个问题；commit message 写清"为什么"。
4. **本地跑测试**：

   ```powershell
   python -m pytest -m unit          # 跑核心模型/序列化/渲染
   python main.py                    # 冒烟，启动主窗口
   ```

5. **PR 模板**：在 `.github/PULL_REQUEST_TEMPLATE.md` 中有完整自检清单，逐项勾选。
6. **CI 必须绿**：`Tests` workflow 会跑 `pytest` + `main.py import 冒烟`，失败不会被合并。

## 改动原则（来自 AGENTS.md）

- **不要顺手重构无关文件**——一个 PR 解决一个问题。
- **优先复用**：`DocumentSerializer` / `FastRenderer` / `PresetManager` / `LayerSerializer` / 缓存&线程池管理器。
- **不要静默吞异常**：禁止 `except: pass` / `except Exception: pass`；统一加 `logger.debug(...)`。
- **修改渲染要同步检查**：预览、单图导出、批量导出、多标签批量导出。
- **修改图层属性要同步检查**：序列化、历史记录、属性面板、画布刷新、导出快照。
- **性能敏感路径不要加高频 `print`**。

## 测试约定

- 文件命名 `tests/test_*.py`。
- 纯逻辑用 `pytest` 风格（直接函数 + `assert`） + `@pytest.mark.unit`。
- 需要 GUI / Qt / 真实 I/O 的用 `@pytest.mark.integration`。
- 旧文件保留 `unittest.TestCase` 风格，不强行迁移。

## 目录速查

```text
main.py                # 当前主要启动入口
build.py               # PyInstaller 打包
app/
  main_window.py       # 主窗口
  controllers/         # 文档/图层控制器
  models/              # 文档、图层、文字、异形、序列化、历史、导出协调
  ui/                  # Qt 窗口、面板、对话框、画布
  utils/               # 渲染、导出、缓存、线程池、日志、预设、图像质量
  engines/             # 高级合成、Alpha 合成、Photoshop 风格混合
  resources/           # 图标与内置图片资源
docs/code-wiki/        # 8 份模块级说明（架构/运行/模型/UI/渲染/序列化/依赖）
docs/superpowers/      # 历史修复计划
tests/                 # 全部测试入口
```

## 提交 PR 后

- CI 自动跑 pytest + 冒烟，PR 上能看到 ✅/❌。
- 维护者会按模块 owner 来 review；改动跨多个模块时建议在 PR 描述里列出模块清单。
- 合并后 commit message 会被 squash，请保证 PR 标题就是最终提交说明。
