"""
Textual 界面组件：主菜单、分类管理、答题、搜索等屏幕。
"""
import os
from typing import List, Dict, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button, Footer, Header, Input, Label, ListItem, ListView,
    Static, Switch, TextArea, Checkbox
)
from textual.containers import Center
from textual.binding import Binding
from textual import events

from bank_manager import BankManager
from quiz_session import QuizSession
from search_engine import SearchEngine


# ---------------------------- 列表项 ----------------------------
class CategoryListItem(ListItem):
    """分类列表项，携带分类名称。"""
    def __init__(self, category: str) -> None:
        super().__init__()
        self.category = category

    def compose(self) -> ComposeResult:
        yield Label(self.category)


class BankFileListItem(ListItem):
    """题库文件列表项，携带分类和文件名。"""
    def __init__(self, category: str, filename: str) -> None:
        super().__init__()
        self.category = category
        self.filename = filename

    def compose(self) -> ComposeResult:
        yield Label(f"{self.filename}.json")


class SearchResultItem(ListItem):
    """搜索结果项，直接接收标签文本和结果数据"""
    def __init__(self, label_text: str, cat: str, fname: str, q: dict) -> None:
        self._label = Label(label_text)
        super().__init__(self._label)
        self.result_data = (cat, fname, q)


# ---------------------------- 主菜单 ----------------------------
class MainMenuScreen(Screen):
    """主菜单：使用 ListView 实现可交互选项，无需底部快捷键栏。"""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Label("题库管理与答题系统", id="title"),
            ListView(
                ListItem(Label("📁 分类管理")),
                ListItem(Label("📝 答题模式")),
                ListItem(Label("🔍 题目搜索")),
                ListItem(Label("🚪 退出系统")),
                id="main-menu-list",
            ),
            id="main-menu-container",
        )
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """根据用户选择的列表项导航到对应屏幕。"""
        index = self.query_one("#main-menu-list", ListView).index
        if index == 0:
            self.app.push_screen(CategoryTreeScreen())
        elif index == 1:
            self.app.push_screen(QuizCategoryScreen())
        elif index == 2:
            self.app.push_screen(SearchScreen())
        elif index == 3:
            self.app.exit()

# ---------------------------- 分类管理 ----------------------------
# ---------- 树节点项（分类/文件） ----------
class TreeNode(ListItem):
    """树形列表项：可表示分类（可折叠）或题库文件"""
    def __init__(self, label_text: str, node_type: str, data=None):
        super().__init__()
        self.node_type = node_type          # "category" 或 "file"
        self.data = data                    # category name 或 (category, filename)
        self.expanded = False               # 分类专用，是否展开
        self.depth = 0                      # 缩进级别
        # 显示文字
        self.label = Label(label_text)
        self.add(self.label)                # 添加到 ListItem

    def toggle_expand(self):
        self.expanded = not self.expanded

    def update_label(self, text: str):
        self.label.update(text)


# ---------- 文件树主屏幕 ----------
class TreeNode(ListItem):
    def __init__(self, label_text: str, node_type: str, data=None):
        self._label = Label(label_text)
        super().__init__(self._label)
        self.node_type = node_type
        self.data = data
        self.expanded = False

    def update_label(self, text: str):
        self._label.update(text)


class CategoryTreeScreen(Screen):
    BINDINGS = [
        Binding("i", "import_html", "导入HTML"),
        Binding("n", "new_category", "新建分类"),
        Binding("d", "delete", "删除选中"),
        Binding("r", "refresh", "刷新"),
        Binding("escape", "back", "返回"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Horizontal(
            Container(
                Static("[bold]题库分类[/bold]", classes="panel-title"),
                ListView(id="tree-list"),
                id="left-panel",
            ),
            Container(
                Static("[bold]题目预览[/bold]", classes="panel-title"),
                TextArea(id="preview-area", read_only=True, language="json"),
                id="right-panel",
            ),
            id="tree-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._build_tree()

    def _build_tree(self) -> None:
        tree = self.query_one("#tree-list", ListView)
        tree.clear()
        for cat in BankManager.list_categories():
            cat_node = TreeNode(f"📁 {cat}", "category", cat)
            tree.append(cat_node)
            files = BankManager.list_bank_files(cat)
            for fname in files:
                file_node = TreeNode(f"  📄 {fname}.json", "file", (cat, fname))
                file_node.display = False         # 初始隐藏
                tree.append(file_node)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if not isinstance(item, TreeNode):
            return
        if item.node_type == "category":
            self._toggle_category(item)
        elif item.node_type == "file":
            cat, fname = item.data
            self._preview_file(cat, fname)

    def _toggle_category(self, cat_node: TreeNode) -> None:
        cat = cat_node.data
        tree = self.query_one("#tree-list", ListView)
        idx = tree.children.index(cat_node)
        i = idx + 1
        show = not cat_node.expanded               # 切换后是否显示
        while i < len(tree.children):
            child = tree.children[i]
            if isinstance(child, TreeNode) and child.node_type == "file" and child.data[0] == cat:
                child.display = show
                i += 1
            elif isinstance(child, TreeNode) and child.node_type == "category":
                break
            else:
                i += 1
        cat_node.expanded = show
        icon = "📂" if cat_node.expanded else "📁"
        cat_node.update_label(f"{icon} {cat}")

    def _preview_file(self, cat: str, fname: str) -> None:
        questions = BankManager.load_bank(cat, fname)
        preview = self.query_one("#preview-area", TextArea)
        lines = []
        for i, q in enumerate(questions):
            lines.append(f"【{i+1}】{q['type']} {q['number']}")
            lines.append(f"  题目：{q['question']}")
            if q['options']:
                lines.append("  选项：")
                for opt in q['options']:
                    lines.append(f"    {opt}")
            lines.append(f"  答案：{q.get('correct_answer', '未设置')}")
            lines.append("")
        preview.clear()
        preview.insert("\n".join(lines))

    # ---------- 功能操作 ----------
    def action_import_html(self) -> None:
        self.app.push_screen(
            InputDialog("请输入HTML文件或文件夹路径："),
            callback=self._import_html
        )

    def _import_html(self, path: str | None) -> None:
        if not path:
            return
        mgr = BankManager()
        item = self._get_selected_item()
        if item and item.node_type == "category":
            target_cat = item.data
        else:
            self.notify("请先选中一个分类", severity="warning")
            return
        existing = set(BankManager.list_bank_files(target_cat))
        if os.path.isfile(path):
            success, count, fname, _ = mgr.import_html_file(target_cat, path, existing)
            if success:
                self.notify(f"导入成功：{fname}.json ({count}题)")
            else:
                self.notify("导入失败", severity="error")
        else:
            mgr.import_from_folder(target_cat, path)
            self.notify("批量导入完成")
        self.action_refresh()

    def action_new_category(self) -> None:
        self.app.push_screen(
            InputDialog("请输入新分类名称："),
            callback=self._create_category
        )

    def _create_category(self, name: str | None) -> None:
        if name:
            BankManager.create_category(name)
            self.action_refresh()

    def action_delete(self) -> None:
        item = self._get_selected_item()
        if not item:
            return
        if item.node_type == "category":
            self.app.push_screen(
                ConfirmDialog(f"删除分类“{item.data}”及其所有文件？"),
                callback=lambda ok: self._delete_category(item.data) if ok else None
            )
        elif item.node_type == "file":
            cat, fname = item.data
            self.app.push_screen(
                ConfirmDialog(f"删除文件“{fname}.json”？"),
                callback=lambda ok: self._delete_file(cat, fname) if ok else None
            )

    def _delete_category(self, cat: str) -> None:
        BankManager.delete_category(cat)
        self.action_refresh()

    def _delete_file(self, cat: str, fname: str) -> None:
        BankManager.delete_bank(cat, fname)
        self.action_refresh()
        self.query_one("#preview-area", TextArea).clear()

    def action_refresh(self) -> None:
        self._build_tree()
        self.query_one("#preview-area", TextArea).clear()

    def _get_selected_item(self) -> TreeNode | None:
        list_view = self.query_one("#tree-list", ListView)
        if list_view.index is not None:
            item = list_view.children[list_view.index]
            if isinstance(item, TreeNode):
                return item
        return None
        
    def action_back(self) -> None:
        self.app.pop_screen()
        

# ---------------------------- 答题模块 ----------------------------
# ---------- 答题模块：选择分类 ----------
class QuizCategoryScreen(Screen):
    BINDINGS = [("escape", "back", "返回")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Label("选择分类", id="title"),
            ListView(id="category-quiz-list"),
            Static("Enter: 选择分类", id="help"),
            id="quiz-category-screen",
        )
        yield Footer()

    def on_mount(self) -> None:
        list_view = self.query_one("#category-quiz-list", ListView)
        for cat in BankManager.list_categories():
            total = sum(len(BankManager.load_bank(cat, f)) for f in BankManager.list_bank_files(cat))
            list_view.append(ListItem(Label(f"{cat} ({total} 题)"), name=cat))

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.name:
            self.app.push_screen(QuizFileSelectScreen(event.item.name))


# ---------- 答题模块：选择题库文件 ----------
class QuizFileSelectScreen(Screen):
    """选择题库：顶部栏 + 左侧多选列表 + 右侧摘要 + Footer 操作键"""
    BINDINGS = [
        Binding("t", "toggle_shuffle", "打乱顺序"),
        Binding("space", "toggle_selection", "选择/取消"),
        Binding("a", "select_all", "全选"),
        Binding("Enter", "start_quiz", "开始答题"),
        Binding("escape", "back", "返回"),
    ]

    def __init__(self, category: str) -> None:
        super().__init__()
        self.category = category
        self.shuffle_on = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Horizontal(
            Static(f"分类：{self.category}", id="category-label"),
            Static("☐ 随机打乱选项顺序", id="shuffle-indicator"),
            id="top-bar",
        )
        yield Horizontal(
            Container(
                Static("[bold]题库文件[/bold]", classes="panel-title"),
                ListView(id="file-quiz-list"),
                Static("Space: 选择/取消 | A: 全选", id="list-hint"),
                id="left-panel",
            ),
            Container(
                Static("[bold]已选题库[/bold]", classes="panel-title"),
                Static("尚未选择任何题库", id="summary-text"),
                Static("", id="start-prompt"),
                id="right-panel",
            ),
            id="quiz-select-body",
        )
        yield Footer()

    def on_mount(self) -> None:
        list_view = self.query_one("#file-quiz-list", ListView)
        for fname in BankManager.list_bank_files(self.category):
            qs = BankManager.load_bank(self.category, fname)
            list_view.append(ListItem(Label(f"☐ {fname}.json（{len(qs)}题）"), name=fname))
        self._refresh_summary()
        list_view.focus()
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_start_quiz()
    # ---------- 动作实现 ----------
    def action_back(self) -> None:
        self.app.pop_screen()

    def action_toggle_shuffle(self) -> None:
        self.shuffle_on = not self.shuffle_on
        indicator = self.query_one("#shuffle-indicator", Static)
        indicator.update("☑ 随机打乱选项顺序" if self.shuffle_on else "☐ 随机打乱选项顺序")

    def action_toggle_selection(self) -> None:
        """Space 键：切换当前高亮项的选中状态"""
        list_view = self.query_one("#file-quiz-list", ListView)
        if list_view.index is not None:
            item = list_view.children[list_view.index]
            item.toggle_class("selected")
            self._update_marking(item)
            self._refresh_summary()

    def action_select_all(self) -> None:
        """A 键：全选所有文件"""
        list_view = self.query_one("#file-quiz-list", ListView)
        for item in list_view.children:
            item.add_class("selected")
            self._update_marking(item)
        self._refresh_summary()

    def action_start_quiz(self) -> None:
        """Enter 键：开始答题"""
        list_view = self.query_one("#file-quiz-list", ListView)
        selected = [item.name for item in list_view.children if item.has_class("selected")]
        if not selected:
            self.notify("请至少选择一个题库文件", severity="warning")
            return
        questions = []
        for fname in selected:
            questions.extend(BankManager.load_bank(self.category, fname))
        self.app.push_screen(QuizScreen(self.category, questions, self.shuffle_on))

    # ---------- 辅助方法 ----------
    def _update_marking(self, item: ListItem) -> None:
        name = item.name
        qs = BankManager.load_bank(self.category, name)
        label = item.query_one(Label)
        if item.has_class("selected"):
            label.update(f"☑ {name}.json（{len(qs)}题）")
        else:
            label.update(f"☐ {name}.json（{len(qs)}题）")

    def _refresh_summary(self) -> None:
        list_view = self.query_one("#file-quiz-list", ListView)
        selected_items = [it for it in list_view.children if it.has_class("selected")]
        summary = self.query_one("#summary-text", Static)
        prompt = self.query_one("#start-prompt", Static)

        if not selected_items:
            summary.update("尚未选择任何题库")
            prompt.update("[italic]请先选择题库文件[/italic]")
            return

        lines = []
        total_q = 0
        for it in selected_items:
            fname = it.name
            qs = BankManager.load_bank(self.category, fname)
            cnt = len(qs)
            lines.append(f"• {fname}.json（{cnt}题）")
            total_q += cnt
        lines.append("")
        lines.append(f"[bold]总计：{len(selected_items)} 个题库，{total_q} 道题目[/bold]")
        summary.update("\n".join(lines))
        prompt.update(f"[bold green]按 Enter 开始答题（共 {total_q} 题）[/bold green]")

# ---------- 答题核心屏幕 ----------
class QuizScreen(Screen):
    BINDINGS = [
        Binding("j", "jump", "跳转到第N题"),
        Binding("l", "list_answers", "查看已答题目"),
        Binding("s", "submit", "提交答卷"),
        Binding("q", "quit_quiz", "退出答题", show=False),
    ]

    session: QuizSession
    current_idx: int = 0
    jump_back_idx: Optional[int] = None
    multi_select: bool = False
    selected_options: set = set()

    def __init__(self, category: str, questions: List[Dict], shuffle_options: bool) -> None:
        super().__init__()
        self.session = QuizSession(questions, shuffle_options=shuffle_options)
        self.category = category

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static(id="progress"),
            Static(id="question-text"),
            ListView(id="options-list"),
            Static(id="answer-status"),
            Static(id="help-text"),
            id="quiz-area",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.show_question(self.current_idx)

    # ------------------------------------------------------------
    def show_question(self, idx: int) -> None:
        self.current_idx = idx
        self.selected_options.clear()

        if 0 <= idx < self.session.total:
            q = self.session.order[idx]
            self.multi_select = q.get('type', '') in ('多选题', '不定项选择题')

            self.query_one("#progress", Static).update(f"第 {idx+1}/{self.session.total} 题")
            self.query_one("#question-text", Static).update(f"[{q['type']}] {q['question']}")

            options_list = self.query_one("#options-list", ListView)
            options_list.clear()
            for i, opt in enumerate(q['options']):
                prefix = "☐ " if self.multi_select else ""
                options_list.append(ListItem(Label(f"{prefix}{opt}")))   # 无 id

            ans = self.session.answers.get(q['id'])
            status = f"已存答案: {ans}" if ans else ""
            self.query_one("#answer-status", Static).update(status)

            hint = "Space: 选择/取消 | Enter: 确认答案 | J/L/S 同左" if self.multi_select else "↑↓ 选择 | Enter: 确认答案 | J/L/S 同左"
            self.query_one("#help-text", Static).update(hint)
        else:
            self.query_one("#progress", Static).update("所有题目已完成！")
            self.query_one("#options-list", ListView).clear()
            self.query_one("#question-text", Static).update("")
            self.query_one("#answer-status", Static).update("")
            self.query_one("#help-text", Static).update("按 S 提交答卷")

    # ---------- 多选切换 ----------
    def on_key(self, event: events.Key) -> None:
        if event.key == "space" and self.multi_select:
            self._toggle_option()
            event.prevent_default()
            event.stop()

    def _toggle_option(self) -> None:
        list_view = self.query_one("#options-list", ListView)
        if list_view.index is None:
            return
        idx = list_view.index
        if idx in self.selected_options:
            self.selected_options.remove(idx)
        else:
            self.selected_options.add(idx)
        self._update_option_mark(idx)

    def _update_option_mark(self, idx: int) -> None:
        """根据 selected_options 更新第 idx 个选项前面的 ☐/☑"""
        q = self.session.order[self.current_idx]
        list_view = self.query_one("#options-list", ListView)
        if idx < 0 or idx >= len(list_view.children):
            return
        item = list_view.children[idx]
        label = item.query_one(Label)
        opt_text = q['options'][idx]
        if self.multi_select:
            mark = "☑ " if idx in self.selected_options else "☐ "
            label.update(f"{mark}{opt_text}")
        else:
            label.update(opt_text)

    # ---------- 确认答案（Enter 键） ----------
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        q = self.session.order[self.current_idx]
        list_view = self.query_one("#options-list", ListView)
        idx = list_view.index
        if idx is None:
            return

        if self.multi_select:
            if idx not in self.selected_options:
                self.selected_options.add(idx)
                self._update_option_mark(idx)
            sorted_indices = sorted(self.selected_options)
            answer = ''.join(chr(ord('A') + i) for i in sorted_indices)
        else:
            answer = chr(ord('A') + idx)

        self.session.record_answer(q['id'], answer)
        self.notify(f"已记录答案: {answer}", timeout=0.5)

        if not self.session.is_all_answered():
            next_idx = self.session.find_next_unanswered_index(self.current_idx)
            if next_idx is not None:
                self.show_question(next_idx)
            else:
                self.show_question(self.current_idx)
        else:
            self.show_question(self.current_idx)

    # ---------- 其他行动（不变） ----------
    def action_jump(self) -> None:
        self.app.push_screen(
            InputDialog(f"跳转到第几题？(1-{self.session.total})"),
            callback=self._do_jump
        )

    def _do_jump(self, text: Optional[str]) -> None:
        if text and text.isdigit():
            target = int(text) - 1
            if 0 <= target < self.session.total:
                self.jump_back_idx = self.current_idx
                self.show_question(target)

    def action_list_answers(self) -> None:
        self.app.push_screen(AnsweredListScreen(self.session))

    def action_submit(self) -> None:
        missing = self.session.get_missing_count()
        if missing > 0:
            self.app.push_screen(
                ConfirmDialog(f"还有 {missing} 题未答，确定提交吗？"),
                callback=lambda ok: self._submit() if ok else None
            )
        else:
            self._submit()

    def _submit(self) -> None:
        self.app.pop_screen()
        self.app.push_screen(ResultScreen(self.session))

    def action_quit_quiz(self) -> None:
        self.app.pop_screen()

# ---------- 已答题目列表 ----------
class AnsweredListScreen(Screen):
    BINDINGS = [("escape", "back", "返回")]

    def __init__(self, session: QuizSession) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ScrollableContainer(
            Static("已作答题目列表：", id="title"),
            *[
                Static(
                    f"[{seq:>3}] 题号 {q['number']} ({q['type']}): {self.session.answers.get(q['id'], '')}"
                )
                for seq, q in enumerate(self.session.order, 1)
                if q['id'] in self.session.answers
            ],
            id="answered-container",
        )
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()


# ---------- 答题结果与复盘 ----------
class ResultScreen(Screen):
    BINDINGS = [
        Binding("d", "details", "查看详情"),
        Binding("escape", "back", "返回"),
    ]

    def __init__(self, session: QuizSession) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        correct_count, percent, user_ans_list, correct_ans_list = self.session.compute_score()
        total = self.session.total

        # 纯文本答案（用于计算宽度）和样式版本
        plain_user = []
        plain_correct = []
        styled_user = []
        styled_correct = []

        for i, q in enumerate(self.session.order):
            ua = user_ans_list[i]
            ca = correct_ans_list[i]
            plain_user.append(ua)
            plain_correct.append(ca)
            if ua != ca:
                styled_user.append(f"[reverse red bold]{ua}[/]")
                styled_correct.append(f"[reverse red bold]{ca}[/]")
            else:
                styled_user.append(ua)
                styled_correct.append(ca)

        # 计算每列最大宽度（基于纯文本）
        max_len = 0
        for s in plain_user + plain_correct:
            if len(s) > max_len:
                max_len = len(s)

        col_width = max_len + 1  # 至少间隔一个空格

        def fmt_row(answers: List[str], plain: List[str], label: str) -> str:
            """生成对齐的答案行，每行10个"""
            rows = [answers[i:i+10] for i in range(0, len(answers), 10)]
            plain_rows = [plain[i:i+10] for i in range(0, len(plain), 10)]
            text = f"{label}:\n"
            for r, pr in zip(rows, plain_rows):
                line = ""
                for styled, p in zip(r, pr):
                    # 用纯文本长度计算需要补充的空格
                    padding = col_width - len(p)
                    line += styled + ' ' * padding
                text += line.rstrip() + "\n"
            return text

        user_display = fmt_row(styled_user, plain_user, "你的答案")
        correct_display = fmt_row(styled_correct, plain_correct, "正确答案")

        yield Header(show_clock=True)
        yield Container(
            Static(f"得分: {correct_count}/{self.session.total} (正确率: {percent:.1f}%)", id="title"),
            Static(user_display),
            Static(correct_display),
            Static("D: 查看详情 | ESC: 返回", id="help"),
            id="result-screen",
        )
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_details(self) -> None:
        self.app.push_screen(ReviewScreen(self.session))


class ReviewScreen(Screen):
    BINDINGS = [
        Binding("n", "next", "下一题"),
        Binding("p", "previous", "上一题"),
        Binding("j", "jump", "跳转"),
        Binding("escape", "back", "返回"),
    ]

    session: QuizSession
    idx: int = 0

    def __init__(self, session: QuizSession) -> None:
        super().__init__()
        self.session = session
        self.idx = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static(id="review-progress"),
            Static(id="review-question"),
            Static(id="review-options"),
            Static(id="review-answer"),
            Static("N:下一题 | P:上一题 | J:跳转 | ESC:返回", id="review-help"),
            id="review-screen",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.update_display()

    def action_back(self) -> None:
        self.app.pop_screen()

    def update_display(self) -> None:
        q = self.session.order[self.idx]
        user_ans = self.session.answers.get(q['id'], "未作答")
        correct_ans = q['correct_answer'].upper() if q['correct_answer'] else "未设置"
        is_correct = (user_ans == correct_ans)
        self.query_one("#review-progress", Static).update(f"第 {self.idx+1}/{self.session.total} 题")
        self.query_one("#review-question", Static).update(f"[{q['type']}] {q['question']}")
        self.query_one("#review-options", Static).update("\n".join(q['options']))
        self.query_one("#review-answer", Static).update(
            f"你的答案: {user_ans}\n正确答案: {correct_ans}\n结果: {'✓ 正确' if is_correct else '✗ 错误'}"
        )

    def action_next(self) -> None:
        if self.idx < self.session.total - 1:
            self.idx += 1
            self.update_display()

    def action_previous(self) -> None:
        if self.idx > 0:
            self.idx -= 1
            self.update_display()

    def action_jump(self) -> None:
        self.app.push_screen(
            InputDialog(f"跳转到第几题？(1-{self.session.total})"),
            callback=self._jump
        )

    def _jump(self, text: Optional[str]) -> None:
        if text and text.isdigit():
            target = int(text) - 1
            if 0 <= target < self.session.total:
                self.idx = target
                self.update_display()


# ---------------------------- 题目搜索 ----------------------------
class SearchScreen(Screen):
    BINDINGS = [("escape", "back", "返回")]

    def __init__(self):
        super().__init__()
        self.results = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # 顶部搜索输入
        yield Container(
            Label("题目搜索", id="title"),
            Input(placeholder="请输入搜索关键词...", id="search-input"),
            id="search-top",
        )
        # 主体双栏
        yield Horizontal(
            Container(
                Static("[bold]搜索结果[/bold]", classes="panel-title"),
                ListView(id="search-results"),
                Static("Enter: 查看详情 | ESC: 返回", id="search-hint"),
                id="left-panel",
            ),
            Container(
                Static("[bold]题目预览[/bold]", classes="panel-title"),
                TextArea(id="preview-area", read_only=True, language="json"),
                id="right-panel",
            ),
            id="search-body",
        )
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        keyword = event.value.strip()
        if not keyword:
            return
        self.results = SearchEngine.search_internal(keyword)
        list_view = self.query_one("#search-results", ListView)
        list_view.clear()
        for cat, fname, q in self.results:
            label_text = f"[{cat}] {fname}.json | {q['number']} | {q['question'][:40]}..."
            item = SearchResultItem(label_text, cat, fname, q)
            list_view.mount(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, SearchResultItem) and event.item.result_data:
            cat, fname, q = event.item.result_data
            self._show_preview(cat, fname, q)

    def _show_preview(self, cat: str, fname: str, q: dict) -> None:
        preview = self.query_one("#preview-area", TextArea)
        lines = [
            f"分类: {cat}  文件: {fname}.json",
            f"题号: {q.get('number', '?')}  类型: {q.get('type', '?')}",
            "",
            f"题目: {q.get('question', '')}",
            "",
            "选项:",
        ]
        for opt in q.get('options', []):
            lines.append(f"  {opt}")
        lines.append("")
        lines.append(f"正确答案: {q.get('correct_answer', '未设置')}")
        preview.clear()
        preview.insert("\n".join(lines))


# ---------------------------- 通用对话框 ----------------------------
class InputDialog(ModalScreen):
    BINDINGS = [("escape", "dismiss")]

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        yield Container(
            Label(self.prompt),
            Input(id="dialog-input"),
            Center(
                Button("确定", variant="primary", id="ok")
            ),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            value = self.query_one("#dialog-input", Input).value
            self.dismiss(value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class ConfirmDialog(ModalScreen):
    BINDINGS = [("escape", "dismiss")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        yield Container(
            Label(self.message),
            Center(
                Horizontal(
                    Button("是", variant="primary", id="yes"),
                    Button("否", variant="default", id="no"),
                    id="confirm-buttons"
                )
            ),
            id="confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)