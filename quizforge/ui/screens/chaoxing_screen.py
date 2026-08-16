"""学习通拉取屏幕:登录(扫码/账号密码) -> 选课程 -> 选作业 -> 拉取并导入。

Worker 安全约定:
    * 所有后台任务通过 ``_run_async`` 启动,统一 ``exit_on_error=False``,
      任何未捕获异常只会提示,不会导致整个应用退出;
    * 按用途分组(登录/扫码轮询/课程作业),避免 exclusive 取消误伤;
    * 协程内更新 UI 前检查 ``is_mounted``,防止屏幕已关闭时操作控件崩溃。
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (Button, ContentSwitcher, Label, OptionList,
                             Static)

from quizforge.chaoxing.client import (ChaoxingError, ChaoxingClient, Course,
                                       LoginFailedError, QrLoginContext, Work)
from quizforge.models import Question
from quizforge.ui.screens.account_login_modal import AccountLoginModal
from quizforge.ui.screens.modals import ConfirmModal
from quizforge.ui.widgets.qr_widget import render_qr_block

#: 登录轮询间隔(秒)。
_QR_POLL_SECONDS = 2.0

#: worker 分组(登录 / 扫码轮询 / 课程与作业)。
_WORKER_LOGIN = "chaoxing_login"
_WORKER_POLL = "chaoxing_poll"
_WORKER_GROUP = "chaoxing"


class ChaoxingScreen(Screen):
    """学习通作业拉取向导。

    流程:未登录时展示二维码并在后台轮询扫码状态(或使用账号密码登录);
    登录成功后依次选择课程与作业,拉取作业题目并预览,确认后导入题库。
    """

    BINDINGS = [("escape", "go_back", "返回")]

    def __init__(self) -> None:
        """初始化向导。"""
        super().__init__()
        self._qr_context: Optional[QrLoginContext] = None
        self._courses: List[Course] = []
        self._works: List[Work] = []
        self._questions: List[Question] = []
        #: 当前选中课程(导入时用于自动创建同名分类)。
        self._current_course: Optional[Course] = None

    @property
    def _client(self) -> ChaoxingClient:
        """学习通客户端(由应用持有)。"""
        return self.app.chaoxing  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    # 后台任务辅助
    # ------------------------------------------------------------------ #
    def _run_async(self, work, group: str, description: str = "") -> None:
        """以安全方式启动后台任务(worker 异常不会导致应用退出)。"""
        self.run_worker(work, group=group, exclusive=True,
                        exit_on_error=False, description=description)

    def _cancel_workers(self) -> None:
        """取消本屏幕的全部后台任务。"""
        for group in (_WORKER_LOGIN, _WORKER_POLL, _WORKER_GROUP):
            try:
                self.app.workers.cancel_group(self, group)  # type: ignore[attr-defined]
            except (KeyError, AttributeError):
                pass

    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Vertical():
            yield Static("从超星学习通拉取作业题目", classes="title")
            yield Static("", id="cx_status")
            with ContentSwitcher(initial="view_login", id="cx_switcher"):
                with Vertical(id="view_login"):
                    yield Static("", id="cx_qr")
                    with Horizontal(classes="button-row"):
                        yield Button("刷新二维码", id="btn_qr_refresh")
                        yield Button("账号密码登录", id="btn_account_login")
                        yield Button("清除登录状态", id="btn_logout")
                        yield Button("返回", id="btn_back")
                with Vertical(id="view_wizard"):
                    yield Static("", id="cx_welcome")
                    yield Label("选择课程:")
                    yield OptionList(id="cx_courses")
                    yield Label("选择作业:")
                    yield OptionList(id="cx_works")
                    yield Static("", id="cx_preview")
                    with Horizontal(classes="button-row"):
                        yield Button("导入选中作业", id="btn_import",
                                     variant="success", disabled=True)
                        yield Button("刷新课程", id="btn_refresh")
                        yield Button("返回", id="btn_back2")

    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        """挂载时重置状态并判断登录态进入对应流程。

        屏幕实例可能被 Textual 复用,必须在此清空上一次的课程/作业/
        题目与导入按钮状态,避免把上一场拉取的题目导入错误分类。
        """
        self._courses = []
        self._works = []
        self._questions = []
        self._current_course = None
        # 注意:on_mount 阶段 is_mounted 仍为 False(Textual 行为),
        # 但 compose 已完成,query_one 可用。
        self.query_one("#btn_import", Button).disabled = True
        if self._client.is_logged_in:
            self._enter_wizard("已登录,请选择课程")
        else:
            self._start_qr_login()

    def on_unmount(self) -> None:
        """卸载时取消所有后台任务。"""
        self._cancel_workers()

    # ------------------------------------------------------------------ #
    # 登录流程
    # ------------------------------------------------------------------ #
    def _start_qr_login(self) -> None:
        """启动二维码登录:获取二维码并后台轮询。"""
        self.query_one("#cx_status", Static).update("正在获取登录二维码...")
        self._run_async(self._do_start_qr(), _WORKER_LOGIN, "获取二维码")

    async def _do_start_qr(self) -> None:
        """获取二维码并展示。"""
        try:
            context = await asyncio.to_thread(self._client.start_qr_login)
        except ChaoxingError as exc:
            self.app.notify(str(exc), title="学习通",  # type: ignore[attr-defined]
                            severity="error")
            if self.is_mounted:
                self.query_one("#cx_status", Static).update("获取二维码失败")
            return
        self._qr_context = context
        if not self.is_mounted:
            return
        qr_text = render_qr_block(context.qr_image_url)
        self.query_one("#cx_qr", Static).update(qr_text)
        self.query_one("#cx_status", Static).update(
            "请使用学习通 App 扫码登录(二维码约 2 分钟有效)")
        # 后台轮询扫码状态(独立分组,避免 exclusive 取消自身)。
        self._run_async(self._poll_qr_loop(), _WORKER_POLL, "轮询扫码状态")

    async def _poll_qr_loop(self) -> None:
        """轮询扫码状态直到登录完成或超时。"""
        while self.is_mounted and self._qr_context is not None:
            await asyncio.sleep(_QR_POLL_SECONDS)
            try:
                status = await asyncio.to_thread(
                    self._client.poll_qr_login, self._qr_context)
            except ChaoxingError as exc:
                self.app.notify(str(exc), title="学习通",  # type: ignore[attr-defined]
                                severity="error")
                break
            if not status["done"]:
                continue
            if status["ok"]:
                if self.is_mounted:
                    self.query_one("#cx_status", Static).update("登录成功")
                self._enter_wizard("登录成功,请选择课程")
            else:
                self.app.notify(status["msg"], title="学习通",  # type: ignore[attr-defined]
                                severity="warning")
                if self.is_mounted:
                    self.query_one("#cx_status", Static).update("登录失败")
            break

    @on(Button.Pressed, "#btn_qr_refresh")
    def _refresh_qr(self) -> None:
        """重新获取二维码。"""
        self._start_qr_login()

    @on(Button.Pressed, "#btn_account_login")
    def _open_account_login(self) -> None:
        """打开账号密码登录对话框。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            AccountLoginModal(), self._on_account_login)

    def _on_account_login(self,
                          credentials: Optional[tuple]) -> None:
        """账号密码登录回调。"""
        if not credentials:
            return
        phone, password = credentials
        if self.is_mounted:
            self.query_one("#cx_status", Static).update("正在登录...")
        self._run_async(self._do_password_login(phone, password),
                        _WORKER_LOGIN, "账号密码登录")

    async def _do_password_login(self, phone: str, password: str) -> None:
        """执行账号密码登录(成功后停止二维码轮询)。"""
        try:
            await asyncio.to_thread(self._client.login_with_password,
                                    phone, password)
        except LoginFailedError as exc:
            self.app.notify(str(exc), title="学习通",  # type: ignore[attr-defined]
                            severity="error")
            if self.is_mounted:
                self.query_one("#cx_status", Static).update("登录失败,请重试")
            return
        except (ChaoxingError, ImportError) as exc:
            self.app.notify(str(exc), title="学习通",  # type: ignore[attr-defined]
                            severity="error")
            if self.is_mounted:
                self.query_one("#cx_status", Static).update("登录失败")
            return
        # 停止残留的二维码轮询(避免过期/重复登录通知)。
        self.app.workers.cancel_group(self, _WORKER_POLL)  # type: ignore[attr-defined]
        if self.is_mounted:
            self.query_one("#cx_status", Static).update("登录成功")
        self._enter_wizard("登录成功,请选择课程")

    @on(Button.Pressed, "#btn_logout")
    def _logout(self) -> None:
        """清除登录状态并回到登录视图。"""
        self._client.logout()
        self.app.workers.cancel_group(self, _WORKER_POLL)  # type: ignore[attr-defined]
        self.app.notify("已清除登录状态", title="学习通")  # type: ignore[attr-defined]
        if self.is_mounted:
            self.query_one("#cx_switcher").current = "view_login"  # type: ignore[attr-defined]
        self._start_qr_login()

    # ------------------------------------------------------------------ #
    # 登录后的向导
    # ------------------------------------------------------------------ #
    def _enter_wizard(self, message: str) -> None:
        """切换到向导视图并加载课程列表。

        注意:该方法可能在 on_mount 期间被调用,此时 is_mounted 仍为
        False(Textual 行为),因此不做 is_mounted 检查;异步 worker
        协程内部的 UI 更新仍会检查 is_mounted。
        """
        self.query_one("#cx_welcome", Static).update(message)
        self.query_one("#cx_switcher").current = "view_wizard"  # type: ignore[attr-defined]
        self._run_async(self._load_courses(), _WORKER_GROUP, "加载课程")

    async def _load_courses(self) -> None:
        """拉取课程列表。"""
        try:
            courses = await asyncio.to_thread(self._client.get_courses)
        except ChaoxingError as exc:
            self.app.notify(str(exc), title="学习通",  # type: ignore[attr-defined]
                            severity="error")
            return
        self._courses = courses
        if not self.is_mounted:
            return
        option_list = self.query_one("#cx_courses", OptionList)
        option_list.clear_options()
        for index, course in enumerate(courses):
            option_list.add_option(f"{index + 1}. {course.name}")
        self.query_one("#cx_works", OptionList).clear_options()
        self.query_one("#cx_preview", Static).update(
            f"共 {len(courses)} 门课程,请选择课程后选择作业。")

    @on(OptionList.OptionSelected, "#cx_courses")
    def _on_course_selected(self, event: OptionList.OptionSelected) -> None:
        """选择课程后加载作业列表。"""
        if not self._courses:
            return
        index = event.option_index
        if not (0 <= index < len(self._courses)):
            return
        course = self._courses[index]
        self._run_async(self._load_works(course), _WORKER_GROUP,
                        f"加载课程 [{course.name}] 的作业")

    async def _load_works(self, course: Course) -> None:
        """拉取指定课程的作业列表。"""
        self._current_course = course
        try:
            works = await asyncio.to_thread(self._client.get_works, course)
        except ChaoxingError as exc:
            self.app.notify(str(exc), title="学习通",  # type: ignore[attr-defined]
                            severity="error")
            return
        self._works = works
        if not self.is_mounted:
            return
        option_list = self.query_one("#cx_works", OptionList)
        option_list.clear_options()
        for index, work in enumerate(works):
            suffix = f"  (截止: {work.deadline})" if work.deadline else ""
            if work.status:
                suffix += f" [{work.status}]"
            option_list.add_option(f"{index + 1}. {work.name}{suffix}")
        self.query_one("#cx_preview", Static).update(
            f"课程 [{course.name}] 共 {len(works)} 个作业,请选择要拉取的作业。")
        self.query_one("#btn_import", Button).disabled = True

    @on(OptionList.OptionSelected, "#cx_works")
    def _on_work_selected(self, event: OptionList.OptionSelected) -> None:
        """选择作业后拉取题目。"""
        if not self._works:
            return
        index = event.option_index
        if not (0 <= index < len(self._works)):
            return
        work = self._works[index]
        self._run_async(self._fetch_work(work), _WORKER_GROUP,
                        f"拉取作业 [{work.name}]")

    async def _fetch_work(self, work: Work) -> None:
        """拉取并解析作业题目,更新预览。"""
        if self.is_mounted:
            self.query_one("#cx_preview", Static).update(
                f"正在拉取作业 [{work.name}] ...")
        try:
            html = await asyncio.to_thread(self._client.get_work_page, work)
            questions = await asyncio.to_thread(
                _parse_questions, html, f"超星学习通 - {work.name}")
        except (ChaoxingError, ValueError) as exc:
            self.app.notify(str(exc), title="学习通",  # type: ignore[attr-defined]
                            severity="error")
            if self.is_mounted:
                self.query_one("#cx_preview", Static).update("拉取失败")
            return
        self._questions = questions
        if not self.is_mounted:
            return
        stats = _count_by_type(questions)
        self.query_one("#cx_preview", Static).update(
            f"作业 [{work.name}] 共解析到 {len(questions)} 题\n" +
            "  |  ".join(f"{label} {count}" for label, count in stats))
        self.query_one("#btn_import", Button).disabled = (len(questions) == 0)

    @on(Button.Pressed, "#btn_import")
    def _import_questions(self) -> None:
        """将拉取的题目导入题库,自动创建/复用与课程同名的分类。"""
        course = self._current_course
        if course is None:
            self.app.notify("请先选择课程", title="学习通导入",  # type: ignore[attr-defined]
                            severity="warning")
            return
        # 按课程名自动建分类(同名分类复用)。
        category = self.app.bank.create_category(course.name)  # type: ignore[attr-defined]
        summary = self.app.bank.merge_questions(  # type: ignore[attr-defined]
            self._questions, category_id=category.id)
        self._show_import_report(category.name, summary)
        self.app.switch_screen("main")  # type: ignore[attr-defined]

    def _show_import_report(self, category_name: str, summary) -> None:
        """导入完成后展示详细报告(新增/跳过,并列出跳过的题)。"""
        lines = [f"分类 [{category_name}] 导入完成:新增 {summary.added} 题,"
                 f"跳过 {summary.skipped} 题"]
        skipped_text = summary.skipped_detail_text()
        if skipped_text:
            lines.append("")
            lines.append("跳过的题目(可能作业已更新但题库未变):")
            lines.append(skipped_text)
        else:
            lines.append("")
            lines.append("(没有跳过的题目)")
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmModal("导入结果", "\n".join(lines),
                         yes_label="知道了", no_label="关闭"),
            lambda _confirmed: None)

    @on(Button.Pressed, "#btn_refresh")
    def _refresh_courses(self) -> None:
        """重新加载课程列表。"""
        self._run_async(self._load_courses(), _WORKER_GROUP, "刷新课程")

    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_back")
    @on(Button.Pressed, "#btn_back2")
    def action_go_back(self) -> None:
        """返回主菜单。"""
        self.app.switch_screen("main")  # type: ignore[attr-defined]


def _parse_questions(html: str, source: str) -> List[Question]:
    """解析作业页面 HTML 为题目列表(延迟导入避免循环依赖)。"""
    from quizforge.chaoxing.parser import parse_work_page
    return parse_work_page(html, source=source)


def _count_by_type(questions: List[Question]) -> List[tuple]:
    """按题型统计题目数量,返回 [(题型名, 数量), ...]。"""
    from quizforge.models import QuestionType
    counts = {qtype: 0 for qtype in QuestionType}
    for question in questions:
        counts[question.qtype] += 1
    return [(qtype.label, counts[qtype]) for qtype in QuestionType
            if counts[qtype] > 0]
