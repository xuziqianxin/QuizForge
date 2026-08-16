"""QuizForge Textual 应用:装配各服务并注册屏幕。"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from textual.app import App
from textual.binding import Binding

from quizforge.chaoxing.client import ChaoxingClient
from quizforge.config import ConfigManager
from quizforge.models import Question
from quizforge.services.bank_service import QuestionBankService
from quizforge.services.exam_service import ExamResult, ExamService, \
    ExamSession
from quizforge.services.import_service import ImportService
from quizforge.storage import CategoryStore, HistoryStore, TemplateStore
from quizforge.ui.cjk_patch import apply_cjk_patch
from quizforge.ui.screens.bank_screen import QuestionBankScreen
from quizforge.ui.screens.chaoxing_screen import ChaoxingScreen
from quizforge.ui.screens.exam_review_screen import ExamReviewScreen
from quizforge.ui.screens.exam_screen import ExamScreen
from quizforge.ui.screens.exam_setup_screen import ExamSetupScreen
from quizforge.ui.screens.history_screen import HistoryScreen
from quizforge.ui.screens.main_screen import MainScreen
from quizforge.ui.screens.search_screen import SearchScreen
from quizforge.ui.screens.settings_screen import SettingsScreen
from quizforge.ui.theme import THEME_CSS

#: 应用 CJK 渲染补丁:修复部分窗口宽度下下拉框中文选项缺字。
#: 必须在任何渲染发生前应用(模块导入时即生效)。
apply_cjk_patch()


class QuizForgeApp(App):
    """QuizForge 主应用。

    持有各服务的共享实例,屏幕通过 ``self.app.xxx`` 访问:
        * bank: 题库服务(增删改查、检索);
        * import_service: JSON 导入导出;
        * exam_service: 答题会话与评分;
        * chaoxing: 学习通客户端;
        * config: 应用配置。
    答题进行中/结束后的会话与结果挂在 ``exam_session`` / ``exam_result``。
    """

    TITLE = "QuizForge"
    SUB_TITLE = "终端题库 · 练习 · 查题 · 学习通拉取"
    CSS = THEME_CSS

    BINDINGS = [
        Binding("ctrl+q", "quit", "退出"),
    ]

    SCREENS = {
        "main": MainScreen,
        "bank": QuestionBankScreen,
        "exam_setup": ExamSetupScreen,
        "exam": ExamScreen,
        "review": ExamReviewScreen,
        "search": SearchScreen,
        "settings": SettingsScreen,
        "history": HistoryScreen,
        "chaoxing": ChaoxingScreen,
    }

    def __init__(self, data_dir: str = "data") -> None:
        """初始化应用与共享服务。

        Args:
            data_dir: 数据目录(存放题库 JSON、配置与学习通 Cookie)。
        """
        super().__init__()
        self.data_dir = os.path.abspath(data_dir)
        self.config = ConfigManager(self.data_dir)
        self.bank = QuestionBankService(CategoryStore(self.data_dir))
        self.import_service = ImportService(self.bank)
        self.templates = TemplateStore(self.data_dir)
        self.history = HistoryStore(self.data_dir)
        self.exam_service = ExamService()
        self.chaoxing = ChaoxingClient(
            os.path.join(self.data_dir,
                         self.config.settings.chaoxing_cookie_file))
        #: 进行中的答题会话(ExamSession 或 None)。
        self.exam_session: Optional[ExamSession] = None
        #: 最近一次答题结果(ExamResult 或 None)。
        self.exam_result: Optional[ExamResult] = None
        #: 当前答题使用的题目(跨分类,供评分使用)。
        self.exam_questions: List[Question] = []
        #: 抽题配置缓存(分类 id -> {题型: 抽取数量})。
        #: 答题系统内保留上次配置,再答一次时自动复用,直到用户修改。
        self.draw_specs_cache: Dict[str, Dict[str, int]] = {}

    def on_mount(self) -> None:
        """应用挂载后进入主菜单。"""
        self.push_screen("main")

    def action_quit(self) -> None:
        """全局退出快捷键。"""
        self.exit()
