"""更新清单签名验证（Ed25519）行为测试（2026-11-02）。

## 要守住的核心保证

改签名前，更新链路只校验清单里的 ``sha256``，而这个值就写在**同一个 JSON** 里：

    {"download_url": "...", "sha256": "abc123..."}

攻击者改清单就能把下载地址指向自己的文件，同时把 sha256 换成新文件的哈希，
校验照样通过 —— 防得住传输损坏，防不住投毒。

本文件要证明的是：**在签名生效后，任何对清单内容的改动都会被拒绝**，
包括最关键的 ``download_url`` 被替换。

## 测试密钥从哪来

现场用 ``Ed25519PrivateKey.generate()`` 生成，不写死任何测试密钥到仓库里
（写死等于公开一把私钥，虽然只是测试用，但会给人"可以随手加"的错觉）。
"""

from __future__ import annotations

import base64
import copy
import json

import pytest

from app.utils.updater_signature import (
    SIGNATURE_ALGORITHM,
    ManifestSignatureError,
    canonical_payload,
    describe_signing_requirement,
    is_public_key_configured,
    verify_manifest,
)

crypto = pytest.importorskip(
    "cryptography", reason="更新签名依赖 cryptography；缺失时跳过而非失败"
)
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)


@pytest.fixture(scope="module")
def keypair():
    """现场生成一对 Ed25519 密钥（不写死到仓库）。"""
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    return private_key, private_raw, public_b64


def _sign(manifest: dict, private_key) -> dict:
    """按与客户端一致的规则签名，返回带签名的新清单。"""
    signed = dict(manifest)
    signature = private_key.sign(canonical_payload(signed))
    signed["signature"] = base64.b64encode(signature).decode()
    signed["signature_algorithm"] = SIGNATURE_ALGORITHM
    return signed


def _base_manifest() -> dict:
    return {
        "version": "1.3.0",
        "release_notes": "修复若干问题\n新增 A、B、C",
        "download_url": "https://example.com/app-1.3.0.exe",
        "installer_url": "https://example.com/app-1.3.0-setup.exe",
        "required": False,
        "published_at": "2026-11-02",
        "sha256": "a" * 64,
        "installer_sha256": "b" * 64,
    }


# ---------------------------------------------------------------------------
# 规范化：签名对"内容"敏感、对"格式"不敏感
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_canonical_payload_excludes_signature_fields():
    """签名本身不能参与被签内容（否则签名自指，永远验不过）。"""
    manifest = {
        "version": "1.0.0",
        "signature": "xxx",
        "signature_algorithm": "ed25519",
    }
    payload = canonical_payload(manifest)
    assert b"signature" not in payload


@pytest.mark.unit
def test_canonical_payload_is_key_order_independent():
    """调换 JSON 键顺序不应改变签名 —— 否则格式化一下清单就废了。"""
    a = {"version": "1.0", "sha256": "abc", "required": True}
    b = {"required": True, "sha256": "abc", "version": "1.0"}
    assert canonical_payload(a) == canonical_payload(b)


@pytest.mark.unit
def test_canonical_payload_keeps_chinese_readable():
    """release_notes 常含中文，必须按 UTF-8 原样参与签名。"""
    payload = canonical_payload({"release_notes": "修复导出问题"})
    assert "修复导出问题".encode("utf-8") in payload


@pytest.mark.unit
def test_canonical_payload_rejects_non_mapping():
    with pytest.raises(ManifestSignatureError):
        canonical_payload(["not", "a", "dict"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 正常签名 / 验证
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_verify_accepts_correctly_signed_manifest(keypair):
    _, _, public_b64 = keypair
    private_key = keypair[0]

    signed = _sign(_base_manifest(), private_key)
    verify_manifest(signed, public_b64, allow_unsigned=False)  # 不抛即通过


@pytest.mark.unit
def test_verify_survives_json_round_trip(keypair):
    """签名后写入磁盘再读回，仍必须验得过（打包脚本会这么干）。"""
    private_key, _, public_b64 = keypair
    signed = _sign(_base_manifest(), private_key)

    reloaded = json.loads(json.dumps(signed, ensure_ascii=False, indent=2))
    verify_manifest(reloaded, public_b64, allow_unsigned=False)


@pytest.mark.unit
def test_verify_survives_key_reordering(keypair):
    """清单键顺序变了（不同 JSON 工具可能重排）不能影响验签。"""
    private_key, _, public_b64 = keypair
    signed = _sign(_base_manifest(), private_key)

    reordered = {key: signed[key] for key in reversed(list(signed))}
    verify_manifest(reordered, public_b64, allow_unsigned=False)


# ---------------------------------------------------------------------------
# 篡改必被拒（核心保证）
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_tampered_download_url_is_rejected(keypair):
    """最关键的一条：把下载地址换成攻击者自己的文件，必须拒绝。

    这正是只有 sha256 时防不住的攻击 —— 攻击者连 sha256 一起改就行了。
    """
    private_key, _, public_b64 = keypair
    signed = _sign(_base_manifest(), private_key)

    tampered = copy.deepcopy(signed)
    tampered["download_url"] = "https://evil.example.com/malware.exe"

    with pytest.raises(ManifestSignatureError):
        verify_manifest(tampered, public_b64, allow_unsigned=False)


@pytest.mark.unit
@pytest.mark.parametrize("field,new_value", [
    ("version", "9.9.9"),
    ("sha256", "f" * 64),
    ("installer_sha256", "e" * 64),
    ("installer_url", "https://evil.example.com/x.exe"),
    ("release_notes", "官方更新，请放心安装"),
    ("required", True),
    ("published_at", "2030-01-01"),
])
def test_tampering_any_field_is_rejected(keypair, field, new_value):
    """逐字段验证：任何字段被改都必须拒绝，不能有漏网的。"""
    private_key, _, public_b64 = keypair
    signed = _sign(_base_manifest(), private_key)

    tampered = copy.deepcopy(signed)
    tampered[field] = new_value

    with pytest.raises(ManifestSignatureError):
        verify_manifest(tampered, public_b64, allow_unsigned=False)


@pytest.mark.unit
def test_adding_extra_field_is_rejected(keypair):
    """往清单里加字段也算篡改（例如塞一个假的 installer_url）。"""
    private_key, _, public_b64 = keypair
    signed = _sign(_base_manifest(), private_key)

    tampered = copy.deepcopy(signed)
    tampered["extra_payload"] = "payload"

    with pytest.raises(ManifestSignatureError):
        verify_manifest(tampered, public_b64, allow_unsigned=False)


@pytest.mark.unit
def test_removing_field_is_rejected(keypair):
    """删字段同样是篡改。"""
    private_key, _, public_b64 = keypair
    signed = _sign(_base_manifest(), private_key)

    tampered = copy.deepcopy(signed)
    tampered.pop("week_field", None)
    tampered.pop("required")

    with pytest.raises(ManifestSignatureError):
        verify_manifest(tampered, public_b64, allow_unsigned=False)


@pytest.mark.unit
def test_signature_from_another_key_is_rejected(keypair):
    """用另一把私钥签的清单必须拒绝（模拟攻击者自签）。"""
    _, _, public_b64 = keypair
    attacker_key = Ed25519PrivateKey.generate()

    signed_by_attacker = _sign(_base_manifest(), attacker_key)

    with pytest.raises(ManifestSignatureError):
        verify_manifest(signed_by_attacker, public_b64, allow_unsigned=False)


# ---------------------------------------------------------------------------
# 缺失 / 格式错误
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_missing_signature_is_rejected_by_default(keypair, monkeypatch):
    """没签名的清单默认拒绝 —— "忘了签"和"被剥掉签名"在客户端无法区分。"""
    monkeypatch.delenv("BTPW_UPDATE_ALLOW_UNSIGNED", raising=False)
    _, _, public_b64 = keypair

    with pytest.raises(ManifestSignatureError, match="缺少签名"):
        verify_manifest(_base_manifest(), public_b64, allow_unsigned=False)


@pytest.mark.unit
def test_missing_signature_allowed_only_with_explicit_flag(keypair, caplog):
    """显式放开时放行，但必须留下警告日志（不能悄悄放过）。"""
    import logging

    _, _, public_b64 = keypair
    with caplog.at_level(logging.WARNING):
        verify_manifest(_base_manifest(), public_b64, allow_unsigned=True)

    assert any("未签名" in record.message for record in caplog.records), caplog.text


@pytest.mark.unit
@pytest.mark.parametrize("bad_signature", [
    "not-base64!!!",
    base64.b64encode(b"too-short").decode(),
    base64.b64encode(b"\x00" * 63).decode(),
    base64.b64encode(b"\x00" * 65).decode(),
])
def test_malformed_signatures_are_rejected(keypair, bad_signature):
    """签名格式不对要明确报错，不能静默当成"验证通过"。"""
    private_key, _, public_b64 = keypair
    signed = _sign(_base_manifest(), private_key)
    signed["signature"] = bad_signature

    with pytest.raises(ManifestSignatureError):
        verify_manifest(signed, public_b64, allow_unsigned=False)


@pytest.mark.unit
def test_unsupported_algorithm_is_rejected(keypair):
    """清单声明了不认识的算法时要拒绝，而不是当没看见。"""
    private_key, _, public_b64 = keypair
    signed = _sign(_base_manifest(), private_key)
    signed["signature_algorithm"] = "rsa-pkcs1v15"

    with pytest.raises(ManifestSignatureError, match="不支持"):
        verify_manifest(signed, public_b64, allow_unsigned=False)


# ---------------------------------------------------------------------------
# 公钥配置
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_placeholder_public_key_counts_as_not_configured():
    """源码里的占位符必须被识别为"未配置"，否则签名形同虚设。"""
    assert is_public_key_configured("REPLACE_WITH_RELEASE_PUBLIC_KEY") is False
    assert is_public_key_configured("") is False
    assert is_public_key_configured("not-base64!!!") is False
    assert is_public_key_configured(base64.b64encode(b"\x00" * 31).decode()) is False


@pytest.mark.unit
def test_placeholder_key_is_never_treated_as_configured():
    """明确断言占位符的判定结果，防止"只改一处、另一处仍放行"。

    这条是补漏：原先只在 verify_manifest 里校验公钥，若有人把
    is_public_key_configured 的占位符判断去掉，其它测试仍会全绿，
    但发布流程会误以为"签名已启用"。
    """
    for placeholder in (
        "REPLACE_WITH_RELEASE_PUBLIC_KEY",
        "  REPLACE_WITH_RELEASE_PUBLIC_KEY  ",
        "",
        "   ",
    ):
        assert is_public_key_configured(placeholder) is False, placeholder


@pytest.mark.unit
def test_valid_public_key_counts_as_configured(keypair):
    _, _, public_b64 = keypair
    assert is_public_key_configured(public_b64) is True


@pytest.mark.unit
def test_unconfigured_key_blocks_verification(keypair):
    """公钥没配好时不能放行 —— 否则"签名从未生效"会被误认为安全。"""
    private_key = keypair[0]
    signed = _sign(_base_manifest(), private_key)

    with pytest.raises(ManifestSignatureError, match="公钥"):
        verify_manifest(signed, "REPLACE_WITH_RELEASE_PUBLIC_KEY", allow_unsigned=False)


@pytest.mark.unit
def test_describe_signing_requirement_warns_when_unconfigured():
    """发布流程要能感知"签名未启用"，避免发出去的包验不了签。"""
    text = describe_signing_requirement()
    if is_public_key_configured():
        assert "已启用" in text
    else:
        assert "未启用" in text and "sign_update_manifest" in text


# ---------------------------------------------------------------------------
# 过渡期自锁保护（很重要，别删）
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_placeholder_build_does_not_lock_itself_out(monkeypatch, caplog):
    """公钥仍是占位符的版本必须能继续更新，否则会自锁死。

    场景推演：如果先发一个公钥是占位符的版本 A，A 强制验签 → A 拒绝所有清单
    → A 永远升不到"带公钥的版本 B"。而更新功能正是唯一的修复手段。

    所以过渡期内退回"仅校验 sha256"，只打警告。这条测试守的就是这个退路：
    一旦有人"为了安全"把过渡期分支删掉，这里会立刻失败。
    """
    import logging

    from app.utils import updater_signature as module

    monkeypatch.setattr(module, "UPDATE_PUBLIC_KEY_B64", "REPLACE_WITH_RELEASE_PUBLIC_KEY")
    monkeypatch.delenv("BTPW_UPDATE_ALLOW_UNSIGNED", raising=False)

    # 不传 public_key_b64，模拟真实客户端调用
    manifest = _base_manifest()
    manifest["signature"] = base64.b64encode(b"x" * 64).decode()

    with caplog.at_level(logging.WARNING):
        module.verify_manifest(manifest)  # 不应抛异常

    assert any("过渡期" in record.message for record in caplog.records), caplog.text


@pytest.mark.unit
def test_configured_build_refuses_without_valid_signature(monkeypatch, keypair):
    """一旦配了公钥，就必须强制验签 —— 过渡期逻辑不能变成永久后门。"""
    from app.utils import updater_signature as module

    _, _, public_b64 = keypair
    monkeypatch.setattr(module, "UPDATE_PUBLIC_KEY_B64", public_b64)

    manifest = _base_manifest()  # 完全没有 signature 字段

    with pytest.raises(ManifestSignatureError):
        module.verify_manifest(manifest)


# ---------------------------------------------------------------------------
# 与 updater 的接线
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_fetch_update_info_verifies_signature(monkeypatch):
    """接线验证：fetch_update_info 必须真的调用验签，不能只写在文档里。"""
    import app.utils.updater as updater_module

    calls = []

    def fake_verify(payload, *args, **kwargs):
        calls.append(payload)
        raise updater_module.verify_manifest.__globals__["ManifestSignatureError"](
            "测试用：强制验签失败"
        )

    monkeypatch.setattr(updater_module, "verify_manifest", fake_verify)
    monkeypatch.setattr(
        updater_module.url_request, "urlopen",
        lambda *a, **k: __import__("contextlib").nullcontext(
            type("R", (), {"read": lambda self: b'{"version":"1.3.0"}'})()
        ),
    )

    with pytest.raises(Exception):
        updater_module.fetch_update_info("https://example.com/update.json")
    assert calls, "fetch_update_info 没有调用验签 —— 签名等于没接上"
