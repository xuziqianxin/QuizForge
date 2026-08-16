"""抽题配置模态框。

按题型设置抽取数量,支持:
    * 每种题型一个数字输入框(仅允许数字,自动去除空格/非法字符),
      实时显示该分类的最大可用数;
    * 输入超过最大值时自动修正为最大值,并在输入框中同步显示;
    * 抽题配置模板:选择已保存模板一键填充,可保存当前配置为新模板、
      删除模板。

关闭时返回 ``{题型: 抽取数量}``(数量大于 0 的题型);取消返回 None。
"""

from __future__ import annotations

from typing import Dict, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical, \
    VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from quizforge.models import QuestionType
from quizforge.ui.screens.modals import PromptModal


class DrawConfigModal(ModalScreen[Optional[Dict[QuestionType, int]]]):
    """抽题设置对话框。"""

    def __init__(self, category_id: str,
                 limits: Optional[Dict[QuestionType, int]] = None) -> None:
        """初始化。

        Args:
            category_id: 当前分类(用于加载抽题模板等)。
            limits: 各题型最大可用题数。由调用方传入(可能已按"排除
                无答案题"开关过滤);为 None 时按分类实际题数计算。
        """
        super().__init__()
        self._category_id = category_id
        #: 题型 -> 该分类最大可用题数。
        self._limits: Dict[QuestionType, int] = (
            dict(limits) if limits is not None else {})

    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        """构建界面(题型数量两列布局;按钮行固定底部,内容超高仅滚动
        配置区,保证"开始抽题"在任何窗口高度都可见可点)。"""
        types = list(QuestionType)
        with Center():
            with Middle():
                with Vertical(classes="modal-box", id="draw_outer"):
                    with VerticalScroll(id="draw_scroll"):
                        yield Static("抽题设置(按题型设置抽取数量)",
                                     classes="title")
                        yield Static("", id="draw_hint")
                        # 题型数量:两列排布(3 行 × 2 列,容下 5 种题型)。
                        for row in range(3):
                            with Horizontal(classes="draw-row"):
                                for qtype in types[row * 2: row * 2 + 2]:
                                    key = qtype.value  # id 不允许句点
                                    yield Label(qtype.label,
                                                id=f"label_{key}")
                                    yield Input("0", id=f"draw_{key}",
                                                type="integer")
                                    yield Static("", id=f"limit_{key}",
                                                 classes="draw-limit")
                        yield Label("配置模板:")
                        with Horizontal(id="draw_template_row"):
                            yield Select([], id="draw_template",
                                         allow_blank=True, prompt="选择模板")
                            yield Button("保存为模板", id="btn_save_tpl")
                            yield Button("删除模板", id="btn_del_tpl")
                    # 按钮行固定在底部,不随配置区滚动。
                    with Horizontal(classes="button-row"):
                        yield Button("开始抽题", id="btn_draw",
                                     variant="success")
                        yield Button("取消", id="btn_cancel",
                                     variant="default")

    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        """挂载时加载该分类的题型上限与已有模板。

        分类可能已被外部删除,加载失败时给出提示并关闭,避免崩溃。
        """
        if not self._limits:
            # 调用方未提供上限时按分类实际题数计算。
            try:
                self._limits = self.app.bank.count_by_type(  # type: ignore[attr-defined]
                    self._category_id)
            except KeyError:
                self.app.notify("分类不存在,请重新选择",  # type: ignore[attr-defined]
                                title="抽题设置", severity="error")
                self.dismiss(None)
                return
        self.query_one("#draw_hint", Static).update(
            f"可抽取上限: 单选 {self._limits.get(QuestionType.SINGLE, 0)} · "
            f"多选 {self._limits.get(QuestionType.MULTIPLE, 0)} · "
            f"判断 {self._limits.get(QuestionType.JUDGE, 0)} · "
            f"填空 {self._limits.get(QuestionType.FILL, 0)} · "
            f"简答 {self._limits.get(QuestionType.SHORT, 0)}")
        for qtype in QuestionType:
            limit = self._limits.get(qtype, 0)
            self.query_one(f"#limit_{qtype.value}", Static).update(
                f"/ {limit}" if limit else "(-)")
        self._reload_templates()

    def _reload_templates(self) -> None:
        """刷新模板下拉列表。"""
        templates = self.app.templates.list_templates()  # type: ignore[attr-defined]
        select = self.query_one("#draw_template", Select)
        select.set_options([(name, name) for name in templates])

    def _current_specs(self) -> Dict[QuestionType, int]:
        """读取当前各题型输入的数量(已修正到上限内)。"""
        specs: Dict[QuestionType, int] = {}
        for qtype in QuestionType:
            raw = self.query_one(f"#draw_{qtype.value}",
                                 Input).value.strip()
            try:
                value = int(raw)
            except ValueError:
                value = 0
            limit = self._limits.get(qtype, 0)
            value = max(0, min(value, limit))
            specs[qtype] = value
        return specs

    def _apply_specs(self, specs: Dict[QuestionType, int]) -> None:
        """将配置写入各题型输入框。"""
        for qtype in QuestionType:
            self.query_one(f"#draw_{qtype.value}", Input).value = \
                str(specs.get(qtype, 0))

    # ------------------------------------------------------------------ #
    # 数量输入:仅数字;超过上限自动修正(输入框同步显示修正值)。
    # ------------------------------------------------------------------ #
    @on(Input.Changed)
    def _on_count_changed(self, event: Input.Changed) -> None:
        """数量输入变化时校验。

        仅在真正超上限(或非法数值)时才改写输入框,避免打断正常输入
        (如前导零、中间输入过程)。
        """
        input_id = event.input.id or ""
        if not input_id.startswith("draw_"):
            return
        qtype = QuestionType(input_id.removeprefix("draw_"))
        limit = self._limits.get(qtype, 0)
        raw = event.input.value.strip()
        try:
            value = int(raw)
        except ValueError:
            value = 0
        corrected = max(0, min(value, limit))
        if corrected != value:
            # 超上限/非法:自动修正为最大值(需求行为)。
            event.input.value = str(corrected)

    # ------------------------------------------------------------------ #
    # 模板操作
    # ------------------------------------------------------------------ #
    @on(Select.Changed, "#draw_template")
    def _on_template_selected(self) -> None:
        """选中模板后填充各题型数量。"""
        select = self.query_one("#draw_template", Select)
        name = select.value
        if not name:
            return
        templates = self.app.templates.list_templates()  # type: ignore[attr-defined]
        specs = templates.get(str(name))
        if specs:
            typed = {QuestionType(key): int(value)
                     for key, value in specs.items()
                     if key in QuestionType.__members__.values()}
            self._apply_specs(typed)

    @on(Button.Pressed, "#btn_save_tpl")
    def _save_template(self) -> None:
        """将当前配置保存为模板。"""
        self.app.push_screen(  # type: ignore[attr-defined]
            PromptModal("保存配置模板", "输入模板名称(同名覆盖):",
                        placeholder="例如: 单元小测"),
            self._on_template_name)

    def _on_template_name(self, name: Optional[str]) -> None:
        """模板名称回调。"""
        if not name:
            return
        specs = self._current_specs()
        self.app.templates.save_template(  # type: ignore[attr-defined]
            name, {qtype.value: count for qtype, count in specs.items()})
        self.app.notify(f"模板 [{name}] 已保存",  # type: ignore[attr-defined]
                        title="抽题设置")
        self._reload_templates()
        self.query_one("#draw_template", Select).value = name

    @on(Button.Pressed, "#btn_del_tpl")
    def _delete_template(self) -> None:
        """删除当前选中的模板。"""
        select = self.query_one("#draw_template", Select)
        name = select.value
        if not name:
            return
        self.app.templates.delete_template(str(name))  # type: ignore[attr-defined]
        self.app.notify(f"模板 [{name}] 已删除",  # type: ignore[attr-defined]
                        title="抽题设置")
        self._reload_templates()

    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_draw")
    def _confirm(self) -> None:
        """确认抽题配置。"""
        specs = {qtype: count for qtype, count in self._current_specs().items()
                 if count > 0}
        if not specs:
            self.app.notify("请至少为一种题型设置抽取数量",  # type: ignore[attr-defined]
                            title="抽题设置", severity="warning")
            return
        self.dismiss(specs)

    @on(Button.Pressed, "#btn_cancel")
    def _cancel(self) -> None:
        """取消。"""
        self.dismiss(None)
