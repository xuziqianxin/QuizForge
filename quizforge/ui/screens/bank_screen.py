"""题库管理屏幕:按分类增删改查、检索、导入导出。"""

from __future__ import annotations

import datetime
from typing import List, Optional

from rich.markup import escape
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (Button, DataTable, Input, Select, Static)

from quizforge.models import Question, QuestionType
from quizforge.services.bank_service import (CategoryInfo,
                                             is_wrongbook_id)
from quizforge.storage import DEFAULT_CATEGORY_NAME
from quizforge.ui.screens.modals import ConfirmModal, PromptModal
from quizforge.ui.screens.question_edit_screen import QuestionEditScreen

#: 表格单页显示条数(分页浏览,大题库可翻页看全量)。
_PAGE_SIZE = 50


class QuestionBankScreen(Screen):
    """题库管理界面。

    顶部为分类选择与检索栏(关键词 + 题型过滤),中部为题目表格,底部为
    操作按钮。选中行后可编辑或删除;支持 JSON 导入导出与跳转学习通拉取。
    表格分页浏览:底部「上一页/下一页」翻页,大题库可看全量。
    """

    BINDINGS = [("escape", "go_back", "返回")]

    def __init__(self) -> None:
        """初始化题库管理界面。"""
        super().__init__()
        self._selected_id: Optional[str] = None
        self._filtered: List[Question] = []
        self._category_id: str = "default"
        self._page: int = 0
        self._total: int = 0

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Vertical():
            yield Static("题库管理", classes="title")
            with Horizontal(id="bank_category_bar"):
                yield Select([], id="bank_category", allow_blank=True,
                             prompt="分类")
                yield Button("新建分类", id="btn_new_cat", variant="default")
                yield Button("删除分类", id="btn_del_cat", variant="error")
            with Horizontal(id="bank_search_bar"):
                yield Input(placeholder="关键词检索(题干/选项/答案/来源)...",
                            id="bank_search")
                yield Select(
                    [(qtype.label, qtype) for qtype in QuestionType] +
                    [("全部题型", "all")],
                    value="all",
                    prompt="题型",
                    id="bank_type",
                    allow_blank=False,
                )
            with Horizontal(id="bank_toolbar"):
                yield Button("添加", id="btn_add", variant="primary")
                yield Button("编辑", id="btn_edit", variant="default",
                             disabled=True)
                yield Button("删除", id="btn_delete", variant="error",
                             disabled=True)
                yield Button("错题", id="btn_wrongbook", variant="default")
                yield Button("导入", id="btn_import", variant="default")
                yield Button("导出", id="btn_export", variant="default")
                yield Button("导出HTML", id="btn_export_html",
                             variant="default")
                yield Button("学习通", id="btn_chaoxing", variant="default")
                yield Button("返回", id="btn_back", variant="default")
            yield DataTable(id="bank_table", cursor_type="row",
                            zebra_stripes=True)
            with Horizontal(id="bank_pager"):
                yield Button("◀ 上一页", id="btn_prev_page",
                             variant="default", disabled=True)
                yield Static("", id="bank_page_info")
                yield Button("下一页 ▶", id="btn_next_page",
                             variant="default", disabled=True)
            yield Static("", id="bank_footer")

    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        """挂载时初始化表格与分类列表。"""
        table = self.query_one("#bank_table", DataTable)
        table.add_column("#", key="index", width=4)
        table.add_column("类型", key="qtype", width=8)
        table.add_column("题干", key="text", width=50)
        table.add_column("答案", key="answer", width=24)
        table.add_column("来源", key="source", width=22)
        self._reload_categories()

    def on_screen_resume(self, event) -> None:
        """每次成为当前屏幕时刷新数据(保留当前分类选择)。"""
        if self.is_mounted:
            self._reload_categories(auto_pick=False)

    # ------------------------------------------------------------------ #
    # 分类
    # ------------------------------------------------------------------ #
    def _reload_categories(self, auto_pick: bool = True) -> None:
        """刷新分类下拉列表并保持当前选中分类。

        Args:
            auto_pick: 进入界面时自动选择第一个非空分类(用户手动
                切换分类后传 False)。
        """
        categories = self.app.bank.list_categories()  # type: ignore[attr-defined]
        select = self.query_one("#bank_category", Select)
        options = [(f"{c.name}({c.count})", c.id) for c in categories]
        select.set_options(options)
        ids = [c.id for c in categories]
        if auto_pick:
            nonempty = [c.id for c in categories if c.count > 0]
            self._category_id = (
                nonempty[0] if nonempty else (ids[0] if ids else "default"))
        elif self._category_id not in ids:
            self._category_id = ids[0] if ids else "default"
        if self._category_id in ids:
            select.value = self._category_id
        self._update_delete_button()
        self._refresh_table()

    def _update_delete_button(self) -> None:
        """按当前分类是否可删除,启用/禁用「删除分类」按钮。

        默认分类是兜底分类,不允许删除;「XX错题」是虚拟分类(聚合
        真实分类错题),同样不可删除。
        """
        button = self.query_one("#btn_del_cat", Button)
        button.disabled = (self._current_category() == "default" or
                           is_wrongbook_id(self._current_category()))

    def _current_category(self) -> str:
        """读取当前选中的分类 id。"""
        value = self.query_one("#bank_category", Select).value
        return str(value) if value else self._category_id

    @on(Select.Changed, "#bank_category")
    def _on_category_changed(self) -> None:
        """切换分类时刷新表格(用户手动切换,不自动改选)。"""
        if self.is_mounted:
            self._category_id = self._current_category()
            self._selected_id = None
            self._update_delete_button()
            self._refresh_table()

    @on(Button.Pressed, "#btn_new_cat")
    def _new_category(self) -> None:
        """新建分类。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            PromptModal("新建分类", "输入分类名称(如学科名、课程名):",
                        placeholder="例如: 高等数学"),
            self._on_category_created)

    def _on_category_created(self, name: Optional[str]) -> None:
        """新建分类回调。"""
        if not name:
            return
        try:
            info: CategoryInfo = self.app.bank.create_category(name)  # type: ignore[attr-defined]
        except ValueError as exc:
            self.app.notify(str(exc), title="新建分类",  # type: ignore[attr-defined]
                            severity="error")
            return
        self._category_id = info.id
        self._reload_categories(auto_pick=False)
        self.app.notify(f"已创建分类 [{info.name}]",  # type: ignore[attr-defined]
                        title="题库管理")

    @on(Button.Pressed, "#btn_del_cat")
    def _delete_category(self) -> None:
        """删除当前分类(连同其中题目,需确认)。"""
        category_id = self._current_category()
        if category_id == "default" or is_wrongbook_id(category_id):
            self.app.notify("该分类不可删除",  # type: ignore[attr-defined]
                            title="题库管理", severity="warning")
            return
        info = self.app.bank.get_category(category_id)  # type: ignore[attr-defined]
        if info is None:
            return
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmModal("删除分类",
                         f"确定删除分类 [{info.name}] 吗?\n"
                         f"将连同其中 {info.count} 道题目一并删除,"
                         "且不可恢复!"),
            self._on_category_deleted)

    def _on_category_deleted(self, confirmed: Optional[bool]) -> None:
        """删除分类确认回调。"""
        if confirmed:
            self.app.bank.delete_category(self._category_id)  # type: ignore[attr-defined]
            self._category_id = "default"
            self._reload_categories()
            self.app.notify("分类已删除",  # type: ignore[attr-defined]
                            title="题库管理")

    # ------------------------------------------------------------------ #
    # 数据加载与展示
    # ------------------------------------------------------------------ #
    def _current_filter(self) -> tuple[str, Optional[QuestionType]]:
        """读取当前检索条件,返回 (关键词, 题型)。"""
        keyword = self.query_one("#bank_search", Input).value
        type_value = self.query_one("#bank_type", Select).value
        qtype = type_value if isinstance(type_value, QuestionType) else None
        return keyword, qtype

    def _refresh_table(self) -> None:
        """按当前分类、检索条件与页码刷新表格与底部统计。"""
        keyword, qtype = self._current_filter()
        category_id = self._current_category()
        try:
            self._total = self.app.bank.count_matches(  # type: ignore[attr-defined]
                keyword, qtype, category_id=category_id)
            total_pages = max(1, -(-self._total // _PAGE_SIZE))
            self._page = min(self._page, total_pages - 1)
            self._page = max(0, self._page)
            self._filtered = self.app.bank.search(  # type: ignore[attr-defined]
                keyword, qtype, category_id=category_id,
                limit=_PAGE_SIZE, offset=self._page * _PAGE_SIZE)
        except KeyError:
            self._filtered = []
            self._total = 0
            total_pages = 1
            self._page = 0
        table = self.query_one("#bank_table", DataTable)
        table.clear()
        for index, question in enumerate(self._filtered, start=1):
            # 无答案题目醒目标记:答案列黄色高亮 + 前缀符号。
            answer_cell = question.answer_text()
            if not question.answer:
                answer_cell = Text(f"⚠ {answer_cell}", style="bold yellow")
            else:
                answer_cell = Text(answer_cell)
            table.add_row(
                Text(str(index)),
                Text(question.qtype.label),
                Text(_truncate(question.text, 46)),
                answer_cell,
                Text(_truncate(question.source, 20)),
                key=question.id,
            )
        # 页码信息与翻页按钮状态。
        self.query_one("#bank_page_info", Static).update(
            f"第 {self._page + 1} / {total_pages} 页"
            f" · 本页 {len(self._filtered)} 题")
        self.query_one("#btn_prev_page", Button).disabled = (self._page == 0)
        self.query_one("#btn_next_page", Button).disabled = \
            (self._page >= total_pages - 1)
        hint = f"共 {self._total} 题"
        if self._total > len(self._filtered):
            hint += f",已分 {total_pages} 页(可用下方翻页浏览全部)"
        footer = self.query_one("#bank_footer", Static)
        footer.update(hint)
        # 检索结果变化后,旧选中可能已失效。
        if self._selected_id not in {q.id for q in self._filtered}:
            self._selected_id = None
        self._update_action_buttons()

    @on(Button.Pressed, "#btn_prev_page")
    def _prev_page(self) -> None:
        """上一页。"""
        if self._page > 0:
            self._page -= 1
            self._selected_id = None
            self._refresh_table()

    @on(Button.Pressed, "#btn_next_page")
    def _next_page(self) -> None:
        """下一页。"""
        total_pages = max(1, -(-self._total // _PAGE_SIZE))
        if self._page < total_pages - 1:
            self._page += 1
            self._selected_id = None
            self._refresh_table()

    def _update_action_buttons(self) -> None:
        """根据是否有选中行启停编辑/删除按钮。

        「XX错题」虚拟分类是聚合视图,题目归属真实分类,不支持在此
        直接编辑/删除/添加。
        """
        has_selection = self._selected_id is not None
        is_wrongbook = is_wrongbook_id(self._current_category())
        self.query_one("#btn_edit", Button).disabled = \
            not has_selection or is_wrongbook
        self.query_one("#btn_delete", Button).disabled = \
            not has_selection or is_wrongbook
        self.query_one("#btn_add", Button).disabled = is_wrongbook
        self.query_one("#btn_import", Button).disabled = is_wrongbook
        self.query_one("#btn_export", Button).disabled = is_wrongbook
        self.query_one("#btn_export_html", Button).disabled = is_wrongbook

    def _refresh_from_bank(self, _result: Optional[bool] = None) -> None:
        """编辑返回后刷新表格(同时保留选中)。"""
        self._refresh_table()

    # ------------------------------------------------------------------ #
    # 行选择
    # ------------------------------------------------------------------ #
    @on(DataTable.RowHighlighted, "#bank_table")
    def _on_row_selected(self, event: DataTable.RowHighlighted) -> None:
        """记录选中题目的 id(高亮即选中)。

        注意:Textual 的 DataTable 单击行只触发 RowHighlighted,
        RowSelected 需要双击或点击已高亮行,因此用 RowHighlighted。
        """
        self._selected_id = str(event.row_key.value)
        self._update_action_buttons()

    # ------------------------------------------------------------------ #
    # 检索
    # ------------------------------------------------------------------ #
    @on(Input.Changed, "#bank_search")
    def _on_search_changed(self) -> None:
        """关键词变化时刷新。"""
        if self.is_mounted:
            self._refresh_table()

    @on(Select.Changed, "#bank_type")
    def _on_type_changed(self) -> None:
        """题型过滤变化时刷新。"""
        if self.is_mounted:
            self._refresh_table()

    # ------------------------------------------------------------------ #
    # 操作
    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_add")
    def _add_question(self) -> None:
        """打开新增题目表单(属于当前分类)。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            QuestionEditScreen(category_id=self._current_category()),
            self._refresh_from_bank)

    @on(Button.Pressed, "#btn_edit")
    def _edit_question(self) -> None:
        """打开编辑表单(带当前选中题目)。"""
        if self._selected_id:
            self.app.push_screen(  # type: ignore[attr-defined]
                QuestionEditScreen(question_id=self._selected_id,
                                   category_id=self._current_category()),
                self._refresh_from_bank)

    @on(Button.Pressed, "#btn_delete")
    def _delete_question(self) -> None:
        """删除当前选中题目(带确认)。"""
        if not self._selected_id:
            return
        question = self.app.bank.get_question(  # type: ignore[attr-defined]
            self._selected_id, category_id=self._current_category())
        title = question.text if question else ""
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmModal("删除确认",
                         f"确定删除题目?\n\n{_truncate(title, 60)}"),
            self._on_delete_confirmed)

    def _on_delete_confirmed(self, confirmed: Optional[bool]) -> None:
        """删除确认回调。"""
        if confirmed and self._selected_id:
            self.app.bank.delete_question(  # type: ignore[attr-defined]
                self._selected_id, category_id=self._current_category())
            self._selected_id = None
            self._refresh_table()
            self.app.notify("题目已删除", title="题库管理")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_import")
    def _import_json(self) -> None:
        """导入 JSON 题库文件到当前分类。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            PromptModal("导入题库",
                        f"将导入到分类 [{self._current_category_name()}]。\n"
                        "请输入 JSON 题库文件路径\n"
                        "(支持题目列表或 {\"questions\": [...]} 格式):",
                        placeholder=r"data\import.json"),
            self._on_import_path)

    def _current_category_name(self) -> str:
        """当前分类名称(用于提示)。"""
        info = self.app.bank.get_category(self._current_category())  # type: ignore[attr-defined]
        return info.name if info else DEFAULT_CATEGORY_NAME

    def _on_import_path(self, path: Optional[str]) -> None:
        """导入路径回调。"""
        if not path:
            return
        try:
            summary = self.app.import_service.import_json_file(  # type: ignore[attr-defined]
                path, category_id=self._current_category())
        except (ValueError, KeyError, OSError) as exc:
            self.app.notify(str(exc), title="导入失败",  # type: ignore[attr-defined]
                            severity="error")
            return
        self._reload_categories(auto_pick=False)
        self._show_import_report(summary)

    def _show_import_report(self, summary) -> None:
        """导入完成后展示详细报告(新增/跳过,并列出跳过的题)。"""
        lines = [f"导入完成:新增 {summary.added} 题,"
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
            self._on_import_report_closed)

    def _on_import_report_closed(self, _confirmed: Optional[bool]) -> None:
        """导入报告关闭回调(无操作)。"""
        pass

    @on(Button.Pressed, "#btn_export")
    def _export_json(self) -> None:
        """导出当前检索结果(或全部)为 JSON 文件。"""
        default_name = datetime.datetime.now().strftime("export_%Y%m%d_%H%M%S")
        self.app.push_screen(  # type: ignore[attr-defined]
            PromptModal("导出题库",
                        f"将导出分类 [{self._current_category_name()}] 的"
                        f"检索结果共 {len(self._filtered)} 题,"
                        "请输入输出文件路径:",
                        value=f"data/{default_name}.json"),
            self._on_export_path)

    @on(Button.Pressed, "#btn_export_html")
    def _export_html(self) -> None:
        """导出当前检索结果为 HTML 试卷(可打印纸质练习)。"""
        if not self._filtered:
            self.app.notify("当前没有可导出的题目",  # type: ignore[attr-defined]
                            title="导出 HTML", severity="warning")
            return
        default_name = datetime.datetime.now().strftime("paper_%Y%m%d_%H%M%S")
        self.app.push_screen(  # type: ignore[attr-defined]
            PromptModal("导出 HTML 试卷",
                        f"将导出分类 [{self._current_category_name()}] 的"
                        f"检索结果共 {len(self._filtered)} 题为"
                        " HTML 试卷(带答题区,可打印):\n"
                        "请输入输出文件路径:",
                        value=f"data/{default_name}.html"),
            self._on_export_html_path)

    def _on_export_html_path(self, path: Optional[str]) -> None:
        """HTML 导出路径回调。"""
        if not path:
            return
        try:
            from quizforge.services.html_exporter import export_questions_html
            count = len(self._filtered)
            export_questions_html(
                self._filtered, path,
                title=f"{self._current_category_name()}试卷",
                show_answers=False)
        except OSError as exc:
            self.app.notify(f"导出失败: {exc}", title="导出 HTML",  # type: ignore[attr-defined]
                            severity="error")
            return
        self.app.notify(f"已导出 {count} 题到 {path}",  # type: ignore[attr-defined]
                        title="导出 HTML")

    def _on_export_path(self, path: Optional[str]) -> None:
        """导出路径回调。"""
        if not path:
            return
        try:
            count = self.app.import_service.export_json_file(  # type: ignore[attr-defined]
                path, self._filtered)
        except OSError as exc:
            self.app.notify(f"导出失败: {exc}", title="导出",  # type: ignore[attr-defined]
                            severity="error")
            return
        self.app.notify(f"已导出 {count} 题到 {path}",  # type: ignore[attr-defined]
                        title="导出成功")

    @on(Button.Pressed, "#btn_chaoxing")
    def _open_chaoxing(self) -> None:
        """跳转到学习通拉取界面。"""
        self.app.push_screen("chaoxing")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_wrongbook")
    def _open_wrongbook(self) -> None:
        """打开错题管理弹窗(当前分类的错题记录)。

        「错题」虚拟分类显示跨分类聚合的全部错题;移除时按题目所属
        真实分类处理。
        """
        from quizforge.ui.screens.wrongbook_modal import WrongBookModal
        category_id = self._current_category()
        info = self.app.bank.get_category(category_id)  # type: ignore[attr-defined]
        name = info.name if info else DEFAULT_CATEGORY_NAME
        questions = self.app.bank.wrong_questions(category_id)  # type: ignore[attr-defined]
        self.app.push_screen(  # type: ignore[attr-defined]
            WrongBookModal(category_id, name, questions),
            self._on_wrongbook_closed)

    def _on_wrongbook_closed(self, _result: Optional[bool]) -> None:
        """错题管理关闭后刷新表格(错题标记可能变化)。"""
        self._refresh_table()

    @on(Button.Pressed, "#btn_back")
    def action_go_back(self) -> None:
        """返回主菜单。"""
        self.app.switch_screen("main")  # type: ignore[attr-defined]


def _truncate(text: str, length: int) -> str:
    """截断文本,超长时以省略号结尾。"""
    text = text.replace("\n", " ")
    return text if len(text) <= length else text[:length - 1] + "…"
