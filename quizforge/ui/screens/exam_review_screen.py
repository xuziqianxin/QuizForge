"""答题回看屏幕:查看作答与正确答案,支持跳转。"""

from __future__ import annotations

from typing import Optional

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, OptionList, Static

from quizforge.services.exam_service import ExamResult

#: 题目状态对应的标记与颜色。
_MARK = {
    True: ("[green]✓[/green]", "正确"),
    False: ("[red]✗[/red]", "错误"),
    None: ("[yellow]○[/yellow]", "未答"),
}


class ExamReviewScreen(Screen):
    """回看界面。

    左侧为可跳转的题目列表(显示状态标记),右侧展示题目详情、你的作答、
    正确答案与解析。
    """

    BINDINGS = [("escape", "go_home", "返回主菜单")]

    def __init__(self) -> None:
        """初始化回看界面。"""
        super().__init__()
        self._index = 0

    @property
    def result(self) -> ExamResult:
        """评分结果(由应用持有)。"""
        return self.app.exam_result  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Vertical():
            yield Static("", id="review_summary")
            with Horizontal():
                yield OptionList(id="review_list")
                with VerticalScroll(id="review_detail"):
                    yield Static("", id="review_detail_text")
            with Horizontal(classes="button-row"):
                yield Button("加入错题本", id="btn_wrongbook",
                             variant="error")
                yield Button("再练一次", id="btn_retry", variant="primary")
                yield Button("返回主菜单", id="btn_home", variant="default")

    def on_mount(self) -> None:
        """挂载时渲染摘要、题目列表与第一题详情。"""
        self._render_all()

    def on_screen_resume(self, event) -> None:
        """成为当前屏幕时全量刷新。

        回看屏幕实例可能被复用(Textual 按名字切换会复用已缓存实例),
        而每次作答都会产生新的 exam_result,必须在此重新渲染,否则会
        显示上一次作答的计分板。
        """
        if self.is_mounted:
            self._render_all()

    def _render_all(self) -> None:
        """按当前 exam_result 全量渲染(摘要、列表、详情)。"""
        result = self.result
        if result is None or not result.results:
            self.query_one("#review_summary", Static).update("(无作答结果)")
            self.query_one("#review_list", OptionList).clear_options()
            self.query_one("#review_detail_text", Static).update("")
            return
        # 错题重练模式:答对已自动移出错题本,答错保留,无需手动再收集。
        if result.session.config.mode == "wrongbook":
            self.query_one("#btn_wrongbook", Button).display = False
        else:
            self.query_one("#btn_wrongbook", Button).display = True
        summary = (f"得分 {result.auto_score} / {result.auto_total}"
                   f"   ·   正确 {result.correct_count}"
                   f"   ·   错误 {result.wrong_count}"
                   f"   ·   未答 {result.unanswered_count}"
                   f"   ·   用时 {result.session.format_elapsed()}")
        if result.no_answer_count:
            summary += f"   ·   未设答案 {result.no_answer_count} 题(未评分)"
        if result.short_question_count:
            summary += f"   ·   简答题 {result.short_question_count} 题(人工评分)"
        self.query_one("#review_summary", Static).update(summary)

        option_list = self.query_one("#review_list", OptionList)
        option_list.clear_options()
        for index, item in enumerate(result.results):
            mark, _ = _MARK[item.is_correct]
            option_list.add_option(
                f"{mark} {index + 1}. {_one_line(item.question.text)}")
        self._render_detail(0)

    # ------------------------------------------------------------------ #
    def _render_detail(self, index: int) -> None:
        """渲染第 index 题的详情。"""
        self._index = index
        item = self.result.results[index]
        question = item.question
        mark, status_text = _MARK[item.is_correct]

        lines = [
            f"[bold]{mark} 第 {index + 1} 题 · {question.qtype.label}"
            f"({status_text})[/bold]",
            "",
            escape(question.text),
        ]
        if question.options:
            lines.append("")
            lines.append("[bold]选项:[/bold]")
            for opt in question.options:
                lines.append(f"  {opt.key}. {escape(opt.text)}")
        lines.append("")
        lines.append(f"[bold]你的作答:[/bold] {escape(item.user_answer)}")
        if item.correct_answer:
            lines.append(f"[bold]正确答案:[/bold] "
                         f"{escape(item.correct_answer)}")
        else:
            lines.append("[dim]正确答案: (未设置,可在题库管理中补充)[/dim]")
        if question.analysis:
            lines.append("")
            lines.append(f"[bold]解析:[/bold] {escape(question.analysis)}")
        if question.source:
            lines.append("")
            lines.append(f"[dim]来源: {escape(question.source)}[/dim]")
        self.query_one("#review_detail_text", Static).update(
            "\n".join(lines))

    # ------------------------------------------------------------------ #
    @on(OptionList.OptionSelected, "#review_list")
    def _on_select(self, event: OptionList.OptionSelected) -> None:
        """跳转到选中的题目。"""
        self._render_detail(event.option_index)

    @on(Button.Pressed, "#btn_wrongbook")
    def _add_to_wrongbook(self) -> None:
        """将本次作答中答错的题目按分类加入错题本。

        每道错题加入其所属分类的错题记录(跨分类题目各自归位)。
        """
        result = self.result
        if result is None or not result.results:
            return
        wrong_items = [
            item for item in result.results if item.is_correct is False
        ]
        if not wrong_items:
            self.notify("本次没有需要加入错题本的题目", severity="information")
            return
        bank = self.app.bank  # type: ignore[attr-defined]
        added = 0
        existed = 0
        for item in wrong_items:
            category_id = bank.find_category_of(item.question.id)
            if category_id is None:
                continue  # 题目已从题库删除,无法归入分类。
            if bank.add_wrong(category_id, item.question.id):
                added += 1
            else:
                existed += 1
        if added == 0 and existed == 0:
            self.notify("题目均已从题库删除,未加入错题本",
                        severity="warning")
            return
        note = f"已加入错题本 {added} 题"
        if existed:
            note += f"(其中 {existed} 题已在错题本中)"
        self.notify(note, severity="information")

    @on(Button.Pressed, "#btn_retry")
    def _retry(self) -> None:
        """重新开始一次答题(使用全新答题设置实例,避免残留上次配置)。"""
        from quizforge.ui.screens.exam_setup_screen import ExamSetupScreen
        self.app.switch_screen(ExamSetupScreen())  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_home")
    def action_go_home(self) -> None:
        """返回主菜单。"""
        self.app.switch_screen("main")  # type: ignore[attr-defined]


def _one_line(text: str, length: int = 24) -> str:
    """将文本压缩为单行摘要。"""
    text = text.replace("\n", " ")
    return text if len(text) <= length else text[:length - 1] + "…"
