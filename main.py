"""QuizForge 程序入口。

用法::

    python main.py            # 正常启动 TUI
    python main.py --selftest # 无头自检(验证模块/存储可用,打包后诊断用)

在支持的终端(如 Windows Terminal / 现代终端模拟器)中运行以获得最佳
显示效果。
"""

from __future__ import annotations

import sys


def _selftest() -> int:
    """无头自检:验证核心模块可导入、存储可读写、UI 可装配,打包后诊断用。"""
    import asyncio
    import os
    import tempfile

    tmp = tempfile.mkdtemp(prefix="quizforge_selftest_")
    from quizforge.models import Option, Question, QuestionType
    from quizforge.services.bank_service import QuestionBankService
    from quizforge.services.exam_service import ExamConfig, ExamService
    from quizforge.storage import CategoryStore

    bank = QuestionBankService(CategoryStore(tmp))
    q = bank.add_question(Question(
        qtype=QuestionType.SINGLE, text="自检题 1+1?",
        options=[Option("A", "2"), Option("B", "3")], answer=["A"]))
    session = ExamService().create_session(
        [q], ExamConfig(question_ids=[q.id]))
    session.record_answer(q.id, ["A"])
    result = ExamService().grade(session, [q])
    storage_ok = bank.count() == 1 and result.auto_score == 1

    # UI 可装配:无头启动应用并渲染主菜单。
    async def _ui_probe() -> bool:
        from quizforge.ui.app import QuizForgeApp
        app = QuizForgeApp(data_dir=os.path.join(tmp, "ui"))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            return len(app.screen.query("#menu_buttons")) > 0

    try:
        ui_ok = asyncio.run(_ui_probe())
    except Exception:
        ui_ok = False

    ok = storage_ok and ui_ok
    print(f"自检{'通过' if ok else '失败'}: "
          f"题库 {bank.count()} 题, 评分 {result.auto_score}/"
          f"{result.auto_total}, UI 渲染 {'正常' if ui_ok else '异常'}")
    return 0 if ok else 1


def main() -> int:
    """启动 QuizForge TUI。

    Returns:
        进程退出码(0 表示正常退出)。
    """
    if "--selftest" in sys.argv:
        return _selftest()

    # Textual 需要真实的 TTY;在非交互环境给出明确提示。
    if not sys.stdout.isatty():
        print("QuizForge 是终端应用,请在交互式终端中运行: python main.py")
        return 1

    from quizforge.ui.app import QuizForgeApp

    QuizForgeApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
