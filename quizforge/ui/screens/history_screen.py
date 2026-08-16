"""历史成绩屏幕:按时间倒序查看答题记录,支持删除与清空。"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static

from quizforge.ui.screens.modals import ConfirmModal

#: 单页显示条数。
_PAGE_SIZE = 50


def _format_ts(iso_ts: str) -> str:
    """将 ISO 时间戳格式化为可读时间(去掉秒后精度)。"""
    try:
        return iso_ts.replace("T", " ")[:19]
    except (ValueError, IndexError):
        return iso_ts


def _fmt_duration(seconds: int) -> str:
    """格式化用时为 MM:SS / H:MM:SS。"""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class HistoryScreen(Screen):
    """历史成绩界面。

    展示每次答题的时间、来源、得分、正确率、用时与题型分布;选中一条
    可删除,支持一键清空。记录按时间倒序(最新在前)。
    """

    BINDINGS = [("escape", "go_back", "返回")]

    def __init__(self) -> None:
        """初始化历史成绩界面。"""
        super().__init__()
        self._page: int = 0
        self._records: List[dict] = []

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Vertical():
            yield Static("历史成绩", classes="title")
            yield Static("", id="history_summary")
            yield DataTable(id="history_table", cursor_type="row",
                            zebra_stripes=True)
            with Horizontal(id="history_pager"):
                yield Button("◀ 上一页", id="btn_prev_page",
                             variant="default", disabled=True)
                yield Static("", id="history_page_info")
                yield Button("下一页 ▶", id="btn_next_page",
                             variant="default", disabled=True)
            with Horizontal(classes="button-row"):
                yield Button("查看作答", id="btn_detail",
                             variant="primary", disabled=True)
                yield Button("导出 HTML", id="btn_export",
                             variant="default", disabled=True)
                yield Button("删除选中", id="btn_delete",
                             variant="error", disabled=True)
                yield Button("清空全部", id="btn_clear",
                             variant="error")
                yield Button("返回", id="btn_back", variant="default")

    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        """挂载时初始化表格。"""
        table = self.query_one("#history_table", DataTable)
        table.add_column("时间", key="time", width=19)
        table.add_column("来源", key="source", width=12)
        table.add_column("得分", key="score", width=10)
        table.add_column("正确率", key="rate", width=8)
        table.add_column("用时", key="duration", width=9)
        table.add_column("题型分布", key="types", width=38)
        self._refresh_table()

    def on_screen_resume(self, event) -> None:
        """每次成为当前屏幕时刷新(可能新增了记录)。"""
        if self.is_mounted:
            self._refresh_table()

    # ------------------------------------------------------------------ #
    def _refresh_table(self) -> None:
        """按页码刷新表格。"""
        self._records = self.app.history.list_records()  # type: ignore[attr-defined]
        total_pages = max(1, -(-len(self._records) // _PAGE_SIZE))
        self._page = min(self._page, total_pages - 1)
        self._page = max(0, self._page)
        page_records = self._records[
            self._page * _PAGE_SIZE:(self._page + 1) * _PAGE_SIZE]

        table = self.query_one("#history_table", DataTable)
        table.clear()
        for record in page_records:
            score = record.get("auto_score", 0)
            total = record.get("auto_total", 0)
            rate = (f"{score * 100 // total}%" if total
                    else "-")
            types = _format_types(record.get("type_distribution", {}))
            table.add_row(
                _format_ts(record.get("timestamp", "")),
                Text(str(record.get("category", "")), style="bold"),
                Text(f"{score} / {total}"),
                Text(rate),
                _fmt_duration(record.get("elapsed_seconds", 0)),
                Text(types),
                key=record.get("timestamp", ""),
            )
        self.query_one("#history_summary", Static).update(
            f"共 {len(self._records)} 次答题记录")
        self.query_one("#history_page_info", Static).update(
            f"第 {self._page + 1} / {total_pages} 页"
            f" · 本页 {len(page_records)} 条")
        self.query_one("#btn_prev_page", Button).disabled = (self._page == 0)
        self.query_one("#btn_next_page", Button).disabled = \
            (self._page >= total_pages - 1)
        self.query_one("#btn_delete", Button).disabled = True
        self.query_one("#btn_detail", Button).disabled = True
        self.query_one("#btn_export", Button).disabled = True

    def _selected_record(self) -> Optional[dict]:
        """返回当前高亮行对应的记录。"""
        table = self.query_one("#history_table", DataTable)
        if table.cursor_row is None:
            return None
        keys = list(table.rows.keys())
        if not (0 <= table.cursor_row < len(keys)):
            return None
        timestamp = str(keys[table.cursor_row].value)
        for record in self._records:
            if record.get("timestamp") == timestamp:
                return record
        return None

    # ------------------------------------------------------------------ #
    @on(DataTable.RowHighlighted, "#history_table")
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """高亮记录后启用操作按钮。"""
        self.query_one("#btn_delete", Button).disabled = False
        self.query_one("#btn_detail", Button).disabled = False
        self.query_one("#btn_export", Button).disabled = False

    @on(Button.Pressed, "#btn_detail")
    def _show_detail(self) -> None:
        """查看选中的作答详情。"""
        record = self._selected_record()
        if record is None:
            return
        from quizforge.ui.screens.history_detail_modal import \
            HistoryDetailModal
        self.app.push_screen(HistoryDetailModal(record))  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_export")
    def _export_html(self) -> None:
        """把选中的作答记录导出为 HTML 试卷。"""
        record = self._selected_record()
        if record is None:
            return
        from quizforge.ui.screens.modals import PromptModal
        default_name = f"history_{record.get('timestamp', 'record')[:19]}"
        default_name = default_name.replace(":", "").replace("T", "_")
        self.app.push_screen(  # type: ignore[attr-defined]
            PromptModal("导出作答记录 HTML",
                        "把这条作答记录导出为 HTML 试卷\n"
                        "(浏览器打开后可查看/打印)。\n"
                        "请输入输出文件路径:",
                        value=f"data/{default_name}.html"),
            lambda path: self._on_export_path(record, path))

    def _on_export_path(self, record: Optional[dict],
                        path: Optional[str]) -> None:
        """导出路径回调。"""
        if not path or record is None:
            return
        try:
            from quizforge.services.html_exporter import export_record_html
            export_record_html(record, path)
        except OSError as exc:
            self.app.notify(f"导出失败: {exc}",  # type: ignore[attr-defined]
                            title="导出 HTML", severity="error")
            return
        self.app.notify(f"已导出到 {path}",  # type: ignore[attr-defined]
                        title="导出 HTML")

    @on(Button.Pressed, "#btn_prev_page")
    def _prev_page(self) -> None:
        """上一页。"""
        if self._page > 0:
            self._page -= 1
            self._refresh_table()

    @on(Button.Pressed, "#btn_next_page")
    def _next_page(self) -> None:
        """下一页。"""
        total_pages = max(1, -(-len(self._records) // _PAGE_SIZE))
        if self._page < total_pages - 1:
            self._page += 1
            self._refresh_table()

    @on(Button.Pressed, "#btn_delete")
    def _delete_selected(self) -> None:
        """删除选中的历史记录(带确认)。"""
        table = self.query_one("#history_table", DataTable)
        row_key = table.cursor_row if table.cursor_row is not None else None
        if row_key is None:
            return
        keys = list(table.rows.keys())
        if not (0 <= row_key < len(keys)):
            return
        timestamp = str(keys[row_key].value)
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmModal("删除记录", "确定删除这条历史成绩吗?"),
            lambda confirmed: self._on_delete_confirmed(
                confirmed, timestamp))

    def _on_delete_confirmed(self, confirmed: Optional[bool],
                             timestamp: str) -> None:
        """删除确认回调。"""
        if confirmed:
            self.app.history.remove(timestamp)  # type: ignore[attr-defined]
            self._refresh_table()
            self.app.notify("记录已删除", title="历史成绩")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_clear")
    def _clear_all(self) -> None:
        """清空全部历史(带确认)。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmModal("清空历史",
                         f"确定清空全部 {len(self._records)} 条历史成绩吗?",
                         yes_label="清空", no_label="取消"),
            self._on_clear_confirmed)

    def _on_clear_confirmed(self, confirmed: Optional[bool]) -> None:
        """清空确认回调。"""
        if confirmed:
            self.app.history.clear()  # type: ignore[attr-defined]
            self._refresh_table()
            self.app.notify("历史成绩已清空", title="历史成绩")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_back")
    def action_go_back(self) -> None:
        """返回设置界面。"""
        self.app.switch_screen("settings")  # type: ignore[attr-defined]


def _format_types(type_dist: dict) -> str:
    """将题型分布 {题型值: 数量} 格式化为可读文本。"""
    from quizforge.models import QuestionType
    parts = []
    for qtype in QuestionType:
        count = type_dist.get(qtype.value, 0)
        if count:
            parts.append(f"{qtype.label}{count}")
    return " ".join(parts) if parts else "-"
