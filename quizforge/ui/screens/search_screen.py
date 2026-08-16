"""查题屏幕:按分类/关键词/题型检索并查看题目详情。"""

from __future__ import annotations

from typing import List, Optional

from rich.markup import escape
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (Button, DataTable, Input, Select, Static)

from quizforge.models import Question, QuestionType
from quizforge.services.bank_service import is_wrongbook_id
from quizforge.ui.screens.question_edit_screen import QuestionEditScreen

#: 结果单页显示条数(分页浏览,大题库可翻页看全量)。
_PAGE_SIZE = 50


class SearchScreen(Screen):
    """查题界面。

    顶部为分类与检索栏(关键词 + 题型),中间为结果表格,底部为选中题目的
    详情(含答案与解析);选中结果可一键进入编辑。结果分页浏览,大题库
    可翻页看全量。
    """

    BINDINGS = [("escape", "go_back", "返回")]

    def __init__(self) -> None:
        """初始化查题界面。"""
        super().__init__()
        self._selected_id: Optional[str] = None
        self._category_id: str = "default"
        self._page: int = 0
        self._total: int = 0

    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Vertical():
            yield Static("查题", classes="title")
            with Horizontal(id="search_bar"):
                yield Select([], id="search_category", allow_blank=True,
                             prompt="分类")
                yield Input(placeholder="输入关键词,实时检索...",
                            id="search_kw")
                yield Select(
                    [(qtype.label, qtype) for qtype in QuestionType] +
                    [("全部题型", "all")],
                    value="all",
                    prompt="题型",
                    id="search_type",
                    allow_blank=False,
                )
            yield DataTable(id="search_table", cursor_type="row",
                            zebra_stripes=True)
            with Horizontal(id="search_pager"):
                yield Button("◀ 上一页", id="btn_prev_page",
                             variant="default", disabled=True)
                yield Static("", id="search_page_info")
                yield Button("下一页 ▶", id="btn_next_page",
                             variant="default", disabled=True)
            with VerticalScroll(id="search_detail"):
                yield Static("", id="search_detail_text")
            with Horizontal(classes="button-row"):
                yield Button("编辑此题", id="btn_edit", variant="primary",
                             disabled=True)
                yield Button("返回", id="btn_back", variant="default")

    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        """挂载时初始化表格与分类。"""
        table = self.query_one("#search_table", DataTable)
        table.add_column("#", key="index", width=4)
        table.add_column("类型", key="qtype", width=8)
        table.add_column("题干", key="text", width=46)
        table.add_column("答案", key="answer", width=22)
        table.add_column("来源", key="source", width=20)
        self._reload_categories()

    def on_screen_resume(self, event) -> None:
        """每次成为当前屏幕时刷新(保留当前分类选择)。"""
        if self.is_mounted:
            self._reload_categories(auto_pick=False)

    def _reload_categories(self, auto_pick: bool = True) -> None:
        """刷新分类下拉列表。

        Args:
            auto_pick: 进入界面时自动选择第一个非空分类。
        """
        categories = self.app.bank.list_categories()  # type: ignore[attr-defined]
        select = self.query_one("#search_category", Select)
        select.set_options(
            [(f"{c.name}({c.count})", c.id) for c in categories])
        ids = [c.id for c in categories]
        if auto_pick:
            nonempty = [c.id for c in categories if c.count > 0]
            self._category_id = (
                nonempty[0] if nonempty else (ids[0] if ids else "default"))
        elif self._category_id not in ids:
            self._category_id = ids[0] if ids else "default"
        if self._category_id in ids:
            select.value = self._category_id
        self._refresh_table()

    @on(Select.Changed, "#search_category")
    def _on_category_changed(self) -> None:
        """切换分类时刷新(用户手动切换,不自动改选)。

        注意:分类 Select 允许空白(allow_blank),空白时保留当前分类,
        避免 str(None) 产生 "None" 分类导致静默无结果。
        """
        if self.is_mounted:
            value = self.query_one("#search_category", Select).value
            if value:
                self._category_id = str(value)
            self._refresh_table()

    def _refresh_table(self) -> None:
        """按当前分类、检索条件与页码刷新结果表格。"""
        keyword = self.query_one("#search_kw", Input).value
        type_value = self.query_one("#search_type", Select).value
        qtype = type_value if isinstance(type_value, QuestionType) else None
        try:
            self._total = self.app.bank.count_matches(  # type: ignore[attr-defined]
                keyword, qtype, category_id=self._category_id)
            total_pages = max(1, -(-self._total // _PAGE_SIZE))
            self._page = min(self._page, total_pages - 1)
            self._page = max(0, self._page)
            results: List[Question] = self.app.bank.search(  # type: ignore[attr-defined]
                keyword, qtype, category_id=self._category_id,
                limit=_PAGE_SIZE, offset=self._page * _PAGE_SIZE)
        except KeyError:
            results = []
            self._total = 0
            total_pages = 1
            self._page = 0

        table = self.query_one("#search_table", DataTable)
        table.clear()
        for index, question in enumerate(results, start=1):
            # 无答案题目醒目标记:答案列黄色高亮 + 前缀符号。
            answer_text = question.answer_text()
            if not question.answer:
                answer_cell = Text(f"⚠ {answer_text}", style="bold yellow")
            else:
                answer_cell = Text(answer_text)
            table.add_row(
                Text(str(index)),
                Text(question.qtype.label),
                Text(_one_line(question.text, 46)),
                answer_cell,
                Text(_one_line(question.source, 20)),
                key=question.id,
            )
        self._selected_id = None
        self.query_one("#btn_edit", Button).disabled = True
        self.query_one("#search_page_info", Static).update(
            f"第 {self._page + 1} / {total_pages} 页"
            f" · 本页 {len(results)} 题")
        self.query_one("#btn_prev_page", Button).disabled = (self._page == 0)
        self.query_one("#btn_next_page", Button).disabled = \
            (self._page >= total_pages - 1)
        hint = f"共检索到 {self._total} 题"
        if self._total > len(results):
            hint += f",已分 {total_pages} 页(可翻页浏览全部)"
        self.query_one("#search_detail_text", Static).update(
            hint + ",点击结果行查看详情。")

    @on(Button.Pressed, "#btn_prev_page")
    def _prev_page(self) -> None:
        """上一页。"""
        if self._page > 0:
            self._page -= 1
            self._refresh_table()

    @on(Button.Pressed, "#btn_next_page")
    def _next_page(self) -> None:
        """下一页。"""
        total_pages = max(1, -(-self._total // _PAGE_SIZE))
        if self._page < total_pages - 1:
            self._page += 1
            self._refresh_table()

    # ------------------------------------------------------------------ #
    @on(Input.Changed, "#search_kw")
    def _on_kw_changed(self) -> None:
        """关键词变化时刷新。"""
        if self.is_mounted:
            self._refresh_table()

    @on(Select.Changed, "#search_type")
    def _on_type_changed(self) -> None:
        """题型变化时刷新。"""
        if self.is_mounted:
            self._refresh_table()

    @on(DataTable.RowHighlighted, "#search_table")
    def _on_row_selected(self, event: DataTable.RowHighlighted) -> None:
        """选中行时展示题目详情(高亮即选中)。"""
        self._selected_id = str(event.row_key.value)
        question = self.app.bank.get_question(  # type: ignore[attr-defined]
            self._selected_id, category_id=self._category_id)
        if question is None:
            return
        # 「XX错题」虚拟分类是聚合视图,不可直接编辑,跳转到真实分类。
        if is_wrongbook_id(self._category_id):
            real = self.app.bank.find_category_of(self._selected_id)  # type: ignore[attr-defined]
            self.query_one("#btn_edit", Button).disabled = real is None
        else:
            self.query_one("#btn_edit", Button).disabled = False
        lines = [
            f"[bold]{question.qtype.label}[/bold]  "
            f"[dim]{escape(question.source)}[/dim]",
            "",
            escape(question.text),
        ]
        if question.options:
            lines.append("")
            lines.append("[bold]选项:[/bold]")
            for opt in question.options:
                lines.append(f"  {opt.key}. {escape(opt.text)}")
        lines.append("")
        if question.answer:
            lines.append(
                f"[bold]答案:[/bold] {escape(question.answer_text())}")
        else:
            lines.append("[bold yellow]⚠ 答案: (未设置,可在题库管理中补充)[/bold yellow]")
        if question.analysis:
            lines.append("")
            lines.append(f"[bold]解析:[/bold] {escape(question.analysis)}")
        self.query_one("#search_detail_text", Static).update(
            "\n".join(lines))

    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_edit")
    def _edit_selected(self) -> None:
        """编辑当前选中的题目(错题虚拟分类时定位真实分类)。"""
        if self._selected_id:
            category_id = self._category_id
            if is_wrongbook_id(category_id):
                real = self.app.bank.find_category_of(  # type: ignore[attr-defined]
                    self._selected_id)
                if real is None:
                    self.app.notify("题目已从题库删除",  # type: ignore[attr-defined]
                                    title="查题", severity="warning")
                    return
                category_id = real
            self.app.push_screen(  # type: ignore[attr-defined]
                QuestionEditScreen(question_id=self._selected_id,
                                   category_id=category_id),
                self._on_edit_done)

    def _on_edit_done(self, _: Optional[bool]) -> None:
        """编辑完成后刷新检索结果。"""
        self._refresh_table()

    @on(Button.Pressed, "#btn_back")
    def action_go_back(self) -> None:
        """返回主菜单。"""
        self.app.switch_screen("main")  # type: ignore[attr-defined]


def _one_line(text: str, length: int = 24) -> str:
    """将文本压缩为单行摘要。"""
    text = text.replace("\n", " ")
    return text if len(text) <= length else text[:length - 1] + "…"
