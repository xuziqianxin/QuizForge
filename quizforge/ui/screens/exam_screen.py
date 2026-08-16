"""答题屏幕:逐题作答、答题卡跳转、提交。"""

from __future__ import annotations

import datetime
from typing import List, Optional

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (Button, Checkbox, Input, RadioButton, RadioSet,
                             Static, TextArea)

from quizforge.models import Question, QuestionType
from quizforge.services.exam_service import ExamSession
from quizforge.ui.screens.answer_sheet_modal import AnswerSheetModal
from quizforge.ui.screens.modals import ConfirmModal

#: 计时显示刷新间隔(秒)。
_TIMER_TICK = 1.0


class ExamScreen(Screen):
    """答题界面。

    按会话顺序逐题展示;支持上一题/下一题、答题卡(查看已答并跳题)与提交。
    选择题的展示顺序遵循会话中的选项乱序结果。
    """

    BINDINGS = [("escape", "go_back", "返回")]

    def __init__(self) -> None:
        """初始化答题界面。"""
        super().__init__()
        self._index = 0

    # ------------------------------------------------------------------ #
    @property
    def session(self) -> ExamSession:
        """当前答题会话(由应用持有)。"""
        return self.app.exam_session  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Vertical():
            yield Static("", id="exam_progress")
            yield Static("", id="exam_meta")
            yield Static("", id="exam_stem")
            yield VerticalScroll(id="exam_options")
            yield Static("", id="exam_timer")
            yield Static("提示: 打开答题卡可查看已答情况并跳转题目",
                         id="exam_hint")
            with Horizontal(classes="button-row"):
                yield Button("上一题", id="btn_prev", variant="default")
                yield Button("答题卡", id="btn_sheet", variant="primary")
                yield Button("下一题", id="btn_next", variant="default")
                yield Button("暂停/继续", id="btn_pause", variant="default")
                yield Button("提交", id="btn_submit", variant="success")

    # ------------------------------------------------------------------ #
    async def on_mount(self) -> None:
        """挂载后渲染第一题并开始计时。"""
        self.session.start_timer()
        await self._render_current()
        self._refresh_timer_display()
        # 每秒刷新计时显示。
        self.set_interval(_TIMER_TICK, self._refresh_timer_display)

    def _current_question(self) -> Optional[Question]:
        """返回当前题目;会话为空或题目不存在时返回 None。

        题目来自 ``app.exam_questions``(开始答题时挂载的参与题目),
        它们可能属于任意分类,不能按"未分类"从题库查询。
        """
        session = self.session
        if not session or not session.order:
            return None
        qid = session.order[self._index]
        for question in self.app.exam_questions:  # type: ignore[attr-defined]
            if question.id == qid:
                return question
        return None

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    async def _render_current(self) -> None:
        """渲染当前题目(题干、选项/输入控件与导航按钮状态)。"""
        question = self._current_question()
        if question is None:
            self.app.notify("没有可作答的题目", severity="warning")  # type: ignore[attr-defined]
            return

        total = len(self.session.order)
        self.query_one("#exam_progress", Static).update(
            f"第 {self._index + 1} / {total} 题")
        meta = question.qtype.label
        if question.source:
            meta += f"  ·  来源: {escape(question.source)}"
        self.query_one("#exam_meta", Static).update(meta)
        self.query_one("#exam_stem", Static).update(
            f"[bold]{escape(question.text)}[/bold]")

        options_area = self.query_one("#exam_options", VerticalScroll)
        await options_area.remove_children()
        await self._mount_answer_inputs(options_area, question)

        self.query_one("#btn_prev", Button).disabled = (self._index == 0)
        self.query_one("#btn_next", Button).disabled = \
            (self._index >= total - 1)

    async def _mount_answer_inputs(self, container: VerticalScroll,
                                   question: Question) -> None:
        """按题型挂载作答控件。"""
        answered = self.session.answers.get(question.id, [])
        order_keys = (self.session.option_order.get(question.id)
                      or [opt.key for opt in question.options])
        mapping = question.option_map

        if question.qtype in (QuestionType.SINGLE, QuestionType.JUDGE):
            # 注意:Textual 8 的 RadioButton 无关联值参数,选项键用 id 关联。
            radios = [
                RadioButton(f"{key}. {mapping.get(key, '')}",
                            id=f"opt_{key}")
                for key in order_keys
            ]
            radio_set = RadioSet(*radios, id="exam_radio")
            await container.mount(radio_set)
            if answered:
                button = radio_set.query_one(f"#opt_{answered[0]}",
                                             RadioButton)
                button.value = True
        elif question.qtype == QuestionType.MULTIPLE:
            checks = [
                Checkbox(f"{key}. {mapping.get(key, '')}",
                         id=f"opt_{key}", value=(key in answered))
                for key in order_keys
            ]
            await container.mount(*checks)
        elif question.qtype == QuestionType.FILL:
            await container.mount(
                Input(value=" / ".join(answered), id="fill_input",
                      placeholder="输入答案"))
        else:  # 简答题
            await container.mount(
                TextArea(" / ".join(answered), id="short_area",
                         placeholder="输入答案"))

    # ------------------------------------------------------------------ #
    # 作答记录
    # ------------------------------------------------------------------ #
    def _save_current(self) -> None:
        """将当前题目控件中的作答写入会话(控件未就绪时安全跳过)。"""
        question = self._current_question()
        if question is None:
            return
        options_area = self.query_one("#exam_options", VerticalScroll)
        keys: List[str] = []

        if question.qtype in (QuestionType.SINGLE, QuestionType.JUDGE):
            nodes = options_area.query("#exam_radio").nodes
            if nodes:
                radio_set = nodes[0]
                for button in radio_set.query(RadioButton):
                    if button.value:
                        keys = [str(button.id).removeprefix("opt_")]
                        break
        elif question.qtype == QuestionType.MULTIPLE:
            keys = [
                cb.id.removeprefix("opt_")  # type: ignore[union-attr]
                for cb in options_area.query(Checkbox) if cb.value
            ]
        elif question.qtype == QuestionType.FILL:
            nodes = options_area.query("#fill_input").nodes
            box = nodes[0] if nodes else None
            if box is not None and box.value.strip():
                keys = [box.value.strip()]
        else:  # 简答题
            nodes = options_area.query("#short_area").nodes
            box = nodes[0] if nodes else None
            if box is not None and box.text.strip():
                keys = [box.text.strip()]

        self.session.record_answer(question.id, keys)

    # ------------------------------------------------------------------ #
    # 计时
    # ------------------------------------------------------------------ #
    def _refresh_timer_display(self) -> None:
        """刷新计时显示。

        限时模拟考试:倒计时显示「剩余 MM:SS」,到点自动交卷;
        不限时:正计时显示「用时 MM:SS」。
        """
        session = self.session
        if session.config.time_limit_seconds > 0:
            if session.time_remaining() <= 0:
                # 时间到:保存当前作答并自动交卷(无需确认)。
                self._save_current()
                self._finish()
                return
            self.query_one("#exam_timer", Static).update(
                f"剩余 {session.format_remaining()}")
        else:
            self.query_one("#exam_timer", Static).update(
                f"用时 {session.format_elapsed()}")

    def _set_frozen(self, frozen: bool) -> None:
        """暂停时冻结作答:禁用导航/提交按钮与全部作答控件。

        暂停计时意味着"考试暂停",期间不能继续作答、切题或提交,
        只能点击「暂停/继续」恢复。
        """
        for button_id in ("#btn_prev", "#btn_next", "#btn_sheet",
                          "#btn_submit"):
            self.query_one(button_id, Button).disabled = frozen
        options_area = self.query_one("#exam_options", VerticalScroll)
        for widget in options_area.query(
                "Button, Checkbox, Input, RadioButton, TextArea"):
            widget.disabled = frozen
        if not frozen:
            # 恢复后按当前题号还原导航按钮状态(首题上一题禁用等)。
            total = len(self.session.order)
            self.query_one("#btn_prev", Button).disabled = (self._index == 0)
            self.query_one("#btn_next", Button).disabled = \
                (self._index >= total - 1)

    @on(Button.Pressed, "#btn_pause")
    def _toggle_pause(self) -> None:
        """暂停 / 继续计时(暂停期间冻结作答)。"""
        if self.session.paused:
            self.session.resume_timer()
            self._set_frozen(False)
            self.query_one("#btn_pause", Button).label = "暂停"
            self.app.notify("计时继续", title="答题")  # type: ignore[attr-defined]
        else:
            self.session.pause_timer()
            self._set_frozen(True)
            self.query_one("#btn_pause", Button).label = "继续"
            self.app.notify("计时已暂停,期间不可作答", title="答题")  # type: ignore[attr-defined]
        self._refresh_timer_display()

    # ------------------------------------------------------------------ #
    # 导航
    # ------------------------------------------------------------------ #
    def _goto(self, index: int) -> None:
        """跳转到指定题号(先保存当前作答)。"""
        self._save_current()
        if 0 <= index < len(self.session.order):
            self._index = index
        self.run_worker(self._render_current(), exclusive=True,
                        exit_on_error=False)

    @on(Button.Pressed, "#btn_prev")
    def _prev(self) -> None:
        """上一题。"""
        self._goto(self._index - 1)

    @on(Button.Pressed, "#btn_next")
    def _next(self) -> None:
        """下一题。"""
        self._goto(self._index + 1)

    @on(Button.Pressed, "#btn_sheet")
    def _open_sheet(self) -> None:
        """打开答题卡。"""
        self._save_current()
        items = [
            (index, qid, self.session.answers.get(qid, []))
            for index, qid in enumerate(self.session.order)
        ]
        self.app.push_screen(  # type: ignore[attr-defined]
            AnswerSheetModal(items, len(self.session.order)),
            self._on_sheet_result)

    def _on_sheet_result(self, index: Optional[int]) -> None:
        """答题卡跳转回调。"""
        if isinstance(index, int):
            self._goto(index)

    # ------------------------------------------------------------------ #
    # 提交
    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_submit")
    def _submit(self) -> None:
        """提交作答(有未答题时先确认)。"""
        self._save_current()
        unanswered = [
            qid for qid in self.session.order
            if not self.session.is_answered(qid)
        ]
        if unanswered:
            self.app.push_screen(  # type: ignore[attr-defined]
                ConfirmModal("提交确认",
                             f"还有 {len(unanswered)} 题未作答,确定提交吗?"),
                self._on_submit_confirmed)
        else:
            self._finish()

    def _on_submit_confirmed(self, confirmed: Optional[bool]) -> None:
        """提交确认回调。"""
        if confirmed:
            self._finish()

    def _finish(self) -> None:
        """评分并进入回看界面。

        app.exam_result 已在下方更新为新结果;回看屏幕通过
        on_screen_resume 在成为当前屏幕时全量刷新,保证显示本次结果。

        错题重练模式:答对的题目自动移出错题本(答错保留,继续重练),
        不再次收集。每次提交后追加一条历史成绩记录。
        """
        session = self.session
        questions = self.app.exam_questions  # type: ignore[attr-defined]
        session.finished_at = datetime.datetime.now().isoformat(
            timespec="seconds")
        session.pause_timer()  # 提交后停止计时,用时写入会话。
        result = self.app.exam_service.grade(session, questions)  # type: ignore[attr-defined]
        if session.config.mode == "wrongbook":
            bank = self.app.bank  # type: ignore[attr-defined]
            for item in result.results:
                if item.is_correct is True:
                    category_id = bank.find_category_of(item.question.id)
                    if category_id is not None:
                        bank.remove_wrong(category_id, item.question.id)
        self.app.exam_result = result  # type: ignore[attr-defined]
        self._record_history(result)
        self.app.switch_screen("review")  # type: ignore[attr-defined]

    def _record_history(self, result: "ExamResult") -> None:
        """把本次成绩追加到历史记录(data/history.json)。"""
        from collections import Counter
        session = result.session
        type_dist = Counter(r.question.qtype.value for r in result.results)
        # 来源分类:错题重练记为「XX错题」;其余从题目所属分类推断;
        # 文件选题的题目可能跨分类,统一记「文件选题」。
        category_name = "文件选题"
        if session.config.mode == "wrongbook":
            category_name = "错题重练"
        else:
            info = self.app.bank.get_category(  # type: ignore[attr-defined]
                session.config.category_id or "default")
            if info is not None:
                category_name = info.name
        record = {
            "timestamp": session.finished_at
                         or datetime.datetime.now().isoformat(
                             timespec="seconds"),
            "mode": session.config.mode,
            "category": category_name,
            "auto_score": result.auto_score,
            "auto_total": result.auto_total,
            "correct": result.correct_count,
            "wrong": result.wrong_count,
            "unanswered": result.unanswered_count,
            "no_answer": result.no_answer_count,
            "elapsed_seconds": session.elapsed_seconds,
            "question_count": len(session.order),
            "type_distribution": dict(type_dist),
            # 逐题作答详情(历史查询 / HTML 导出用)。
            "details": [
                {
                    "qtype": item.question.qtype.value,
                    "qtype_label": item.question.qtype.label,
                    "text": item.question.text,
                    "options": [
                        {"key": opt.key, "text": opt.text}
                        for opt in item.question.options
                    ],
                    "user_answer": item.user_answer,
                    "correct_answer": item.correct_answer,
                    "is_correct": item.is_correct,
                    "analysis": item.question.analysis,
                    "answer": list(item.question.answer),
                }
                for item in result.results
            ],
        }
        try:
            self.app.history.add(record)  # type: ignore[attr-defined]
        except OSError:
            # 历史记录写入失败不影响本次答题结果。
            pass

    # ------------------------------------------------------------------ #
    def action_go_back(self) -> None:
        """退出本次答题(需确认)。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmModal("退出答题", "退出将丢弃本次作答,确定吗?",
                         yes_label="退出", no_label="继续答题"),
            self._on_back_confirmed)

    def _on_back_confirmed(self, confirmed: Optional[bool]) -> None:
        """退出确认回调。"""
        if confirmed:
            self.app.switch_screen("main")  # type: ignore[attr-defined]
