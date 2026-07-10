from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
import os
import shutil
import subprocess
import sys

def build():
    # 清理旧目录
    print("Cleaning up old build directories...")
    if os.path.exists('dist'):
        try:
            shutil.rmtree('dist')
        except Exception as e:
            print(f"Warning: Could not remove dist directory: {e}")
    if os.path.exists('build'):
        try:
            shutil.rmtree('build')
        except Exception as e:
            print(f"Warning: Could not remove build directory: {e}")
    
    # 确保 app/resources 存在
    if not os.path.exists('app/resources'):
        print("Error: app/resources not found!")
        return

    # PyInstaller 命令参数
    cmd = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--clean',
        '--windowed',
        '--onefile',
        '--name=批图王',
        '--icon=app/resources/app_icon.ico',
        # 添加资源目录
        '--add-data=app/resources;app/resources',
        # 版本信息
        '--version-file=version_info.txt' if os.path.exists('version_info.txt') else None,
        # 隐藏导入
        '--hidden-import=PySide6',
        '--hidden-import=PIL',
        '--hidden-import=pyvips',
        '--hidden-import=app.workers.export_worker',
        '--hidden-import=cv2',
        '--hidden-import=numpy',
        '--hidden-import=scipy',
        # 排除不需要的模块以减小体积（可选）
        # '--exclude-module=matplotlib',
        # 入口文件
        'main.py'
    ]

    # 检查 presets
    if os.path.exists('presets'):
        cmd.insert(6, '--add-data=presets;presets')
    
    # 过滤 None 值
    cmd = [arg for arg in cmd if arg is not None]
    
    print("Executing command:", " ".join(cmd))
    
    try:
        subprocess.check_call(cmd)
        print("\n" + "="*50)
        print("打包成功！")
        print(f"输出目录: {os.path.abspath('dist')}")
        print(f"可执行文件: {os.path.abspath('dist/批图王.exe')}")
        print("="*50)
    except subprocess.CalledProcessError as e:
        print(f"\n打包失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build()
