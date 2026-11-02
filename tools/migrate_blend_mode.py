"""把历史 .cmp / 预设文件里的 blend_mode 统一归一为 int。

背景
----
早期版本把 ``blend_mode`` 存成中文名（如「正常」「正片叠底」），后来改为
0-15 的 int。读取侧已在 ``LayerPropertyManager._validate_and_convert_type``
做了兼容（``blend_mode_to_int``），所以老文件能正常打开。

但存量文件里的值仍是混合格式：同一个 JSON/pickle 里既有 int 又有中文。
这会让下游任何「直接读字典」的代码（统计脚本、导出分析、第三方工具）
各自处理一遍，容易漏。本脚本把存量一次洗净。

安全约束
--------
- **默认 dry-run**，只报告不改文件。加 ``--apply`` 才真正写入。
- 写入前把原文件复制到 ``<原文件名>.bak-<时间戳>``。
- 只动 ``blend_mode`` 这一个键，其余内容原样保留（pickle 重新 dump，
  但字典结构与对象引用关系不变）。
- 已经是 int 且合法的值不动。

用法
----
    python -m tools.migrate_blend_mode                 # 只报告
    python -m tools.migrate_blend_mode --apply         # 实际写入

    # 指定目录（默认用户预设目录）
    python -m tools.migrate_blend_mode --dir "D:/some/presets" --apply
"""

from __future__ import annotations

import argparse
import datetime
import os
import pickle
import shutil
import sys
from pathlib import Path

# 允许以脚本形式直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.blend_modes import BLEND_MODE_NAMES, blend_mode_to_int  # noqa: E402
from app.utils.trusted_pickle import load_trusted_pickle  # noqa: E402

VALID_INTS = set(range(len(BLEND_MODE_NAMES)))


def default_presets_dir() -> Path:
    """用户数据目录下的 presets（与 PresetManager 保持一致）。"""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "批图王" / "presets"
    return Path.home() / ".config" / "批图王" / "presets"


def _is_normalized(value) -> bool:
    """int 且在 0-15 范围内才算已归一。"""
    return isinstance(value, int) and not isinstance(value, bool) and value in VALID_INTS


def walk_documents(payload):
    """遍历预设/文档数据里的所有图层 dict，逐层下钻分组 children。"""
    if isinstance(payload, dict) and isinstance(payload.get("documents"), list):
        containers = payload["documents"]
    elif isinstance(payload, dict):
        containers = [payload]
    else:
        return

    stack = list(containers)
    while stack:
        doc = stack.pop()
        if not isinstance(doc, dict):
            continue
        for layer in doc.get("layers") or []:
            if not isinstance(layer, dict):
                continue
            yield layer
            children = layer.get("children")
            if isinstance(children, list):
                stack.append({"layers": children})


def migrate_payload(payload):
    """就地修正 payload 里的 blend_mode，返回 (修改数, 变更明细)。"""
    changes = []
    for layer in walk_documents(payload):
        if "blend_mode" not in layer:
            continue
        raw = layer["blend_mode"]
        if _is_normalized(raw):
            continue
        normalized = blend_mode_to_int(raw)
        layer["blend_mode"] = normalized
        changes.append((layer.get("name") or "<未命名>", repr(raw), normalized))
    return len(changes), changes


def process_file(path: Path, *, apply: bool) -> tuple[int, list]:
    """处理单个文件，返回 (修改数, 明细)。"""
    with open(path, "rb") as handle:
        payload = load_trusted_pickle(handle, str(path))

    count, changes = migrate_payload(payload)
    if count == 0 or not apply:
        return count, changes

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak-{stamp}")
    shutil.copy2(path, backup)

    tmp = path.with_suffix(path.suffix + ".migrating")
    with open(tmp, "wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)
    return count, changes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把历史预设里的中文 blend_mode 归一为 int（默认 dry-run）"
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="预设目录（默认 %%APPDATA%%/批图王/presets）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入；不加时只报告将改动什么",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="只打印汇总，不逐条列出图层",
    )
    args = parser.parse_args(argv)

    target = args.dir or default_presets_dir()
    if not target.is_dir():
        print(f"目录不存在：{target}", file=sys.stderr)
        return 2

    files = sorted(target.glob("*.cmp"))
    if not files:
        print(f"{target} 下没有 .cmp 文件")
        return 0

    total_files_changed = 0
    total_layers_changed = 0

    for path in files:
        try:
            count, changes = process_file(path, apply=args.apply)
        except Exception as error:  # noqa: BLE001 - 单个文件失败不影响其余
            print(f"[跳过] {path.name}: {error}", file=sys.stderr)
            continue
        if count == 0:
            continue
        total_files_changed += 1
        total_layers_changed += count
        verb = "已修正" if args.apply else "待修正"
        print(f"{verb} {path.name}: {count} 个图层")
        if not args.quiet:
            for name, raw, new in changes[:8]:
                print(f"    {name}: {raw} -> {new}")
            if len(changes) > 8:
                print(f"    … 其余 {len(changes) - 8} 个")

    mode = "已写入" if args.apply else "dry-run（未改动任何文件）"
    print(
        f"\n汇总：{total_files_changed} 个文件 / {total_layers_changed} 个图层"
        f" —— {mode}"
    )
    if not args.apply and total_layers_changed:
        print("加 --apply 实际写入（会先备份 .bak-<时间戳>）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
