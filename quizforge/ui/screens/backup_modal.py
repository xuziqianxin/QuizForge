"""备份恢复模态框:列出 data/backup/ 全部备份,选中一份并确认后还原。"""

from __future__ import annotations

from typing import List, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static

from quizforge.storage import BackupEntry, list_backups, restore_backup


def _format_ts(timestamp: str) -> str:
    """将备份时间戳(YYYYmmdd_HHMMSSffffff)格式化为可读时间。"""
    try:
        date_part, time_part = timestamp.split("_", 1)
        return (f"{date_part[0:4]}-{date_part[4:6]}-{date_part[6:8]} "
                f"{time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}")
    except (ValueError, IndexError):
        return timestamp


def _fmt_size(size: int) -> str:
    """格式化文件大小。"""
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


class BackupRestoreModal(ModalScreen[None]):
    """备份恢复弹窗。

    列出数据目录全部备份文件(按原文件名分组,显示备份时间与大小),
    选中一份后点「恢复选中」,二次确认后还原到其目标位置;恢复前会
    自动备份当前文件。关闭时返回 None。
    """

    def __init__(self, data_dir: str) -> None:
        """初始化备份恢复弹窗。

        Args:
            data_dir: 数据根目录。
        """
        super().__init__()
        self._data_dir = data_dir
        self._entries: List[BackupEntry] = []

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Center():
            with Middle():
                with Vertical(classes="modal-box"):
                    yield Static("从备份恢复", classes="title")
                    yield Static("", id="backup_hint", classes="hint")
                    yield OptionList(id="backup_list")
                    yield Static("选择一份备份后点[恢复选中]",
                                 id="backup_tip", classes="hint")
                    with Horizontal(classes="button-row"):
                        yield Button("恢复选中", id="btn_restore",
                                     variant="primary", disabled=True)
                        yield Button("关闭", id="btn_close",
                                     variant="default")

    def on_mount(self) -> None:
        """挂载时列出全部备份。"""
        self._entries = list_backups(self._data_dir)
        option_list = self.query_one("#backup_list", OptionList)
        option_list.clear_options()
        # 按原文件名 + 时间升序展示。
        for entry in self._entries:
            option_list.add_option(
                f"{entry.original_name}  "
                f"[{_format_ts(entry.timestamp)}] {_fmt_size(entry.size)}")
        if not self._entries:
            self.query_one("#backup_hint", Static).update(
                "(data/backup/ 下暂无备份)")
            self.query_one("#btn_restore", Button).disabled = True
        else:
            self.query_one("#backup_hint", Static).update(
                f"共 {len(self._entries)} 份备份,恢复前会自动备份当前文件")

    @on(OptionList.OptionHighlighted, "#backup_list")
    def _on_highlight(self) -> None:
        """高亮备份后启用恢复按钮。"""
        self.query_one("#btn_restore", Button).disabled = False

    @on(Button.Pressed, "#btn_restore")
    def _restore(self) -> None:
        """恢复选中的备份(带二次确认)。"""
        option_list = self.query_one("#backup_list", OptionList)
        index = option_list.highlighted
        if index is None or not (0 <= index < len(self._entries)):
            return
        entry = self._entries[index]
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmBackupModal(entry, self._data_dir),
            self._on_restore_done)

    def _on_restore_done(self, restored: Optional[bool]) -> None:
        """恢复完成回调。"""
        if restored:
            self.dismiss(None)

    @on(Button.Pressed, "#btn_close")
    def _close(self) -> None:
        """关闭弹窗。"""
        self.dismiss(None)


class ConfirmBackupModal(ModalScreen[bool]):
    """恢复确认弹窗:展示备份信息,确认后执行恢复。"""

    def __init__(self, entry: BackupEntry, data_dir: str) -> None:
        """初始化确认弹窗。"""
        super().__init__()
        self._entry = entry
        self._data_dir = data_dir

    def compose(self) -> ComposeResult:
        """构建界面。"""
        entry = self._entry
        with Center():
            with Middle():
                with Vertical(classes="modal-box"):
                    yield Static("恢复确认", classes="title")
                    yield Static(
                        f"将用以下备份覆盖当前文件:\n\n"
                        f"  文件: {entry.original_name}\n"
                        f"  备份时间: {_format_ts(entry.timestamp)}\n"
                        f"  大小: {_fmt_size(entry.size)}\n\n"
                        f"恢复前会自动备份当前文件(可在备份列表中找回),\n"
                        f"确定恢复吗?",
                        id="confirm_message")
                    with Horizontal(classes="button-row"):
                        yield Button("恢复", id="btn_yes",
                                     variant="primary")
                        yield Button("取消", id="btn_no",
                                     variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理按钮点击。"""
        if event.button.id == "btn_yes":
            try:
                restore_backup(self._entry, self._data_dir)
            except Exception as exc:  # noqa: BLE001 兜底:任何异常都不卡死弹窗
                import traceback as _tb
                _tb.print_exc()
                self.app.notify(f"恢复失败: {exc}",  # type: ignore[attr-defined]
                                title="备份恢复", severity="error")
                self.dismiss(False)
                return
            self.app.notify(  # type: ignore[attr-defined]
                f"已从备份恢复 {self._entry.original_name}",
                title="备份恢复")
            self.dismiss(True)
        elif event.button.id == "btn_no":
            self.dismiss(False)
