"""开发侧代码备份工具。

在修改代码前运行本脚本,将当前源码完整复制到 ``_dev_backup/<时间戳>/``,
防止修改出错无法回退。保留最近 ``MAX_KEEP`` 份备份,更早的自动清理。

用法(在项目根目录)::

    python tools/backup_code.py
    python tools/backup_code.py --note "修复答题卡跳转"

约定:每次修改代码前先运行本脚本(或直接复制将被修改的文件到
``_dev_backup/``),修改后同步更新 README.md 并在 CHANGELOG.md 记录。
"""

from __future__ import annotations

import argparse
import datetime
import glob
import os
import shutil
import sys

#: 备份根目录。
BACKUP_ROOT = "_dev_backup"

#: 最多保留的备份份数。
MAX_KEEP = 10

#: 需要备份的路径(相对项目根)。
TARGETS = [
    "main.py",
    "quizforge",
    "tests",
    "tools",
    "docs",
    "README.md",
    "CHANGELOG.md",
    "TODO.md",
    "requirements.txt",
    "pyproject.toml",
    "start.bat",
    "start.ps1",
    "start.sh",
]


def main() -> int:
    """执行备份。"""
    parser = argparse.ArgumentParser(description="开发侧代码备份")
    parser.add_argument("--note", default="", help="本次备份说明(写入目录名)")
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    note = re_safe(args.note)
    dir_name = f"{timestamp}{'_' + note if note else ''}"
    target_dir = os.path.join(root, BACKUP_ROOT, dir_name)
    os.makedirs(target_dir, exist_ok=True)

    copied = 0
    for item in TARGETS:
        src = os.path.join(root, item)
        if os.path.isdir(src):
            dst = os.path.join(target_dir, item)
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns(
                                "__pycache__", "*.pyc", ".pytest_cache"))
            copied += 1
        elif os.path.isfile(src):
            shutil.copy2(src, os.path.join(target_dir, item))
            copied += 1
    print(f"已备份 {copied} 项到 {BACKUP_ROOT}/{dir_name}")

    # 清理旧备份,只保留最近 MAX_KEEP 份。
    all_backups = sorted(glob.glob(os.path.join(root, BACKUP_ROOT, "*")))
    for old in all_backups[:-MAX_KEEP]:
        shutil.rmtree(old, ignore_errors=True)
    return 0


def re_safe(text: str) -> str:
    """将说明文本转为安全的目录名字符。"""
    import re
    return re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text).strip("_")


if __name__ == "__main__":
    raise SystemExit(main())
