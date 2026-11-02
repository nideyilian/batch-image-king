"""更新清单签名验证（Ed25519）。

## 为什么需要它

在此之前，更新链路只校验 ``sha256``，而 ``sha256`` 就写在**同一个 JSON 里**：

    {"download_url": "...", "sha256": "abc123..."}

攻击者只要能改清单，就能把 ``download_url`` 指向自己的木马，同时把 ``sha256``
改成木马文件的哈希 —— 校验依然"通过"。这等于自己证明自己，防的只是传输损坏，
防不住投毒。

加了 Ed25519 签名后：

    签名 = sign(私钥, 清单全文去掉 signature 字段)
    验证 = verify(内置公钥, 清单全文去掉 signature 字段, 签名)

私钥只在发布者机器上离线保存，**客户端只内置 32 字节公钥**。即使程序被完整逆向，
攻击者也拿不到私钥，无法伪造能被接受的清单。

## 清单格式

    {
      "version": "1.3.0",
      "download_url": "...",
      "sha256": "...",
      "signature": "base64(64 字节签名)"
    }

签名的明文 = 把 JSON 里的 ``signature`` 字段**移除**后，按规范化 JSON
（``sort_keys=True, separators=(",", ":"), ensure_ascii=False``）重新序列化。
用规范化形式而不是原始字节，是为了让清单可以被格式化/换行/调键序而不破坏签名。

## 降级策略

清单没有 ``signature`` 字段时：默认**拒绝**（fail-closed），因为"忘了签"和
"被剥掉签名"在客户端无法区分。想临时放开用环境变量
``BTPW_UPDATE_ALLOW_UNSIGNED=1``，会在日志里留明确警告。
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

# 发布公钥（Ed25519，32 字节，base64）。
#
# ⚠️ 这把公钥对应一把**离线保管**的私钥，私钥不在仓库里、也不在任何构建产物里。
# 替换公钥意味着"从这一版开始，旧版客户端不再接受新清单签名"——
# 所以要换必须先发一版把新公钥带下去，等覆盖够了再启用。
UPDATE_PUBLIC_KEY_B64 = "REPLACE_WITH_RELEASE_PUBLIC_KEY"

# 签名算法标识，写进清单便于以后换算法时区分
SIGNATURE_ALGORITHM = "ed25519"

# 明文里必须排除的字段（签名本身不能参与被签内容）
SIGNATURE_FIELDS = ("signature", "signature_algorithm")


class ManifestSignatureError(ValueError):
    """清单签名缺失、格式错误或不匹配。"""


def canonical_payload(manifest: Mapping[str, Any]) -> bytes:
    """把清单规范化成待签名字节。

    规则：移除签名字段 → JSON 规范化序列化 → UTF-8 编码。

    用 ``ensure_ascii=False`` 让中文（release_notes 可能含中文）保持原样，
    这样签名对"人改措辞"敏感、但对"换编码"不敏感。两侧必须用同一规则，
    签名工具见 ``tools/sign_update_manifest.py``。
    """
    if not isinstance(manifest, Mapping):
        raise ManifestSignatureError("清单必须是 JSON 对象")

    body = {key: value for key, value in manifest.items() if key not in SIGNATURE_FIELDS}
    try:
        text = json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as error:
        raise ManifestSignatureError(f"清单无法规范化为 JSON：{error}") from error
    return text.encode("utf-8")


def _decode_signature(signature: str) -> bytes:
    """解析 base64 签名，长度必须是 64 字节（Ed25519 固定）。"""
    if not isinstance(signature, str) or not signature.strip():
        raise ManifestSignatureError("签名为空")
    try:
        raw = base64.b64decode(signature.strip(), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ManifestSignatureError(f"签名不是合法 base64：{error}") from error
    if len(raw) != 64:
        raise ManifestSignatureError(f"签名长度应为 64 字节，实际 {len(raw)}")
    return raw


def _decode_public_key(public_key_b64: str) -> bytes:
    try:
        raw = base64.b64decode(public_key_b64.strip(), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ManifestSignatureError(f"公钥不是合法 base64：{error}") from error
    if len(raw) != 32:
        raise ManifestSignatureError(f"公钥长度应为 32 字节，实际 {len(raw)}")
    return raw


def is_public_key_configured(public_key_b64: str = "") -> bool:
    """发布公钥是否已经正确配置（占位符不算）。"""
    value = (public_key_b64 or UPDATE_PUBLIC_KEY_B64 or "").strip()
    if not value or value == "REPLACE_WITH_RELEASE_PUBLIC_KEY":
        return False
    try:
        _decode_public_key(value)
    except ManifestSignatureError:
        return False
    return True


def _allow_unsigned() -> bool:
    return os.environ.get("BTPW_UPDATE_ALLOW_UNSIGNED", "") == "1"


def verify_manifest(
    manifest: Mapping[str, Any],
    public_key_b64: str = "",
    *,
    allow_unsigned: Optional[bool] = None,
) -> None:
    """校验清单签名，不通过就抛 ``ManifestSignatureError``。

    Args:
        manifest: 已解析的清单 dict。
        public_key_b64: 覆盖内置公钥（测试用；生产留空走内置）。
        allow_unsigned: 覆盖"允许未签名"的判定（测试用）。

    Raises:
        ManifestSignatureError: 签名缺失/格式错/不匹配/公钥未配置。
    """
    permitted_unsigned = _allow_unsigned() if allow_unsigned is None else bool(allow_unsigned)

    # ── 过渡期自锁保护（必须最先判断）────────────────────────────────
    # 如果这个客户端**编译时**就没配公钥（仍是占位符），说明它是签名机制
    # 上线之前发出的版本。此时若强制验签，该版本会永远拒绝所有清单 ——
    # 包括将来那个"把公钥带下来"的修复版，等于自锁死、再也升不上去。
    # 而更新功能正是唯一的修复手段。
    #
    # 顺序很关键：必须在"缺签名"检查**之前**。否则老清单（本来就无签名）
    # 会先撞上"缺少签名"被拒，过渡期根本走不到。
    #
    # 只在"调用方也没显式给公钥"时才算过渡期：显式传入说明调用方
    # （测试 / 未来支持公钥热更新的场景）明确要求验证，不能拦在这里。
    if not public_key_b64 and not is_public_key_configured():
        logger.warning(
            "本客户端未内置发布公钥（占位符），处于签名过渡期："
            "本次仅校验 sha256，无法防御清单投毒。请尽快升级到已配置公钥的版本。"
        )
        return

    signature = manifest.get("signature") if isinstance(manifest, Mapping) else None
    algorithm = ""
    if isinstance(manifest, Mapping):
        algorithm = str(manifest.get("signature_algorithm", "") or "").strip().lower()

    if not signature:
        if permitted_unsigned:
            logger.warning(
                "更新清单未签名，已按 BTPW_UPDATE_ALLOW_UNSIGNED=1 放行 —— "
                "此模式下无法防御清单投毒"
            )
            return
        raise ManifestSignatureError(
            "更新清单缺少签名，已拒绝（如需临时放行请设 BTPW_UPDATE_ALLOW_UNSIGNED=1）"
        )

    if algorithm and algorithm != SIGNATURE_ALGORITHM:
        raise ManifestSignatureError(
            f"不支持的签名算法：{algorithm}（仅支持 {SIGNATURE_ALGORITHM}）"
        )

    key_b64 = (public_key_b64 or UPDATE_PUBLIC_KEY_B64 or "").strip()

    if not is_public_key_configured(key_b64):
        # 自己配了公钥（或调用方传入），但这个 key 不合法 —— 不能放行
        if permitted_unsigned:
            logger.warning("发布公钥无效，已按 BTPW_UPDATE_ALLOW_UNSIGNED=1 放行")
            return
        raise ManifestSignatureError("发布公钥格式无效，无法验证清单签名")

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as error:  # pragma: no cover - 打包缺依赖时才会走到
        raise ManifestSignatureError(
            "缺少 cryptography 依赖，无法验证更新签名"
        ) from error

    payload = canonical_payload(manifest)
    signature_bytes = _decode_signature(str(signature))
    public_key = Ed25519PublicKey.from_public_bytes(_decode_public_key(key_b64))

    try:
        public_key.verify(signature_bytes, payload)
    except InvalidSignature as error:
        raise ManifestSignatureError("更新清单签名验证失败：内容可能已被篡改") from error


def describe_signing_requirement() -> str:
    """给发布流程用的一句话提示（写进打包脚本的输出）。"""
    if not is_public_key_configured():
        return (
            "⚠️ 更新清单签名未启用：客户端内置公钥仍是占位符。"
            "请运行 tools/sign_update_manifest.py --gen-key 生成密钥，"
            "把公钥填入 app/utils/updater_signature.py 的 UPDATE_PUBLIC_KEY_B64"
        )
    return "更新清单签名已启用（Ed25519）"
