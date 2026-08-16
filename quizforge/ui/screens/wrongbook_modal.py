"""错题管理模态框:查看当前分类错题并手动移除。"""

from __future__ import annotations

from typing import List, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static


class WrongBookModal(ModalScreen[None]):
    """错题管理弹窗。

    列出指定分类错题记录中的题目摘要,支持:
        * 移除选中错题(答对/不再需要重练时手动移出);
        * 全部移除(清空该分类错题记录)。

    关闭时返回 None(不移除任何内容)。
    """

    def __init__(self, category_id: str, category_name: str,
                 questions: List[object]) -> None:
        """初始化错题管理弹窗。

        Args:
            category_id: 分类 id。
            category_name: 分类名称(仅展示)。
            questions: 该分类错题对应的题目对象列表。
        """
        super().__init__()
        self._category_id = category_id
        self._category_name = category_name
        self._questions = questions

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Center():
            with Middle():
                with Vertical(classes="modal-box"):
                    yield Static(
                        f"错题管理 [{self._category_name}]"
                        f" · {len(self._questions)} 题",
                        id="wrongbook_title", classes="title")
                    yield OptionList(id="wrongbook_list")
                    yield Static("选择一道错题后点[移除选中]",
                                 id="wrongbook_hint", classes="hint")
                    with Horizontal(classes="button-row"):
                        yield Button("移除选中", id="btn_remove_one",
                                     variant="primary", disabled=True)
                        yield Button("全部移除", id="btn_remove_all",
                                     variant="error")
                        yield Button("关闭", id="btn_close",
                                     variant="default")

    def on_mount(self) -> None:
        """挂载时填充错题列表。"""
        option_list = self.query_one("#wrongbook_list", OptionList)
        option_list.clear_options()
        for index, question in enumerate(self._questions, start=1):
            text = getattr(question, "text", "")
            text = str(text).replace("\n", " ")
            option_list.add_option(f"{index}. {_truncate(text, 40)}")

    @on(OptionList.OptionHighlighted, "#wrongbook_list")
    def _on_highlight(self) -> None:
        """高亮错题后启用移除按钮。"""
        self.query_one("#btn_remove_one", Button).disabled = False

    @on(Button.Pressed, "#btn_remove_one")
    def _remove_selected(self) -> None:
        """移除选中的错题。

        「错题」虚拟分类聚合跨分类题目,移除时按题目所属真实分类
        处理(调用方传入的 category_id 可能是虚拟分类)。
        """
        option_list = self.query_one("#wrongbook_list", OptionList)
        index = option_list.highlighted
        if index is None or not (0 <= index < len(self._questions)):
            return
        question = self._questions[index]
        bank = self.app.bank  # type: ignore[attr-defined]
        real_category = bank.find_category_of(question.id)
        if real_category is None:
            self.app.notify("题目已从题库删除,无法移除",  # type: ignore[attr-defined]
                            title="错题管理", severity="warning")
            return
        bank.remove_wrong(real_category, question.id)
        del self._questions[index]
        option_list.remove_option_at_index(index)
        self.query_one("#btn_remove_one", Button).disabled = True
        self.app.notify("已移出错题本", title="错题管理")  # type: ignore[attr-defined]
        self._update_title()
        if not self._questions:
            self.query_one("#wrongbook_hint", Static).update(
                "本分类错题已清空")

    def _update_title(self) -> None:
        """刷新标题中的错题数量。"""
        self.query_one("#wrongbook_title", Static).update(
            f"错题管理 [{self._category_name}]"
            f" · {len(self._questions)} 题")

    @on(Button.Pressed, "#btn_remove_all")
    def _remove_all(self) -> None:
        """清空错题记录(虚拟分类时逐题按真实分类清空)。"""
        if not self._questions:
            self.dismiss(None)
            return
        bank = self.app.bank  # type: ignore[attr-defined]
        for question in list(self._questions):
            real_category = bank.find_category_of(question.id)
            if real_category is not None:
                bank.remove_wrong(real_category, question.id)
        self.app.notify("已清空错题记录", title="错题管理")  # type: ignore[attr-defined]
        self.dismiss(None)

    @on(Button.Pressed, "#btn_close")
    def _close(self) -> None:
        """关闭弹窗。"""
        self.dismiss(None)


def _truncate(text: str, length: int) -> str:
    """截断文本,超长时以省略号结尾。"""
    text = text.replace("\n", " ")
    return text if len(text) <= length else text[:length - 1] + "…"
