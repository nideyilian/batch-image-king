"""打包排除清单（build.py 与 批图王.spec 共用）。

这个文件存在的唯一目的：让 PyInstaller 不要把它在打包机器上看到的东西
全部塞进产物。历史产物 429MB 里约 200MB 是 torch / WebEngine / ffmpeg /
pandas / Pythonwin 等本程序从未 import 的模块（详见 .workbuddy/memory
2026-10-27 诊断记录）。

规则：只排除「确认零引用」的模块。新增排除项前先在仓库里
``grep -rn "import <名字>"`` 确认无引用，否则会在用户机器上炸 ImportError。
"""

import os

# --- 第三方重型库 -------------------------------------------------------
# torch: 仅 app/utils/obe_task_render.py 的 _should_use_gpu_for_task() 里 import，
#        而该函数全仓无调用点，已判定为死代码。
# imageio_ffmpeg / imageio: 零 import，由某个已安装包的依赖被连带扫入。
# pandas / matplotlib / IPython / jupyter: 零 import，打包机环境污染。
# pydantic / pydantic_core: 零 import。
HEAVY_LIBS = [
    "torch",
    "torchvision",
    "torchaudio",
    "imageio_ffmpeg",
    "imageio",
    "pandas",
    "matplotlib",
    "pydantic",
    "pydantic_core",
    "IPython",
    "jupyter",
    "notebook",
    "jupyter_client",
    "jupyter_core",
    "nbformat",
    "nbconvert",
    "sympy",
    "onnx",
    "onnxruntime",
    "tensorflow",
    "transformers",
    "accelerate",
    "triton",
    "numexpr",
    "bottleneck",
]

# --- PySide6 未使用的子模块 --------------------------------------------
# 只保留程序真正 import 的：QtCore / QtGui / QtWidgets / QtQml / QtQuick /
# QtSvg（QML 侧另需 QtQuick.Layouts / QtQuick.Controls / QtQuick.Dialogs，
# 它们由 QtQuick 的 hook 自动收集，不在此列）。
# WebEngine 尤其重要：Qt6WebEngineCore.dll 单文件 195MB（压缩后 78.6MB），
# 而全仓 0 处引用 QWebEngine*。
PYSIDE_UNUSED = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    "PySide6.QtHelp",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtHttpServer",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtTextToSpeech",
    "PySide6.QtAxContainer",
    "PySide6.QtDBus",
    "PySide6.QtPrintSupport",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickTest",
    "PySide6.QtNetworkAuth",
]

# --- 标准库里用不到的重量级模块 ----------------------------------------
# 注意：sqlite3 / unittest / setuptools / distutils 刻意不排除。
#   - sqlite3.dll 只有 0.8MB，收益远小于风险
#   - unittest 是大量第三方库的运行时依赖
#   - setuptools / pkg_resources 可能被 importlib.metadata 间接用到
# 只排除真正确认零引用、且打包机上有装的大件。
STDLIB_UNUSED = [
    "tkinter",
    "turtle",
    "turtledemo",
    "idlelib",
    "lib2to3",
    "pydoc_data",
]

# --- 打包机上装的其他杂项（实拆 429MB 产物里发现的） -------------------
# Pythonwin / pywin / win32ui：来自 pywin32，零 import，2.9MB
MISC_UNUSED = [
    "Pythonwin",
    "pywin",
    "win32ui",
]

EXCLUDES = HEAVY_LIBS + PYSIDE_UNUSED + STDLIB_UNUSED + MISC_UNUSED

# --- 需要按二进制排除的 DLL -------------------------------------------------
# `--exclude-module` 只能挡住 Python 模块的 import，挡不住这些**随相邻 pyd 一并
# 被 hook 收集**的 Qt 原生库。实测 `PySide6.QtWebEngineCore` 已列入 EXCLUDES，
# Qt6WebEngineCore.dll（79.8MB）仍然被打了进去。必须用 `--exclude-binary`。
#
# 每一项都在实拆产物后确认过：程序零引用、且不属于 Qt 基础运行时。
EXCLUDE_BINARIES = [
    # WebEngine 全家族：全仓 0 处引用 QWebEngine*
    "Qt6WebEngineCore.dll",
    "Qt6WebEngineQuick.dll",
    "Qt6WebEngineQuickDelegatesQml.dll",
    "Qt6WebEngineWidgets.dll",
    # 软件 OpenGL 回退实现，7.3MB。Qt 仅在无硬件加速时用它，
    # 本程序有真实 GPU 即可走 原生 OpenGL；保留会稳定多占 7.3MB。
    "opengl32sw.dll",
    # 用不到的 Qt 可选模块
    "Qt6Pdf.dll",
    "Qt6Quick3DRuntimeRender.dll",
    "Qt6Quick3DParticles.dll",
    "Qt6Quick3DUtils.dll",
    "Qt6Quick3DAssetImport.dll",
    "Qt6Quick3DAssetUtils.dll",
    "Qt6Quick3DEffects.dll",
    "Qt6Quick3DHelpers.dll",
    "Qt6Quick3DIblBaker.dll",
    "Qt6Quick3DParticleEffects.dll",
    "Qt6Quick3DRuntimeRender_asm.dll",
    "Qt63DCore.dll",
    "Qt63DRender.dll",
    "Qt63DAnimation.dll",
    "Qt63DInput.dll",
    "Qt63DLogic.dll",
    "Qt63DExtras.dll",
    "Qt6Graphs.dll",
    "Qt6Charts.dll",
    "Qt6DataVisualization.dll",
    "Qt6Multimedia.dll",
    "Qt6MultimediaWidgets.dll",
    "Qt6SpatialAudio.dll",
    "Qt6TextToSpeech.dll",
    "Qt6ShaderTools.dll",
    "Qt6Designer.dll",
    "Qt6UiTools.dll",
    "Qt6Help.dll",
    "Qt6Sql.dll",
    "Qt6Test.dll",
    "Qt6Bluetooth.dll",
    "Qt6Nfc.dll",
    "Qt6Positioning.dll",
    "Qt6Sensors.dll",
    "Qt6SerialPort.dll",
    "Qt6RemoteObjects.dll",
    "Qt6Scxml.dll",
    "Qt6StateMachine.dll",
    "Qt6HttpServer.dll",
    # cv2 的视频 IO 解码器 —— 项目零处使用 VideoCapture/VideoWriter/视频文件。
    # 本机 cv2 目录里堆了 3 个历史版本的 ffmpeg（4100/4110/500），
    # 打包时会被 hook 全部收进去，实占 33.7MB。静态图解码不走它
    # （cv2.imdecode 只处理单帧位图）。
    "opencv_videoio_ffmpeg4100_64.dll",
    "opencv_videoio_ffmpeg4110_64.dll",
    "opencv_videoio_ffmpeg500_64.dll",
]



def _strip_binaries(binaries):
    """剔除用不到的二进制。

    两条规则：
    1. 文件名命中 ``EXCLUDE_BINARIES``；
    2. 路径落在 ``EXCLUDE_DIRS`` 覆盖的 Qt QML 插件目录下（这些目录里全是
       未被 QML 引用的可选模块插件，逐个列文件名不现实）。
    """
    unwanted_names = set(EXCLUDE_BINARIES)
    # 统一成小写 + 正斜杠比较：PyInstaller 在 Windows 上给的 dest 是
    # 反斜杠，且大小写不确定，直接用子串匹配会漏。
    normalized_dirs = [d.replace("\\", "/").lower() for d in EXCLUDE_DIRS]
    kept = []
    removed_bytes = 0
    for entry in binaries:
        # entry 形如 (dest_name, src_path, typecode)
        dest = str(entry[0]).replace("\\", "/")
        basename = dest.rsplit("/", 1)[-1]
        haystack = dest.lower()
        if basename in unwanted_names or any(d in haystack for d in normalized_dirs):
            src = entry[1] if len(entry) > 1 else None
            try:
                if src:
                    removed_bytes += os.path.getsize(src)
            except OSError:
                pass
            continue
        kept.append(entry)
    if removed_bytes:
        print(f"[build_excludes] 剔除无用二进制约 {removed_bytes / 1048576:.1f} MB")
    return kept


# 整个目录都不要的 Qt QML 插件（程序未 import 对应模块）
EXCLUDE_DIRS = [
    "qml/QtQuick/VirtualKeyboard",   # 虚拟键盘，2.9MB，桌面端用不到
    "qml/QtQuick3D",                 # 3D，2.0MB
    "qml/Qt3D",                      # 3D
    "qml/QtCharts",                  # 图表
    "qml/QtGraphs",                  # 图表
    "qml/QtDataVisualization",       # 图表
    "qml/QtMultimedia",              # 音视频
    "qml/QtSpatialAudio",
    "qml/QtTextToSpeech",
    "qml/QtWebEngine",               # WebEngine 残留插件
    "qml/QtWebChannel",
    "qml/QtWebSockets",
    "qml/QtPdf",
    "qml/QtSql",
    "qml/QtTest",
    "qml/QtBluetooth",
    "qml/QtNfc",
    "qml/QtPositioning",
    "qml/QtSensors",
    "qml/QtSerialPort",
    "qml/QtRemoteObjects",
    "qml/QtScxml",
    "qml/QtStateMachine",
    "qml/QtDesigner",
    "qml/QtUiTools",
    "qml/QtHelp",
    "qml/QtQuick3DPhysics",
    "qml/QtQuick/Particles",
    "qml/QtQuick/Timeline",
    "qml/QtQuick/SceneGraph",
    "qml/QtQuick/Scene3D",
]


def dedupe(items):
    """去重且保序（PyInstaller 对重复 exclude 不报错，但清单要可读）。"""
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


if __name__ == "__main__":
    print("# 排除的 Python 模块:")
    for name in dedupe(EXCLUDES):
        print(name)
    print("\n# 排除的二进制:")
    for name in EXCLUDE_BINARIES:
        print(name)
