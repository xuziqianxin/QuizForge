"""一键打包 QuizForge 为 Windows exe(PyInstaller)。

用法(项目根目录)::

    python tools/build_exe.py

产物:``dist/QuizForge.exe``(单文件,约 37 MB)。

说明:
    * 依赖 ``pyinstaller``(``pip install pyinstaller``);
    * Textual 的 CSS/资源内嵌在 Python 模块中,无需额外收集;
    * ``data/`` 目录运行时在 exe 所在目录自动生成,不打包;
    * 打包后双击或在终端运行 ``QuizForge.exe`` 即可。
"""

from __future__ import annotations

import os
import subprocess
import sys

#: 项目根目录(脚本位于 tools/ 下)。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 应用显示名(与 pyproject.toml 的 version 保持一致)。
APP_NAME = "QuizForge"


def main() -> int:
    """执行 PyInstaller 打包。"""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",          # 单文件
        "--console",          # 终端应用
        "--name", APP_NAME,
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", os.path.join(ROOT, "build"),
        # Textual 需要完整收集(含动态导入的组件)。
        "--collect-all", "textual",
        "--collect-all", "rich",
        os.path.join(ROOT, "main.py"),
    ]
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("[错误] 打包失败,请查看上方 PyInstaller 输出。")
        return result.returncode
    exe_path = os.path.join(ROOT, "dist", f"{APP_NAME}.exe")
    if os.path.isfile(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"[完成] {exe_path} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
