#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新清单签名工具（发布者使用，不随客户端分发）。

## 首次准备（只做一次）

    python tools/sign_update_manifest.py --gen-key

会在当前目录生成两个文件：
    update_private_key.txt   私钥（base64，**绝不能提交进仓库**）
    update_public_key.txt    公钥（base64，填进 app/utils/updater_signature.py）

私钥建议立刻移到离线介质（U 盘 / 密码管理器），并删除本地副本。

## 每次发版

    python tools/sign_update_manifest.py update/update.json

工具会：读取清单 → 移除旧 signature → 规范化 → 签名 → 写回 signature 字段。
加 ``--verify`` 可自检签名是否有效（会读公钥文件）：

    python tools/sign_update_manifest.py update/update.json --verify

## 注意

签名的明文规则必须与客户端 ``app/utils/updater_signature.canonical_payload``
完全一致：移除 ``signature`` / ``signature_algorithm`` 两个字段后，
按 ``sort_keys=True, separators=(",",":"), ensure_ascii=False`` 序列化。
改任一侧都要同步另一侧，否则线上清单会被客户端拒绝。
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.utils.updater_signature import (  # noqa: E402
    SIGNATURE_ALGORITHM,
    ManifestSignatureError,
    canonical_payload,
    verify_manifest,
)

PRIVATE_KEY_FILE = "update_private_key.txt"
PUBLIC_KEY_FILE = "update_public_key.txt"


def _require_crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        print(
            "缺少 cryptography 依赖。安装：pip install cryptography",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return Ed25519PrivateKey, serialization


def generate_keypair(output_dir: Path) -> tuple[Path, Path]:
    Ed25519PrivateKey, serialization = _require_crypto()

    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    private_path = output_dir / PRIVATE_KEY_FILE
    public_path = output_dir / PUBLIC_KEY_FILE
    private_path.write_text(base64.b64encode(private_raw).decode(), encoding="utf-8")
    public_path.write_text(base64.b64encode(public_raw).decode(), encoding="utf-8")

    print("已生成密钥：")
    print(f"  私钥: {private_path}   ← 立刻移到离线介质，不要提交")
    print(f"  公钥: {public_path}")
    print()
    print("把公钥填进 app/utils/updater_signature.py：")
    print(f'  UPDATE_PUBLIC_KEY_B64 = "{public_path.read_text(encoding="utf-8").strip()}"')
    return private_path, public_path


def _load_private_key(path: Path, Ed25519PrivateKey):
    if not path.exists():
        raise SystemExit(
            f"找不到私钥文件 {path}。先运行 --gen-key，或把私钥放回当前目录。"
        )
    raw = base64.b64decode(path.read_text(encoding="utf-8").strip(), validate=True)
    if len(raw) != 32:
        raise SystemExit(f"私钥长度应为 32 字节，实际 {len(raw)}")
    return Ed25519PrivateKey.from_private_bytes(raw)


def sign_manifest(manifest_path: Path, private_key_path: Path) -> dict:
    Ed25519PrivateKey, _ = _require_crypto()

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"清单不是合法 JSON：{error}")
    if not isinstance(manifest, dict):
        raise SystemExit("清单必须是 JSON 对象")

    payload = canonical_payload(manifest)
    private_key = _load_private_key(private_key_path, Ed25519PrivateKey)
    signature = base64.b64encode(private_key.sign(payload)).decode()

    manifest["signature"] = signature
    manifest["signature_algorithm"] = SIGNATURE_ALGORITHM

    # 保持与仓库现有清单一致的缩进与中文可读性
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已签名：{manifest_path}")
    print(f"  签名: {signature}")
    return manifest


def verify_file(manifest_path: Path, public_key_path: Path) -> bool:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not public_key_path.exists():
        raise SystemExit(f"找不到公钥文件 {public_key_path}")
    public_b64 = public_key_path.read_text(encoding="utf-8").strip()
    try:
        verify_manifest(manifest, public_b64, allow_unsigned=False)
    except ManifestSignatureError as error:
        print(f"验证失败：{error}", file=sys.stderr)
        return False
    print("验证通过：签名与清单一致")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="更新清单 Ed25519 签名工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("manifest", nargs="?", type=Path, help="要签名的 update.json")
    parser.add_argument("--gen-key", action="store_true", help="生成一对新密钥")
    parser.add_argument("--key", type=Path, default=Path(PRIVATE_KEY_FILE),
                        help=f"私钥文件（默认 {PRIVATE_KEY_FILE}）")
    parser.add_argument("--public-key", type=Path, default=Path(PUBLIC_KEY_FILE),
                        help=f"公钥文件（默认 {PUBLIC_KEY_FILE}）")
    parser.add_argument("--verify", action="store_true", help="签名后自检")
    parser.add_argument("--dry-run", action="store_true", help="只打印签名，不写回文件")
    args = parser.parse_args(argv)

    if args.gen_key:
        generate_keypair(Path.cwd())
        return 0

    if not args.manifest:
        parser.print_help()
        return 1
    if not args.manifest.exists():
        raise SystemExit(f"清单不存在：{args.manifest}")

    if args.dry_run:
        Ed25519PrivateKey, _ = _require_crypto()
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        payload = canonical_payload(manifest)
        private_key = _load_private_key(args.key, Ed25519PrivateKey)
        print(base64.b64encode(private_key.sign(payload)).decode())
        return 0

    manifest = sign_manifest(args.manifest, args.key)

    if args.verify:
        manifest_text = args.manifest.read_text(encoding="utf-8")
        round_trip = json.loads(manifest_text)
        # 自检：写回后再读一遍，确认规范化后仍能验签（防止格式化破坏签名）
        public_b64 = (
            args.public_key.read_text(encoding="utf-8").strip()
            if args.public_key.exists()
            else ""
        )
        if not public_b64:
            print("（跳过自检：没有公钥文件）")
            return 0
        try:
            verify_manifest(round_trip, public_b64, allow_unsigned=False)
        except ManifestSignatureError as error:
            print(f"自检失败：写回后的清单验签不通过 —— {error}", file=sys.stderr)
            print("这通常意味着写回时改变了 JSON 规范形式，请检查写回逻辑。",
                  file=sys.stderr)
            return 1
        print("自检通过：写回后仍可验签")

    if "signature" not in manifest:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
