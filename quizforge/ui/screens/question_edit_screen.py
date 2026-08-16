"""题目编辑屏幕:新增与修改共用同一表单。"""

from __future__ import annotations

from typing import List, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (Button, Input, Label, Select, Static, TextArea)

from quizforge.models import (Option, Question, QuestionType,
                              normalize_answer_text)
from quizforge.ui.screens.modals import ConfirmModal


class QuestionEditScreen(Screen):
    """题目新增/编辑表单。

    Attributes:
        question_id: 编辑的题目 id;None 表示新增。
    """

    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, question_id: Optional[str] = None,
                 category_id: str = "default") -> None:
        """初始化表单。

        Args:
            question_id: 待编辑题目 id;为 None 时进入新增模式。
            category_id: 题目所属分类 id。
        """
        super().__init__()
        self.question_id = question_id
        self.category_id = category_id
        self._is_edit = question_id is not None

    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        """构建表单界面。"""
        with Vertical(id="edit_form"):
            yield Static("编辑题目" if self._is_edit else "添加题目",
                         classes="title")
            yield Label("题型:")
            yield Select(
                [(qtype.label, qtype) for qtype in QuestionType],
                value=QuestionType.SINGLE,
                id="edit_type",
                allow_blank=False,
            )
            yield Label("题干:")
            yield TextArea("", id="edit_text")
            yield Label("选项(每行一个,自动编号 A/B/C...;判断题无需填写):",
                        id="edit_opt_hint")
            yield TextArea("", id="edit_options", disabled=False)
            yield Label("答案:", id="edit_ans_label")
            yield Input("", id="edit_answer",
                        placeholder="单选:A | 多选:A,C | 判断:对/错 | "
                                    "填空/简答:文本(多个可接受答案用 | 分隔)")
            yield Label("解析(可选):")
            yield TextArea("", id="edit_analysis")
            yield Label("来源(可选):")
            yield Input("", id="edit_source")
            with Horizontal(classes="button-row"):
                yield Button("保存", id="btn_save", variant="success")
                yield Button("取消", id="btn_cancel", variant="default")

    def on_mount(self) -> None:
        """挂载时填充表单(编辑模式)。"""
        if self._is_edit and self.question_id:
            question = self.app.bank.get_question(  # type: ignore[attr-defined]
                self.question_id, category_id=self.category_id)
            if question is None:
                self.app.notify("题目不存在", severity="error")  # type: ignore[attr-defined]
                self.dismiss(None)
                return
            self.query_one("#edit_type", Select).value = question.qtype
            self.query_one("#edit_text", TextArea).text = question.text
            self.query_one("#edit_options", TextArea).text = "\n".join(
                opt.text for opt in question.options)
            self.query_one("#edit_answer", Input).value = self._answer_to_text(
                question)
            self.query_one("#edit_analysis", TextArea).text = question.analysis
            self.query_one("#edit_source", Input).value = question.source
        self._sync_type_ui()

    # ------------------------------------------------------------------ #
    # 题型联动
    # ------------------------------------------------------------------ #
    @on(Select.Changed, "#edit_type")
    def _on_type_changed(self) -> None:
        """题型变化时更新选项区可用状态与答案提示。"""
        self._sync_type_ui()

    def _current_type(self) -> QuestionType:
        """读取当前选择的题型。"""
        value = self.query_one("#edit_type", Select).value
        return value if isinstance(value, QuestionType) else QuestionType.SINGLE

    def _sync_type_ui(self) -> None:
        """判断题禁用选项编辑,并更新答案提示。"""
        qtype = self._current_type()
        options_area = self.query_one("#edit_options", TextArea)
        options_area.disabled = (qtype == QuestionType.JUDGE)
        if qtype == QuestionType.JUDGE:
            self.query_one("#edit_ans_label", Label).update("答案(对 或 错):")
        else:
            self.query_one("#edit_ans_label", Label).update("答案:")

    # ------------------------------------------------------------------ #
    # 保存 / 取消
    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_save")
    def _save(self) -> None:
        """校验并保存题目。"""
        try:
            question = self._build_question()
            if self._is_edit and self.question_id:
                self.app.bank.update_question(  # type: ignore[attr-defined]
                    self.question_id, question,
                    category_id=self.category_id)
            else:
                self.app.bank.add_question(question,  # type: ignore[attr-defined]
                                           category_id=self.category_id)
        except (ValueError, KeyError) as exc:
            self.app.notify(str(exc), title="保存失败",  # type: ignore[attr-defined]
                            severity="error")
            return
        self.app.notify("题目已保存", title="题库管理")  # type: ignore[attr-defined]
        self.dismiss(True)

    @on(Button.Pressed, "#btn_cancel")
    def action_cancel(self) -> None:
        """取消编辑(未保存时确认)。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmModal("放弃修改", "当前修改尚未保存,确定放弃吗?",
                         yes_label="放弃", no_label="继续编辑"),
            self._on_discard_confirmed)

    def _on_discard_confirmed(self, confirmed: Optional[bool]) -> None:
        """放弃确认回调。"""
        if confirmed:
            self.dismiss(None)

    # ------------------------------------------------------------------ #
    # 表单解析
    # ------------------------------------------------------------------ #
    def _build_question(self) -> Question:
        """从表单构建题目对象(尚未校验)。"""
        qtype = self._current_type()
        text = self.query_one("#edit_text", TextArea).text.strip()
        options_raw = self.query_one("#edit_options", TextArea).text
        answer_raw = self.query_one("#edit_answer", Input).value.strip()
        analysis = self.query_one("#edit_analysis", TextArea).text.strip()
        source = self.query_one("#edit_source", Input).value.strip()

        question = Question(qtype=qtype, text=text, analysis=analysis,
                            source=source)

        if qtype == QuestionType.JUDGE:
            question.answer = self._parse_judge_answer(answer_raw)
        elif qtype in (QuestionType.SINGLE, QuestionType.MULTIPLE):
            question.options = [
                Option(key="", text=line.strip())
                for line in options_raw.splitlines() if line.strip()
            ]
            question.answer = [
                key for key in normalize_answer_text(answer_raw).split(",")
                if key
            ]
        elif qtype == QuestionType.FILL:
            question.answer = self._split_acceptable_answers(answer_raw)
        else:  # 简答题
            question.answer = self._split_acceptable_answers(answer_raw)
        return question

    @staticmethod
    def _parse_judge_answer(raw: str) -> List[str]:
        """解析判断题答案:"对"/"错"(容忍 √/×/true/false 等写法)。"""
        value = raw.strip().lower()
        if value in ("对", "√", "t", "true", "正确", "是", "a"):
            return ["A"]
        if value in ("错", "×", "x", "f", "false", "错误", "否", "b"):
            return ["B"]
        raise ValueError("判断题答案必须为: 对 或 错")

    @staticmethod
    def _split_acceptable_answers(raw: str) -> List[str]:
        """按 | 分割可接受答案(填空/简答)。"""
        return [part.strip() for part in raw.split("|") if part.strip()]

    @staticmethod
    def _answer_to_text(question: Question) -> str:
        """将题目答案转换为表单文本。"""
        if question.qtype == QuestionType.JUDGE:
            return "对" if question.answer == ["A"] else "错"
        if question.is_choice:
            return ",".join(question.answer)
        return "|".join(question.answer)
