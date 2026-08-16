"""通用模态框:确认对话框与文本输入对话框。"""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class ConfirmModal(ModalScreen[bool]):
    """确认对话框,返回 True(确认)或 False(取消)。"""

    def __init__(self,
                 title: str,
                 message: str,
                 yes_label: str = "确定",
                 no_label: str = "取消") -> None:
        """初始化确认框。

        Args:
            title: 标题。
            message: 提示内容。
            yes_label: 确认按钮文字。
            no_label: 取消按钮文字。
        """
        super().__init__()
        self._title = title
        self._message = message
        self._yes_label = yes_label
        self._no_label = no_label

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Center():
            with Middle():
                with Vertical(classes="modal-box"):
                    yield Static(self._title, classes="title")
                    yield Static(self._message, id="modal_message")
                    with Horizontal(classes="button-row"):
                        yield Button(self._yes_label, id="btn_yes",
                                     variant="primary")
                        yield Button(self._no_label, id="btn_no",
                                     variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理按钮点击。"""
        if event.button.id == "btn_yes":
            self.dismiss(True)
        elif event.button.id == "btn_no":
            self.dismiss(False)


class PromptModal(ModalScreen[Optional[str]]):
    """文本输入对话框,返回输入内容;取消时返回 None。"""

    def __init__(self,
                 title: str,
                 prompt: str,
                 value: str = "",
                 placeholder: str = "") -> None:
        """初始化输入框。

        Args:
            title: 标题。
            prompt: 输入说明。
            value: 初始值。
            placeholder: 占位提示。
        """
        super().__init__()
        self._title = title
        self._prompt = prompt
        self._value = value
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Center():
            with Middle():
                with Vertical(classes="modal-box"):
                    yield Static(self._title, classes="title")
                    yield Static(self._prompt, id="modal_message")
                    yield Input(value=self._value,
                                placeholder=self._placeholder,
                                id="prompt_input")
                    with Horizontal(classes="button-row"):
                        yield Button("确定", id="btn_ok", variant="primary")
                        yield Button("取消", id="btn_cancel", variant="default")

    def on_mount(self) -> None:
        """挂载后聚焦输入框。"""
        self.query_one("#prompt_input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理按钮点击。"""
        if event.button.id == "btn_ok":
            self.dismiss(self.query_one("#prompt_input", Input).value.strip())
        elif event.button.id == "btn_cancel":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """回车视为确定。"""
        self.dismiss(event.value.strip())
