# 批量导出 Worker 200 张阈值设计

## 目标

批量导出达到 200 张时，统一使用一次性独立 worker；200 张以下保持现有内部导出流程。worker 内部的线程数、预加载、画质、缓存和内存策略全部不变，因此不降低正常渲染吞吐量。

## 行为

- `count < 200`：按现有条件执行；不会仅因数量启用 worker。
- `count >= 200`：启用独立 worker。
- 旧项目中已保存的 `export_worker_min_count=500` 自动收紧到 200。
- 如果未来配置了比 200 更低的阈值，保留更低值。
- `export_external_worker_enabled=False` 和 `BTPW_DISABLE_EXPORT_WORKER=1` 继续优先禁用。
- `BTPW_FORCE_EXPORT_WORKER=1` 继续优先强制启用。
- worker 子进程通过 `BTPW_EXPORT_WORKER_CHILD=1` 继续禁止递归启动 worker。

## 修改范围

- `app/models/document.py`：新文档默认阈值由 500 改为 200。
- `app/utils/export_worker_client.py`：读取旧配置后，将有效阈值限制为不高于 200。
- 新增针对阈值、旧配置和环境变量优先级的单元测试。

## 完成标准

- 199 张、少量图层时不启用 worker。
- 200 张时启用 worker。
- 旧配置 500 在 200 张时仍启用 worker。
- 显式禁用和子进程保护仍然有效。
- 现有 worker、批量导出测试和 Python 编译检查通过。
