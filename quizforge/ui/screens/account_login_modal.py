"""账号密码登录模态框。"""

from __future__ import annotations

from typing import Optional, Tuple

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class AccountLoginModal(ModalScreen[Optional[Tuple[str, str]]]):
    """学习通账号密码登录对话框,返回 (手机号, 密码);取消返回 None。"""

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Center():
            with Middle():
                with Vertical(classes="modal-box"):
                    yield Static("学习通账号登录", classes="title")
                    yield Static(
                        "使用手机号/学号与密码登录(密码仅在本次请求中使用,\n"
                        "不会保存;登录状态以 Cookie 形式持久化)。",
                        id="modal_message")
                    yield Input(placeholder="手机号 / 学号",
                                id="login_phone")
                    yield Input(placeholder="密码", id="login_password",
                                password=True)
                    with Horizontal(classes="button-row"):
                        yield Button("登录", id="btn_login",
                                     variant="primary")
                        yield Button("取消", id="btn_cancel",
                                     variant="default")

    def on_mount(self) -> None:
        """挂载后聚焦账号输入框。"""
        self.query_one("#login_phone", Input).focus()

    def _submit(self) -> None:
        """收集输入并关闭对话框。"""
        phone = self.query_one("#login_phone", Input).value.strip()
        password = self.query_one("#login_password", Input).value
        if not phone or not password:
            self.app.notify("请输入账号和密码", title="登录",  # type: ignore[attr-defined]
                            severity="warning")
            return
        self.dismiss((phone, password))

    @on(Button.Pressed, "#btn_login")
    def _on_login(self) -> None:
        """点击登录。"""
        self._submit()

    @on(Button.Pressed, "#btn_cancel")
    def _on_cancel(self) -> None:
        """点击取消。"""
        self.dismiss(None)

    @on(Input.Submitted, "#login_password")
    def _on_password_submit(self) -> None:
        """密码框回车视为提交。"""
        self._submit()
