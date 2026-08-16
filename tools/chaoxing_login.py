"""学习通账号密码登录命令行工具。

在 TUI 之外预登录学习通并保存 Cookie,之后打开 QuizForge 即自动恢复
登录态(无需再次扫码)。

用法::

    python tools/chaoxing_login.py 手机号
    python tools/chaoxing_login.py 手机号 密码        # 不推荐明文传参
    python tools/chaoxing_login.py --phone 手机号     # 密码交互式输入

可选参数:
    --data-dir DIR   数据目录(默认 data,需与 main.py 使用的一致)
    --logout         清除已保存的登录态
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

# 允许从项目根目录直接导入 quizforge 包。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quizforge.chaoxing.client import (ChaoxingError, ChaoxingClient,  # noqa: E402
                                       LoginFailedError)
from quizforge.config import ConfigManager  # noqa: E402


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="学习通账号密码登录工具")
    parser.add_argument("phone", nargs="?", help="手机号/学号")
    parser.add_argument("password", nargs="?", default=None,
                        help="密码(建议省略,交互式输入)")
    parser.add_argument("--data-dir", default="data", help="数据目录")
    parser.add_argument("--logout", action="store_true", help="清除登录态")
    args = parser.parse_args()

    config = ConfigManager(args.data_dir)
    client = ChaoxingClient(
        os.path.join(args.data_dir, config.settings.chaoxing_cookie_file))

    if args.logout:
        client.logout()
        print("已清除学习通登录态")
        return 0

    phone = args.phone or input("手机号/学号: ").strip()
    password = args.password or getpass.getpass("密码: ")
    if not phone or not password:
        print("账号和密码不能为空", file=sys.stderr)
        return 1

    try:
        client.login_with_password(phone, password)
    except LoginFailedError as exc:
        print(f"登录失败: {exc}", file=sys.stderr)
        return 1
    except (ChaoxingError, ImportError) as exc:
        print(f"登录异常: {exc}", file=sys.stderr)
        return 1

    try:
        courses = client.get_courses()
    except ChaoxingError as exc:
        print(f"登录成功,但获取课程列表失败: {exc}", file=sys.stderr)
        return 1
    print(f"登录成功!共 {len(courses)} 门课程,登录态已保存到 "
          f"{client.cookie_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
