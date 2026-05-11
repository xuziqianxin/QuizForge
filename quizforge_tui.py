"""QuizForge 终端 UI 主程序。"""
import os
from textual.app import App, ComposeResult
from tui_screens import MainMenuScreen
from bank_manager import BankManager


class QuizForgeTUI(App):
    CSS_PATH = "tui_styles.css"
    TITLE = "QuizForge"
    SUB_TITLE = "题库管理与答题系统"

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen())

    def compose(self) -> ComposeResult:
        yield from []  # 根组件由 Screen 控制


if __name__ == "__main__":
    os.makedirs(BankManager.category_path(""), exist_ok=True)
    QuizForgeTUI().run()