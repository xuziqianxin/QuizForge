"""答题设置屏幕:选题方式(分类抽题 / 文件选题)、随机化开关与题目预览。"""

from __future__ import annotations

from typing import Dict, List, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (Button, Checkbox, ContentSwitcher, Input, Label,
                             Select, Static)

from quizforge.models import Question, QuestionType
from quizforge.services.bank_service import is_wrongbook_id
from quizforge.services.exam_service import (ExamConfig, ExamSession,
                                             draw_questions,
                                             load_questions_from_file)
from quizforge.ui.screens.draw_config_modal import DrawConfigModal
from quizforge.ui.screens.exam_screen import ExamScreen

#: 题目预览最多显示的条数。
_PREVIEW_LIMIT = 50


class ExamSetupScreen(Screen):
    """答题前的设置界面。

    两种选题方式:
        * 分类抽题:从所选分类中按"每种题型抽取数量"无放回随机抽题
          (数量超过该题型上限时自动修正为上限);可通过"抽题设置"
          配置数量,并使用已保存的配置模板。「错题」是一个虚拟分类,
          聚合各分类的错题,同样走分类抽题流程(答对自动移出错题);
        * 文件选题:通过文件(JSON id/题干列表或每行一个题干)指定
          要作答的题目。

    随机抽取使用系统熵,同一场考试内题目不会重复;随机打乱题目/选项
    顺序的开关默认跟随全局设置,可在此单独覆盖。
    """

    BINDINGS = [("escape", "go_back", "返回")]

    #: 选题方式 -> (中文名, 值)。
    MODES = [
        ("分类抽题(按题型数量)", "draw"),
        ("文件选题(指定题目)", "file"),
    ]

    def __init__(self) -> None:
        """初始化。"""
        super().__init__()
        self._category_id: str = "default"
        #: 分类抽题配置:题型 -> 抽取数量(None 表示尚未配置)。
        self._draw_specs: Optional[Dict[QuestionType, int]] = None
        #: 已抽中的题目(配置确认后立即抽取,预览与实际作答一致)。
        self._drawn_questions: List[Question] = []
        #: 文件选题结果。
        self._file_questions: List[Question] = []

    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        """构建界面。"""
        with Vertical():
            yield Static("开始答题", classes="title")
            yield Label("选题方式:")
            yield Select(
                [(name, value) for name, value in self.MODES],
                value="draw",
                id="setup_mode",
                allow_blank=False,
            )
            with ContentSwitcher(initial="view_draw", id="mode_switcher"):
                with Vertical(id="view_draw"):
                    yield Label("分类(抽题来源):")
                    yield Select([], id="setup_category",
                                 allow_blank=True, prompt="分类")
                    with Horizontal(id="draw_control_row"):
                        yield Button("抽题设置", id="btn_draw_config",
                                     variant="primary")
                        yield Static("", id="draw_summary")
                with Vertical(id="view_file"):
                    yield Label("题目文件(JSON 或每行一个题干):")
                    with Horizontal(id="file_control_row"):
                        yield Input("", id="setup_file",
                                    placeholder=r"data\exam_questions.json")
                        yield Button("读取", id="btn_load_file",
                                     variant="primary")
                    yield Static("", id="file_summary")
            yield Static("", id="setup_count")
            yield Label("所选题目预览:")
            with VerticalScroll(id="setup_preview"):
                yield Static("", id="setup_preview_text")
            yield Checkbox("随机打乱题目顺序", id="setup_shuffle_q")
            yield Checkbox("随机打乱选择题选项顺序", id="setup_shuffle_o")
            yield Checkbox("分类抽题时排除无答案题目",
                           id="setup_exclude_no_answer")
            with Horizontal(id="time_limit_row"):
                yield Label("限时模拟考试(分钟,0=不限时):")
                yield Input("", id="setup_time_limit",
                            placeholder="0")
            yield Static("限时模式倒计时显示,时间到自动交卷",
                         id="setup_time_limit_hint", classes="hint")
            yield Static("以上开关即时保存到全局设置",
                         id="setup_switch_hint")
            with Horizontal(classes="button-row"):
                yield Button("开始答题", id="btn_start", variant="success")
                yield Button("返回", id="btn_back", variant="default")

    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        """挂载时以全局设置初始化开关,并刷新分类与预览。

        若该分类保存过抽题配置(再答一次等场景),自动恢复并抽题,
        无需用户重新手动配置。
        """
        settings = self.app.config.settings  # type: ignore[attr-defined]
        self.query_one("#setup_shuffle_q", Checkbox).value = \
            settings.shuffle_questions
        self.query_one("#setup_shuffle_o", Checkbox).value = \
            settings.shuffle_options
        self.query_one("#setup_exclude_no_answer", Checkbox).value = \
            settings.exclude_no_answer
        time_limit = settings.time_limit_minutes
        self.query_one("#setup_time_limit", Input).value = \
            str(time_limit) if time_limit else "0"
        self._reload_categories()
        self._restore_cached_specs()

    # ------------------------------------------------------------------ #
    # 开关(即时保存到全局配置,答题设置与设置界面共用同一份设置)
    # ------------------------------------------------------------------ #
    @on(Checkbox.Changed, "#setup_shuffle_q")
    def _on_shuffle_q_changed(self) -> None:
        """随机题目顺序开关变化:即时保存到全局配置。"""
        try:
            self.app.config.update(  # type: ignore[attr-defined]
                shuffle_questions=self.query_one(
                    "#setup_shuffle_q", Checkbox).value)
        except OSError as exc:
            self.app.notify(f"保存设置失败: {exc}",  # type: ignore[attr-defined]
                            title="答题设置", severity="error")

    @on(Checkbox.Changed, "#setup_shuffle_o")
    def _on_shuffle_o_changed(self) -> None:
        """随机选项顺序开关变化:即时保存到全局配置。"""
        try:
            self.app.config.update(  # type: ignore[attr-defined]
                shuffle_options=self.query_one(
                    "#setup_shuffle_o", Checkbox).value)
        except OSError as exc:
            self.app.notify(f"保存设置失败: {exc}",  # type: ignore[attr-defined]
                            title="答题设置", severity="error")

    @on(Checkbox.Changed, "#setup_exclude_no_answer")
    def _on_exclude_no_answer_changed(self) -> None:
        """排除无答案题目开关变化:即时保存到全局配置并重抽。"""
        try:
            self.app.config.update(  # type: ignore[attr-defined]
                exclude_no_answer=self.query_one(
                    "#setup_exclude_no_answer", Checkbox).value)
        except OSError as exc:
            self.app.notify(f"保存设置失败: {exc}",  # type: ignore[attr-defined]
                            title="答题设置", severity="error")
            return
        # 开关影响抽题池:若已配置过抽题,重新抽取。
        if self._draw_specs is not None:
            try:
                self._drawn_questions = draw_questions(
                    self._draw_pool(), self._draw_specs)
            except KeyError:
                self._drawn_questions = []
            self._refresh_preview()

    @on(Input.Changed, "#setup_time_limit")
    def _on_time_limit_changed(self) -> None:
        """限时分钟数变化:即时保存到全局配置(非法输入按 0 处理)。"""
        raw = self.query_one("#setup_time_limit", Input).value.strip()
        try:
            minutes = max(0, int(raw))
        except ValueError:
            minutes = 0
        try:
            self.app.config.update(  # type: ignore[attr-defined]
                time_limit_minutes=minutes)
        except OSError as exc:
            self.app.notify(f"保存设置失败: {exc}",  # type: ignore[attr-defined]
                            title="答题设置", severity="error")

    def _draw_pool(self) -> List[Question]:
        """返回当前分类的抽题题目池。

        若全局设置开启「分类抽题时排除无答案题目」,则过滤掉未设置
        标准答案的题(如学习通导入的无答案题),避免抽到无法自动
        评分的题。
        """
        questions = self.app.bank.questions(  # type: ignore[attr-defined]
            self._category_id)
        if self.app.config.settings.exclude_no_answer:  # type: ignore[attr-defined]
            questions = [q for q in questions if q.answer]
        return questions

    def _restore_cached_specs(self) -> None:
        """恢复上次保存的抽题配置(按当前分类),并重新抽题预览。"""
        if self._draw_specs is not None:
            return
        cached = self.app.draw_specs_cache.get(self._category_id)  # type: ignore[attr-defined]
        if not cached:
            return
        specs = {QuestionType(key): int(value)
                 for key, value in cached.items()
                 if key in QuestionType.__members__.values()}
        if not specs:
            return
        self._draw_specs = specs
        try:
            self._drawn_questions = draw_questions(
                self._draw_pool(), specs)
        except KeyError:
            self._drawn_questions = []
        self._refresh_preview()

    def on_screen_resume(self, event) -> None:
        """回到本界面时刷新分类与预览(保留当前分类与抽题配置)。"""
        if self.is_mounted:
            self._reload_categories(auto_pick=False)

    # ------------------------------------------------------------------ #
    # 分类
    # ------------------------------------------------------------------ #
    def _reload_categories(self, auto_pick: bool = True) -> None:
        """刷新分类下拉列表(自动选择第一个非空分类)。"""
        categories = self.app.bank.list_categories()  # type: ignore[attr-defined]
        select = self.query_one("#setup_category", Select)
        select.set_options(
            [(f"{c.name}({c.count})", c.id) for c in categories])
        ids = [c.id for c in categories]
        if auto_pick:
            nonempty = [c.id for c in categories if c.count > 0]
            self._category_id = (
                nonempty[0] if nonempty else (ids[0] if ids else "default"))
        elif self._category_id not in ids:
            self._category_id = ids[0] if ids else "default"
        if self._category_id in ids:
            # 程序化设置分类值:屏蔽 Changed 事件,避免 resume 等场景
            # 误触发 _on_category_changed 而清空已配置的抽题结果。
            with select.prevent(Select.Changed):
                select.value = self._category_id
        self._refresh_preview()

    @on(Select.Changed, "#setup_mode")
    def _on_mode_changed(self) -> None:
        """选题方式切换。"""
        if self.is_mounted:
            mode = self.query_one("#setup_mode", Select).value
            self.query_one("#mode_switcher").current = (  # type: ignore[attr-defined]
                "view_draw" if mode == "draw" else "view_file")
            self._refresh_preview()

    @on(Select.Changed, "#setup_category")
    def _on_category_changed(self) -> None:
        """分类变化(用户手动切换)时刷新预览。

        分类变化后,旧的抽题配置与已抽题目失效,需重新配置;
        若分类值未变化(例如屏幕恢复时重复触发的事件),保留已有配置。
        """
        if not self.is_mounted:
            return
        value = self.query_one("#setup_category", Select).value
        if not value:
            return  # 空白选择:保留当前分类,避免 "None" 分类。
        new_id = str(value)
        if new_id == self._category_id and self._draw_specs is not None:
            return  # 值未变化且已配置,保留抽题结果。
        self._category_id = new_id
        self._draw_specs = None
        self._drawn_questions = []
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # 抽题配置
    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_draw_config")
    def _open_draw_config(self) -> None:
        """打开抽题设置(按题型配置抽取数量)。"""
        pool = self._draw_pool()
        limits: Dict[QuestionType, int] = {}
        for question in pool:
            limits[question.qtype] = limits.get(question.qtype, 0) + 1
        self.app.push_screen(  # type: ignore[attr-defined]
            DrawConfigModal(self._category_id, limits=limits),
            self._on_draw_config)

    # ------------------------------------------------------------------ #
    # 文件选题
    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_load_file")
    def _load_file(self) -> None:
        """读取题目文件。"""
        path = self.query_one("#setup_file", Input).value.strip()
        if not path:
            self.app.notify("请输入题目文件路径", title="文件选题",  # type: ignore[attr-defined]
                            severity="warning")
            return
        try:
            questions = load_questions_from_file(path, self.app.bank)  # type: ignore[attr-defined]
        except (ValueError, OSError) as exc:
            self.app.notify(str(exc), title="文件选题",  # type: ignore[attr-defined]
                            severity="error")
            return
        self._file_questions = questions
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # 预览
    # ------------------------------------------------------------------ #
    def _current_summary(self) -> tuple[str, int]:
        """返回 (摘要文本, 当前可答题数)。"""
        mode = self.query_one("#setup_mode", Select).value
        if mode == "file":
            count = len(self._file_questions)
            if not self._file_questions:
                return "请先输入题目文件路径并点击[读取]", 0
            return f"文件已读取 {count} 题", count
        # 分类抽题模式。
        if is_wrongbook_id(self._category_id):
            if not self._draw_specs:
                return ("错题分类:请点击[抽题设置]配置各题型的抽取数量"
                        "(答对自动移出错题)", 0)
            if not self._drawn_questions:
                return "错题抽题结果为空,请检查配置", 0
            return (f"已抽 {len(self._drawn_questions)} 题(错题,"
                    "答对自动移出)", len(self._drawn_questions))
        if not self._draw_specs:
            return "请点击[抽题设置]配置各题型的抽取数量", 0
        if not self._drawn_questions:
            return "抽题结果为空,请检查配置", 0
        return (f"已抽 {len(self._drawn_questions)} 题", 
                len(self._drawn_questions))

    def _wrongbook_questions(self) -> List[Question]:
        """返回当前「XX错题」虚拟分类的题目。"""
        return self.app.bank.questions(  # type: ignore[attr-defined]
            self._category_id)

    def _refresh_preview(self) -> None:
        """刷新题目数量、摘要与预览列表。"""
        mode = self.query_one("#setup_mode", Select).value
        summary, count = self._current_summary()
        self.query_one("#setup_count", Static).update(f"将答题 {count} 题")
        self.query_one("#btn_start", Button).disabled = (count == 0)
        if mode == "draw":
            self.query_one("#draw_summary", Static).update(summary)
        else:
            self.query_one("#file_summary", Static).update(summary)

        lines: List[str] = []
        if mode == "draw":
            # 抽题模式:展示已抽中的具体题目(预览与实际作答一致)。
            for index, question in enumerate(self._drawn_questions,
                                             start=1):
                if index > _PREVIEW_LIMIT:
                    break
                no_answer = " [dim][未设答案][/dim]" if not question.answer \
                    else ""
                lines.append(
                    f"{index}. [{question.qtype.label}] "
                    f"{_one_line(question.text, 40)}{no_answer}")
            if len(self._drawn_questions) > _PREVIEW_LIMIT:
                lines.append(
                    f"… 共 {len(self._drawn_questions)} 题,"
                    f"仅预览前 {_PREVIEW_LIMIT} 题")
        elif mode == "file" and self._file_questions:
            for index, question in enumerate(self._file_questions,
                                             start=1):
                if index > _PREVIEW_LIMIT:
                    break
                no_answer = " [dim][未设答案][/dim]" if not question.answer \
                    else ""
                lines.append(
                    f"{index}. [{question.qtype.label}] "
                    f"{_one_line(question.text, 40)}{no_answer}")
            if len(self._file_questions) > _PREVIEW_LIMIT:
                lines.append(
                    f"… 共 {len(self._file_questions)} 题,"
                    f"仅预览前 {_PREVIEW_LIMIT} 题")
        self.query_one("#setup_preview_text", Static).update(
            "\n".join(lines) if lines else "(尚未配置)")

    # ------------------------------------------------------------------ #
    @on(Button.Pressed, "#btn_start")
    def _start_exam(self) -> None:
        """开始答题(未配置抽题时强制弹出抽题设置)。"""
        mode = self.query_one("#setup_mode", Select).value
        if mode == "draw":
            if not self._drawn_questions:
                self.app.push_screen(  # type: ignore[attr-defined]
                    DrawConfigModal(self._category_id), self._on_draw_config)
                return
            # 使用已抽好的题目(与预览一致)。
            questions = self._drawn_questions
        else:
            if not self._file_questions:
                self.app.notify("请先读取题目文件",  # type: ignore[attr-defined]
                                title="无法开始", severity="warning")
                return
            questions = self._file_questions
        self._begin(questions)

    def _on_draw_config(self,
                        specs: Optional[Dict[QuestionType, int]]) -> None:
        """抽题设置回调:保存配置、立即抽题并预览具体题目。

        抽题结果保存在 ``_drawn_questions``,预览区展示具体题目,
        "开始答题"时直接使用这批题目(预览与实际作答一致)。

        配置同时写入应用级缓存,再答一次时自动恢复(直到用户修改)。
        """
        if not specs:
            return
        self._draw_specs = specs
        # 缓存当前分类的抽题配置,供"再答一次"等场景复用。
        self.app.draw_specs_cache[self._category_id] = {  # type: ignore[attr-defined]
            qtype.value: count for qtype, count in specs.items()}
        try:
            self._drawn_questions = draw_questions(
                self._draw_pool(), specs)
        except KeyError:
            self.app.notify("分类不存在,请重新选择",  # type: ignore[attr-defined]
                            title="抽题设置", severity="warning")
            self._drawn_questions = []
            return
        self._refresh_preview()

    def _begin(self, questions: List[Question]) -> None:
        """创建答题会话并进入答题界面。

        使用全新 ExamScreen 实例(不走实例缓存),避免上一场作答的
        状态(题号/作答)残留。当抽题来源是「错题」虚拟分类时,会话
        标记为错题重练模式(答对自动移出错题索引)。
        """
        raw_limit = self.query_one("#setup_time_limit", Input).value.strip()
        try:
            time_limit_seconds = max(0, int(raw_limit)) * 60
        except ValueError:
            time_limit_seconds = 0
        config = ExamConfig(
            question_ids=[q.id for q in questions],
            shuffle_questions=self.query_one(
                "#setup_shuffle_q", Checkbox).value,
            shuffle_options=self.query_one(
                "#setup_shuffle_o", Checkbox).value,
            mode=("wrongbook" if is_wrongbook_id(self._category_id)
                  else "exam"),
            time_limit_seconds=time_limit_seconds,
            category_id=("" if self._category_id in ("", "file")
                         else self._category_id),
        )
        session: ExamSession = self.app.exam_service.create_session(  # type: ignore[attr-defined]
            questions, config)
        self.app.exam_session = session  # type: ignore[attr-defined]
        self.app.exam_result = None  # type: ignore[attr-defined]
        self.app.exam_questions = questions  # type: ignore[attr-defined]
        self.app.push_screen(ExamScreen())  # type: ignore[attr-defined]

    @on(Button.Pressed, "#btn_back")
    def action_go_back(self) -> None:
        """返回主菜单。"""
        self.app.switch_screen("main")  # type: ignore[attr-defined]


def _one_line(text: str, length: int = 40) -> str:
    """将文本压缩为单行摘要。"""
    text = text.replace("\n", " ")
    return text if len(text) <= length else text[:length - 1] + "…"
