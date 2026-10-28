from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_build_generates_onedir_installer_and_onefile_portable_outputs():
    """两种产物的构建顺序与输出目录保持不变。

    实现方式已从「一长串 PyInstaller 命令行参数」收敛到「统一走 spec +
    环境变量传模式」，因为命令行没有 `--exclude-binary` 开关，无法剔除
    Qt hook 整批收集的原生 DLL。这里断言的是同一件事：
    先 onedir 到 dist/，再 onefile 到 dist/，且两者仍由 build.py 驱动。
    """
    source = (REPO_ROOT / "build.py").read_text(encoding="utf-8")

    # 两种模式都要构建，且都能把模式传给 spec
    assert "run_build('onedir'" in source
    assert "run_build(\n            'onefile'" in source
    assert "env['BTK_BUILD_MODE'] = mode" in source
    # 统一入口是 spec，不再散落资源清单到命令行
    assert "批图王.spec" in source
    assert "build' / 'installer'" in source
    assert "build' / 'portable'" in source


@pytest.mark.unit
def test_nsis_installs_the_onedir_tree():
    source = (REPO_ROOT / "installer" / "批图王.nsi").read_text(encoding="utf-8-sig")

    assert 'File /r "..\\dist\\${APP_NAME}\\*"' in source
    assert 'CreateShortcut "$DESKTOP\\${APP_NAME}.lnk" "$INSTDIR\\${APP_EXE}"' in source
    assert 'RMDir /r "$INSTDIR"' in source


@pytest.mark.unit
def test_checked_in_spec_uses_onedir_collect_layout():
    """spec 必须同时支持 onedir（COLLECT）与 onefile，默认 onedir。

    onefile 下 EXE 内嵌 binaries/datas，不能同时 COLLECT；用
    ``exclude_binaries=not ONEFILE`` 表达这一条件。
    """
    source = (REPO_ROOT / "批图王.spec").read_text(encoding="utf-8")

    assert "BTK_BUILD_MODE" in source
    assert 'os.environ.get("BTK_BUILD_MODE", "onedir")' in source
    assert "exclude_binaries=not ONEFILE" in source
    assert "coll = COLLECT(" in source
    assert "a.binaries" in source
    assert "a.datas" in source


@pytest.mark.unit
def test_spec_excludes_unused_binaries():
    """排除清单必须真正接到 spec 上。

    `--exclude-module` 挡不住被 Qt hook 整批收集的原生 DLL，
    因此必须有 `_strip_binaries(a.binaries)` 这一步，否则产物会重新
    把 Qt6WebEngineCore.dll（79.8MB）等塞回来。
    """
    source = (REPO_ROOT / "批图王.spec").read_text(encoding="utf-8")
    excludes_source = (REPO_ROOT / "build_excludes.py").read_text(encoding="utf-8")

    assert "from build_excludes import" in source
    assert "_strip_binaries(a.binaries)" in source
    assert "excludes=dedupe(EXCLUDES)" in source
    # 关键排除项仍在清单里
    assert "Qt6WebEngineCore.dll" in excludes_source
    assert "opengl32sw.dll" in excludes_source
    assert "torch" in excludes_source
