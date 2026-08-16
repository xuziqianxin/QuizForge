"""答题卡模态框:展示作答情况并支持跳转。

使用 DataTable 展示(题号 / 状态 / 所选答案),自适应宽度、题目多时可
滚动,高亮行即跳转对应题目。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static


class AnswerSheetModal(ModalScreen[Optional[int]]):
    """答题卡。

    每行一题:未作答显示"未答";已作答的选择题显示所选答案字母,
    填空/简答题显示"已答"。高亮某行即跳转到对应题目。
    """

    def __init__(self, items: List[Tuple[int, str, List[str]]],
                 total: int) -> None:
        """初始化答题卡。

        Args:
            items: 每题信息列表,元素为 (题号下标, 题目id, 已作答键列表)。
            total: 题目总数。
        """
        super().__init__()
        self._items = items
        self._total = total
        #: 跳转是否已启用(挂载期间 DataTable 初始化光标会触发
        #: RowHighlighted,必须忽略,否则 modal 刚打开就被关闭)。
        self._jumps_enabled = False

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Center():
            with Middle():
                with Vertical(classes="modal-box"):
                    yield Static(
                        f"答题卡(共 {self._total} 题) — "
                        "已作答的选择题显示所选答案,高亮行可跳转",
                        id="sheet_title")
                    yield DataTable(id="sheet_table", cursor_type="row",
                                    zebra_stripes=True)
                    with Vertical(classes="button-row"):
                        yield Button("关闭", id="btn_close", variant="primary")

    def on_mount(self) -> None:
        """挂载时填充表格,并在稳定后启用跳转。"""
        table = self.query_one("#sheet_table", DataTable)
        table.add_column("题号", key="index", width=6)
        table.add_column("状态", key="status", width=8)
        table.add_column("所选答案", key="answer", width=24)
        for index, _, keys in self._items:
            if keys:
                if _is_choice_keys(keys):
                    status, answer = "已答", "".join(keys)
                else:
                    status, answer = "已答", "已答"
            else:
                status, answer = "未答", ""
            table.add_row(str(index + 1), status, answer, key=str(index))
        # 挂载期间的光标初始化事件被忽略,稍后启用跳转。
        self.set_timer(0.1, self._enable_jumps)

    def _enable_jumps(self) -> None:
        """启用行高亮跳转。"""
        self._jumps_enabled = True

    # ------------------------------------------------------------------ #
    @on(DataTable.RowHighlighted, "#sheet_table")
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """高亮行即跳转到对应题目(挂载稳定后才生效)。"""
        if not self._jumps_enabled:
            return
        self.dismiss(int(str(event.row_key.value)))

    @on(Button.Pressed, "#btn_close")
    def _close(self) -> None:
        """关闭答题卡。"""
        self.dismiss(None)


def _is_choice_keys(keys: List[str]) -> bool:
    """判断作答键是否为字母形式(选择题)。"""
    return all(len(key) == 1 and key.isalpha() for key in keys)
