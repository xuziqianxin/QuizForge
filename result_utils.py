"""答题结果格式化工具，提供对齐和高亮显示。"""
from typing import List
from config import ITEMS_PER_ROW, RICH_WRONG_STYLE


def build_aligned_answers(user_answers: List[str],
                          correct_answers: List[str],
                          order_questions: List[dict]) -> Tuple[str, str]:
    """
    根据用户答案和正确答案生成带 Rich 标记的对齐文本。
    错误答案用 reverse red bold 高亮。
    返回 (用户答案文本, 正确答案文本) 元组。
    """
    plain_user = []
    plain_correct = []
    styled_user = []
    styled_correct = []

    for i, q in enumerate(order_questions):
        ua = user_answers[i] if i < len(user_answers) else "未作答"
        ca = correct_answers[i] if i < len(correct_answers) else "未设置"
        plain_user.append(ua)
        plain_correct.append(ca)
        if ua != ca:
            styled_user.append(f"[{RICH_WRONG_STYLE}]{ua}[/]")
            styled_correct.append(f"[{RICH_WRONG_STYLE}]{ca}[/]")
        else:
            styled_user.append(ua)
            styled_correct.append(ca)

    # 计算最大文本长度
    max_len = max((len(s) for s in plain_user + plain_correct), default=0)
    col_width = max_len + 1  # 至少间隔一个空格

    def _fmt_row(styled: List[str], plain: List[str], label: str) -> str:
        """将答案列表格式化为每行 ITEMS_PER_ROW 个的对齐文本。"""
        rows = [styled[i:i + ITEMS_PER_ROW] for i in range(0, len(styled), ITEMS_PER_ROW)]
        plain_rows = [plain[i:i + ITEMS_PER_ROW] for i in range(0, len(plain), ITEMS_PER_ROW)]
        text = f"{label}:\n"
        for styled_row, plain_row in zip(rows, plain_rows):
            line = ""
            for s, p in zip(styled_row, plain_row):
                padding = col_width - len(p)
                line += s + ' ' * padding
            text += line.rstrip() + "\n"
        return text

    user_text = _fmt_row(styled_user, plain_user, "你的答案")
    correct_text = _fmt_row(styled_correct, plain_correct, "正确答案")
    return user_text, correct_text