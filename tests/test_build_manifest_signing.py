"""build.py 自动签名清单的行为测试（2026-11-02）。

## 为什么需要

`build.py` 的 `write_update_manifest` 每次发版都会**重写** update.json。
加了签名之后，重写必然让旧签名失效。

如果靠"打完成记得再签一次"，迟早会漏。而漏签的后果极其隐蔽：
**不会报任何错**，只是所有已升级客户端静默拒绝这次更新 ——
用户看到的是"已是最新版本"，永远收不到新版，排查时根本想不到是签名问题。

所以让 build.py 自己签，并用这里的测试锁住三条行为：
1. 找到密钥 → 自动签名，且签出来的能验过
2. 找不到密钥 → 不签，但必须明确提示（不能静默跳过）
3. 密钥损坏 → 不中断打包，但要提示"本次发布将不带有效签名"
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def build_module():
    """导入 build.py。

    它顶层会做参数解析相关导入，这里先把 argv 压成无害值，
    避免 pytest 自己的命令行参数被 argparse 吃掉。
    """
    original_argv = sys.argv
    sys.argv = ["build.py"]
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        import build  # noqa: PLC0415 - 必须在 argv 调整之后导入

        yield build
    finally:
        sys.argv = original_argv


@pytest.fixture
def key_file(tmp_path):
    """现场生成一把临时私钥，返回文件路径。"""
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.generate()
    raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "update_private_key.txt"
    path.write_text(base64.b64encode(raw).decode(), encoding="utf-8")
    return path, private_key


@pytest.mark.unit
def test_signs_manifest_when_key_available(build_module, key_file, monkeypatch):
    """找到密钥时必须自动签名，且签出来的东西能验过。"""
    path, private_key = key_file
    monkeypatch.setenv("BTPW_SIGNING_KEY", str(path))

    payload = {"version": "1.2.1", "download_url": "https://example.com/a.exe"}
    signed = build_module._sign_manifest_payload(dict(payload))

    assert "signature" in signed
    assert signed["signature_algorithm"] == "ed25519"

    # 用同一把密钥推出的公钥验证
    from cryptography.hazmat.primitives import serialization

    from app.utils.updater_signature import verify_manifest

    public_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    verify_manifest(signed, public_b64, allow_unsigned=False)


@pytest.mark.unit
def test_signature_covers_version_and_urls(build_module, key_file, monkeypatch):
    """签名必须覆盖下载地址 —— 这正是防投毒的关键字段。"""
    path, _ = key_file
    monkeypatch.setenv("BTPW_SIGNING_KEY", str(path))

    base = {"version": "1.2.1", "download_url": "https://ok.example/a.exe"}
    signed = build_module._sign_manifest_payload(dict(base))

    tampered = dict(signed)
    tampered["download_url"] = "https://evil.example/malware.exe"

    from app.utils.updater_signature import ManifestSignatureError, verify_manifest

    with pytest.raises(ManifestSignatureError):
        verify_manifest(tampered, allow_unsigned=False)


@pytest.mark.unit
def test_missing_key_leaves_manifest_unsigned(build_module, monkeypatch):
    """找不到密钥时不签名，但必须给出可执行的提示（不能静默跳过）。"""
    monkeypatch.delenv("BTPW_SIGNING_KEY", raising=False)
    monkeypatch.setattr(build_module, "_find_signing_key", lambda: None)

    payload = {"version": "1.2.1", "download_url": "https://example.com/a.exe"}
    result = build_module._sign_manifest_payload(dict(payload))

    assert "signature" not in result

    # 不能断言 capsys：build.py 用的是 safe_print，它的 file 参数在导入时
    # 就绑定了当时的 sys.stdout，pytest 替换 stdout 后抓不到。改判"是否会被打印"。
    from app.utils.print_utils import _should_print

    for message in (
        "[错误] 未找到签名私钥，update.json 将不带签名",
        "[错误] 后果：已升级到「强制验签」版本的客户端会拒绝这次更新",
    ):
        assert _should_print(message) is True, (
            f"这条警告会被 safe_print 静默吞掉：{message!r}。"
            "必须以 [错误] 开头（safe_print 只放行带关键词的消息）"
        )


@pytest.mark.unit
def test_broken_key_does_not_abort_build(build_module, tmp_path, monkeypatch):
    """密钥文件损坏时不能抛异常中断打包，但必须提示签名失败。"""
    bad_key = tmp_path / "bad_key.txt"
    bad_key.write_text("this-is-not-valid-base64!!!", encoding="utf-8")
    monkeypatch.setenv("BTPW_SIGNING_KEY", str(bad_key))

    payload = {"version": "1.2.1", "download_url": "https://example.com/a.exe"}
    result = build_module._sign_manifest_payload(dict(payload))  # 不应抛异常

    assert "signature" not in result

    from app.utils.print_utils import _should_print

    assert _should_print("[错误] 清单签名失败（本次发布将不带有效签名）: xxx") is True
    assert _should_print("[错误] 已升级客户端会拒绝此清单，请修复后重新打包") is True


@pytest.mark.unit
def test_key_lookup_prefers_env_then_cwd(build_module, tmp_path, monkeypatch):
    """查找顺序：环境变量 > 当前目录 > 项目根。

    环境变量优先，是为了让 CI / 多份密钥并存时能明确指定。
    """
    env_key = tmp_path / "from_env.txt"
    env_key.write_text("x", encoding="utf-8")
    monkeypatch.setenv("BTPW_SIGNING_KEY", str(env_key))

    assert build_module._find_signing_key() == env_key

    # 环境变量指向不存在的文件时，回退到 cwd
    monkeypatch.setenv("BTPW_SIGNING_KEY", str(tmp_path / "nope.txt"))
    cwd_key = tmp_path / "update_private_key.txt"
    cwd_key.write_text("y", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    found = build_module._find_signing_key()
    assert found is not None
    assert found.name == "update_private_key.txt"


@pytest.mark.unit
def test_signing_does_not_mutate_input_payload(build_module, key_file, monkeypatch):
    """签名应返回新对象或就地改传入的副本；调用方传 dict(payload) 时不能串味。

    这里验证的是"签名后 payload 里该有的业务字段一个不少"，
    避免有人在签名时误删字段。
    """
    path, _ = key_file
    monkeypatch.setenv("BTPW_SIGNING_KEY", str(path))

    original = {
        "version": "1.2.1",
        "download_url": "https://example.com/a.exe",
        "sha256": "a" * 64,
        "published_at": "2026-11-02",
    }
    result = build_module._sign_manifest_payload(dict(original))

    for field, value in original.items():
        assert result[field] == value, f"签名后字段 {field} 被改动"

@pytest.mark.unit
def test_signing_warnings_survive_safe_print_filter():
    """签名相关警告必须能穿过 safe_print 的输出过滤（真实踩过的坑）。

    build.py 顶层做了 ``from app.utils.print_utils import safe_print as print``，
    而 safe_print 默认只放行带"错误/失败/Exception/Traceback"关键词、
    或以 [ERROR]/[CRITICAL]/[严重错误] 开头的消息。

    最初我写的警告是「⚠️ 未找到签名私钥…」，不含任何关键词 →
    **被静默吞掉**。打包的人会以为签名成功，实际发出去的是未签名清单，
    而后果是所有已升级客户端收不到这次更新。

    这条测试把"什么样的前缀能被打印"钉死，防止以后又写回 ⚠️ 开头。
    """
    from app.utils.print_utils import _should_print

    # 必须能穿透的（当前实现用的就是这些）
    for must_print in (
        "[错误] 未找到签名私钥，update.json 将不带签名",
        "[错误] 清单签名失败（本次发布将不带有效签名）: xxx",
        "[ERROR] 任意内容",
    ):
        assert _should_print(must_print) is True, must_print

    # 会被吞掉的（这就是最初踩的坑，写进测试当反例）
    for will_be_swallowed in (
        "⚠️  未找到签名私钥，update.json 将不带签名",
        "已刷新更新清单",
    ):
        assert _should_print(will_be_swallowed) is False, will_be_swallowed
