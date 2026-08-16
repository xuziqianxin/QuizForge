"""历史作答详情模态框:按题展示某次作答的题干/选项/你的作答/正确答案。"""

from __future__ import annotations

from typing import Dict, List

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical, \
    VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static

#: 题目状态对应的标记与颜色。
_MARK = {
    True: ("[green]✓[/green]", "正确"),
    False: ("[red]✗[/red]", "错误"),
    None: ("[yellow]○[/yellow]", "未答"),
}


def _fmt_duration(seconds: int) -> str:
    """格式化用时。"""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class HistoryDetailModal(ModalScreen[None]):
    """历史作答详情弹窗。

    左侧为题目列表(带状态标记),右侧为选中题的详情(题干/选项/你的
    作答/正确答案/解析);底部可导出 HTML。
    """

    def __init__(self, record: Dict) -> None:
        """初始化详情弹窗。"""
        super().__init__()
        self._record = record
        self._index = 0

    def compose(self) -> ComposeResult:
        """构建界面。"""
        details: List[Dict] = self._record.get("details", [])
        with Center():
            with Middle():
                with Vertical(classes="modal-box"):
                    yield Static("", id="detail_title")
                    with Horizontal():
                        yield OptionList(id="detail_list")
                        with VerticalScroll(id="detail_body"):
                            yield Static("", id="detail_text")
                    with Horizontal(classes="button-row"):
                        yield Button("导出 HTML", id="btn_export",
                                     variant="primary")
                        yield Button("关闭", id="btn_close",
                                     variant="default")

    def on_mount(self) -> None:
        """挂载时渲染摘要、题目列表与第一题详情。"""
        record = self._record
        details: List[Dict] = record.get("details", [])
        score = record.get("auto_score", 0)
        total = record.get("auto_total", 0)
        self.query_one("#detail_title", Static).update(
            f"作答详情 [{record.get('category', '')}] "
            f"{score}/{total} · 用时 "
            f"{_fmt_duration(record.get('elapsed_seconds', 0))}")

        option_list = self.query_one("#detail_list", OptionList)
        option_list.clear_options()
        for index, detail in enumerate(details):
            mark, _ = _MARK.get(detail.get("is_correct"), _MARK[None])
            option_list.add_option(
                f"{mark} {index + 1}. {_one_line(detail.get('text', ''))}")
        self._render_detail(0)

    def _render_detail(self, index: int) -> None:
        """渲染第 index 题的详情。"""
        details: List[Dict] = self._record.get("details", [])
        if not details:
            self.query_one("#detail_text", Static).update(
                "(该记录没有逐题作答详情)")
            return
        self._index = min(index, len(details) - 1)
        detail = details[self._index]
        mark, status_text = _MARK.get(detail.get("is_correct"), _MARK[None])
        lines = [
            f"[bold]{mark} 第 {self._index + 1} 题 · "
            f"{detail.get('qtype_label', '')}({status_text})[/bold]",
            "",
            escape(detail.get("text", "")),
        ]
        options = detail.get("options") or []
        if options:
            lines.append("")
            lines.append("[bold]选项:[/bold]")
            for opt in options:
                lines.append(f"  {opt.get('key', '')}. "
                             f"{escape(opt.get('text', ''))}")
        lines.append("")
        lines.append(f"[bold]你的作答:[/bold] "
                     f"{escape(detail.get('user_answer', ''))}")
        if detail.get("correct_answer"):
            lines.append(f"[bold]正确答案:[/bold] "
                         f"{escape(detail.get('correct_answer', ''))}")
        if detail.get("analysis"):
            lines.append("")
            lines.append(f"[bold]解析:[/bold] "
                         f"{escape(detail.get('analysis', ''))}")
        self.query_one("#detail_text", Static).update("\n".join(lines))

    @on(OptionList.OptionSelected, "#detail_list")
    def _on_select(self, event: OptionList.OptionSelected) -> None:
        """跳转到选中的题目。"""
        self._render_detail(event.option_index)

    @on(Button.Pressed, "#btn_export")
    def _export(self) -> None:
        """导出这条作答记录为 HTML。"""
        from quizforge.ui.screens.modals import PromptModal
        default_name = f"history_{self._record.get('timestamp', '')[:19]}"
        default_name = default_name.replace(":", "").replace("T", "_")
        self.app.push_screen(  # type: ignore[attr-defined]
            PromptModal("导出作答记录 HTML",
                        "导出为 HTML 试卷(浏览器可查看/打印):",
                        value=f"data/{default_name}.html"),
            self._on_export_path)

    def _on_export_path(self, path: object) -> None:
        """导出路径回调。"""
        if not path:
            return
        try:
            from quizforge.services.html_exporter import export_record_html
            export_record_html(self._record, str(path))
        except OSError as exc:
            self.app.notify(f"导出失败: {exc}",  # type: ignore[attr-defined]
                            title="导出 HTML", severity="error")
            return
        self.app.notify(f"已导出到 {path}",  # type: ignore[attr-defined]
                        title="导出 HTML")

    @on(Button.Pressed, "#btn_close")
    def _close(self) -> None:
        """关闭弹窗。"""
        self.dismiss(None)


def _one_line(text: str, length: int = 26) -> str:
    """将文本压缩为单行摘要。"""
    text = str(text or "").replace("\n", " ")
    return text if len(text) <= length else text[:length - 1] + "…"
