"""主菜单屏幕。"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from quizforge.services.bank_service import is_wrongbook_id


class MainScreen(Screen):
    """应用主菜单,提供各功能入口。"""

    BINDINGS = [("q", "quit_app", "退出")]

    def compose(self) -> ComposeResult:
        """构建主菜单界面。"""
        with Vertical():
            yield Static("QuizForge", id="menu_title")
            yield Static("终端题库管理 · 答题练习 · 查题 · 学习通拉取",
                         id="menu_subtitle")
            yield Static("", id="menu_stats")
            with Vertical(id="menu_buttons"):
                yield Button("📚 题库管理", id="btn_bank", variant="primary")
                yield Button("✏️ 开始答题", id="btn_exam", variant="primary")
                yield Button("🔍 查题", id="btn_search", variant="primary")
                yield Button("⚙️ 设置", id="btn_settings", variant="default")
                yield Button("🌐 从学习通导入", id="btn_chaoxing",
                             variant="default")
                yield Button("🚪 退出", id="btn_quit", variant="error")

    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        """挂载时刷新题库统计信息。"""
        self._refresh_stats()

    def on_screen_resume(self, event) -> None:
        """每次回到主菜单时刷新统计(题库可能在别的界面被修改)。"""
        if self.is_mounted:
            self._refresh_stats()

    def _refresh_stats(self) -> None:
        """刷新题库统计信息(分类数与总题数)。

        「XX错题」是虚拟分类(题目来自真实分类),不重复计入总数,
        单独在末尾展示错题总数。
        """
        categories = self.app.bank.list_categories()  # type: ignore[attr-defined]
        real = [c for c in categories if not is_wrongbook_id(c.id)]
        total = sum(c.count for c in real)
        top = " | ".join(
            f"{c.name} {c.count}" for c in real[:5])
        text = f"共 {len(real)} 个分类 · {total} 题"
        if top:
            text += f"  |  {top}"
        wrong_total = sum(c.count for c in categories
                          if is_wrongbook_id(c.id))
        if wrong_total:
            text += f"  |  📕 错题 {wrong_total}"
        self.query_one("#menu_stats", Static).update(text)

    def action_quit_app(self) -> None:
        """快捷键退出。"""
        self.app.exit()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_bank")
    def _open_bank(self) -> None:
        """进入题库管理。"""
        self.app.push_screen("bank")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_exam")
    def _open_exam(self) -> None:
        """进入答题设置(全新实例,避免残留上次抽题配置)。"""
        from quizforge.ui.screens.exam_setup_screen import ExamSetupScreen
        self.app.push_screen(ExamSetupScreen())  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_search")
    def _open_search(self) -> None:
        """进入查题。"""
        self.app.push_screen("search")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_settings")
    def _open_settings(self) -> None:
        """进入设置。"""
        self.app.push_screen("settings")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_chaoxing")
    def _open_chaoxing(self) -> None:
        """进入学习通拉取。"""
        self.app.push_screen("chaoxing")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_quit")
    def _quit(self) -> None:
        """退出应用。"""
        self.app.exit()  # type: ignore[attr-defined]
