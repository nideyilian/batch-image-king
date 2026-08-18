# .cmp 格式安全路线

## 当前策略

`.cmp` 项目和预设文件当前仍使用 pickle，以保持历史项目兼容。所有读取入口统一经过
`app.utils.trusted_pickle.load_trusted_pickle()`，内部使用受限 Unpickler：

- 只允许纯数据/容器类型的 `builtins`（`dict`/`list`/`tuple`/`str`/`int`/`float`/`bool` 等）。
- 允许少量安全标准库模块（`enum`、`collections`、`datetime`、`copyreg`）。
- 允许应用自身命名空间 `app.*`（图层/文档数据如 `ShapeType` 枚举）。
- `os`、`subprocess`、`posix`、`builtins.eval`/`exec`/`__import__`/`getattr`/`open` 等
  经典 RCE 载荷一律抛 `pickle.UnpicklingError` 并拒绝加载（2026-08 落地）。

用户仍只应打开来自本人或可信来源的 `.cmp` 文件；受限反序列化大幅收窄了攻击面，
但 pickle 本身仍不是安全的外部交换格式。

## 中期路线

为 `.cmp` 增加版本化 schema：

- 文档元数据、画布、图层属性使用受控字典结构。
- 图片、字体、预设资源以路径或资源清单引用。
- 加载时先验证 `version`、必需字段、图层类型和字段类型。
- 不符合 schema 的文件进入用户可见错误分支，不进入渲染/导出流程。

## 长期路线

迁移到 JSON 或 MessagePack 保存结构化数据，二进制资源独立存储或引用。保留旧 pickle
导入器作为迁移工具，导入后立即保存为新格式。
