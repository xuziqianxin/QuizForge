"""设置屏幕:学习通登录管理、数据概况。

答题相关开关(随机题目/随机选项/排除无答案)已移至**答题设置界面**
(见 exam_setup_screen.py),在那里即改即存到全局配置,本界面不再
重复提供,避免两处状态不一致。
"""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from quizforge.ui.screens.modals import ConfirmModal


class SettingsScreen(Screen):
    """设置界面。

    提供:
        * 学习通登录状态查看与清除;
        * 当前数据存储概况(分类/模板/配置文件等,与实际结构一致);
        * 当前全局开关状态一览(修改请到答题设置界面)。
    """

    BINDINGS = [("escape", "go_back", "返回")]

    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Vertical():
            yield Static("设置", classes="title")

            yield Static("学习通", classes="section-title")
            with Horizontal(id="cx_status_row"):
                yield Label("登录状态:", id="cx_status_label")
                yield Button("清除登录", id="btn_logout_cx",
                             variant="error", disabled=True)

            yield Static("答题选项(修改请到答题设置)", classes="section-title")
            yield Static("", id="settings_switches")

            yield Static("数据概况", classes="section-title")
            yield Static("", id="settings_info")
            with Horizontal(classes="button-row"):
                yield Button("历史成绩", id="btn_history",
                             variant="default")
                yield Button("备份恢复", id="btn_backup_restore",
                             variant="default")
                yield Button("返回", id="btn_back", variant="default")

    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        """挂载时刷新状态与数据概况。"""
        self._refresh_status()

    def on_screen_resume(self, event) -> None:
        """回到设置界面时刷新状态与数据概况(分类/模板可能已变化)。"""
        if self.is_mounted:
            self._refresh_status()

    # ------------------------------------------------------------------ #
    def _refresh_status(self) -> None:
        """刷新学习通登录状态、开关状态与数据概况。"""
        chaoxing = self.app.chaoxing  # type: ignore[attr-defined]
        if chaoxing.is_logged_in:
            uid = chaoxing.session.cookies.get("_uid") or \
                chaoxing.session.cookies.get("UID") or "?"
            self.query_one("#cx_status_label", Label).update(
                f"已登录 (uid {uid})")
            self.query_one("#btn_logout_cx", Button).disabled = False
        else:
            self.query_one("#cx_status_label", Label).update("未登录")
            self.query_one("#btn_logout_cx", Button).disabled = True

        settings = self.app.config.settings  # type: ignore[attr-defined]
        self.query_one("#settings_switches", Static).update(
            f"随机打乱题目顺序: {'开' if settings.shuffle_questions else '关'}\n"
            f"随机打乱选项顺序: {'开' if settings.shuffle_options else '关'}\n"
            f"排除无答案题目: {'开' if settings.exclude_no_answer else '关'}\n"
            f"限时模拟考试: "
            f"{settings.time_limit_minutes} 分钟"
            f"{'(0=不限时)' if settings.time_limit_minutes == 0 else '到点自动交卷'}\n"
            f"(以上在「开始答题 -> 答题设置」中修改,即改即存)")

        config = self.app.config  # type: ignore[attr-defined]
        from quizforge.services.bank_service import is_wrongbook_id
        categories = self.app.bank.list_categories()  # type: ignore[attr-defined]
        real = [c for c in categories if not is_wrongbook_id(c.id)]
        total = sum(c.count for c in real)
        templates = self.app.templates.list_templates()  # type: ignore[attr-defined]
        store = self.app.bank.store  # type: ignore[attr-defined]
        info = (
            f"数据目录: {config.data_dir}\n"
            f"分类存储: {store.bank_dir}\n"
            f"  {len(real)} 个分类 · 共 {total} 题\n"
            f"抽题模板: {len(templates)} 个\n"
            f"配置文件: {config.config_path}\n"
            f"学习通登录态: {config.settings.chaoxing_cookie_file}")
        self.query_one("#settings_info", Static).update(info)

    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_logout_cx")
    def _logout_chaoxing(self) -> None:
        """清除学习通登录状态(需确认)。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            ConfirmModal("清除学习通登录",
                         "将清除本机的学习通登录状态,确定吗?",
                         yes_label="清除", no_label="取消"),
            self._on_logout_confirmed)

    def _on_logout_confirmed(self, confirmed: Optional[bool]) -> None:
        """清除登录确认回调。"""
        if confirmed:
            self.app.chaoxing.logout()  # type: ignore[attr-defined]
            self._refresh_status()
            self.app.notify("已清除学习通登录状态",  # type: ignore[attr-defined]
                            title="设置")

    @on(Button.Pressed, "#btn_history")
    def _open_history(self) -> None:
        """打开历史成绩界面。"""
        self.app.push_screen("history")  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_backup_restore")
    def _open_backup_restore(self) -> None:
        """打开备份恢复弹窗(列出 data/backup/ 全部备份)。"""
        from quizforge.ui.screens.backup_modal import BackupRestoreModal
        self.app.push_screen(  # type: ignore[attr-defined]
            BackupRestoreModal(self.app.data_dir),  # type: ignore[attr-defined]
            self._on_backup_restore_done)

    def _on_backup_restore_done(self, _result: Optional[bool]) -> None:
        """备份恢复完成后刷新数据概况(分类/模板可能已变化)。"""
        self._refresh_status()
        self.app.notify("若恢复了题库/配置,已自动重载",  # type: ignore[attr-defined]
                        title="备份恢复", severity="information")

    @on(Button.Pressed, "#btn_back")
    def action_go_back(self) -> None:
        """返回主菜单(开关已在答题设置即时保存,无需确认)。"""
        self.app.switch_screen("main")  # type: ignore[attr-defined]
