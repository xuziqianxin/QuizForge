"""HTML 试卷导出。

提供两类导出(输出完整 HTML 文档,浏览器可直接打开、打印为 PDF):

    * 历史作答记录导出(``export_record_html``):按记录中的逐题详情
      渲染题干/选项/你的作答/正确答案/解析,标注对错,用于复盘;
    * 题库试卷导出(``export_questions_html``):题干 + 选项(带字母)
      + 答题区(选择题可勾选、填空/简答可填写),用于纸质练习
      (TODO 08)。

所有文本均经过 HTML 转义,避免注入与显示异常。
"""

from __future__ import annotations

import html
import os
from typing import Dict, List, Optional, Sequence

from quizforge.models import Question, QuestionType

_CSS = """
body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
       margin: 2em auto; max-width: 860px; padding: 0 1em;
       color: #222; line-height: 1.7; }
h1 { font-size: 1.4em; border-bottom: 2px solid #4a90d9;
     padding-bottom: .3em; }
h2 { font-size: 1.1em; margin-top: 1.6em; color: #333; }
.meta { color: #666; font-size: .9em; margin-bottom: 1.5em; }
.q { margin-bottom: 1.6em; padding: .8em 1em; border: 1px solid #ddd;
     border-radius: 6px; background: #fafafa; }
.q.correct { border-left: 4px solid #2e8b57; }
.q.wrong { border-left: 4px solid #c0392b; }
.q.unanswered { border-left: 4px solid #b8860b; }
.qtext { font-weight: bold; margin-bottom: .4em; }
.options { margin: .4em 0 .4em 1.2em; }
.options li { margin: .15em 0; list-style: none; }
.answer { margin-top: .4em; font-size: .92em; }
.yours { color: #c0392b; }
.correct-ans { color: #2e8b57; }
.analysis { color: #555; font-size: .9em; margin-top: .3em; }
.badge { display: inline-block; padding: 0 .5em; border-radius: 3px;
         color: #fff; font-size: .8em; margin-left: .5em; }
.badge.ok { background: #2e8b57; }
.badge.no { background: #c0392b; }
.badge.skip { background: #b8860b; }
.answer-area { margin: .4em 0 .4em 1.2em; font-size: .95em; }
@media print { .q { break-inside: avoid; } }
"""


def _escape(text: object) -> str:
    """HTML 转义(空值转空串)。"""
    return html.escape(str(text or ""), quote=True)


def _fmt_duration(seconds: int) -> str:
    """格式化用时。"""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _page(title: str, body: str) -> str:
    """拼装完整 HTML 页面。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{_escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""


# ---------------------------------------------------------------------- #
# 历史作答记录导出
# ---------------------------------------------------------------------- #
def export_record_html(record: Dict, path: str) -> str:
    """把一条历史成绩记录导出为 HTML(含逐题作答与判分)。

    Args:
        record: 历史记录字典(含 details 逐题详情)。
        path: 输出文件路径。

    Returns:
        输出文件路径。

    Raises:
        OSError: 写入失败。
    """
    title = f"作答记录 - {_escape(record.get('category', ''))}"
    score = record.get("auto_score", 0)
    total = record.get("auto_total", 0)
    meta = (
        f"<div class='meta'>"
        f"时间: {_escape(record.get('timestamp', ''))} &nbsp;|&nbsp; "
        f"来源: {_escape(record.get('category', ''))} &nbsp;|&nbsp; "
        f"得分: {score} / {total} &nbsp;|&nbsp; "
        f"正确率: {score * 100 // total if total else '-'}% "
        f"&nbsp;|&nbsp; 用时: {_fmt_duration(record.get('elapsed_seconds', 0))}"
        f"</div>"
    )

    details = record.get("details", [])
    if not details:
        body = meta + "<p>(该记录没有逐题作答详情)</p>"
        return _write_page(path, title, body)

    items = []
    for index, detail in enumerate(details, start=1):
        items.append(_render_record_question(index, detail))
    body = meta + "\n".join(items)
    return _write_page(path, title, body)


def _render_record_question(index: int, detail: Dict) -> str:
    """渲染一条历史记录的题目。"""
    is_correct = detail.get("is_correct")
    if is_correct is True:
        css = "correct"
        badge = "<span class='badge ok'>正确</span>"
    elif is_correct is False:
        css = "wrong"
        badge = "<span class='badge no'>错误</span>"
    else:
        css = "unanswered"
        badge = "<span class='badge skip'>未答/待评</span>"

    lines = [
        f"<div class='q {css}'>",
        f"<div class='qtext'>{index}. "
        f"[{_escape(detail.get('qtype_label', ''))}] "
        f"{_escape(detail.get('text', ''))} {badge}</div>",
    ]
    options = detail.get("options") or []
    if options:
        lines.append("<ul class='options'>")
        for opt in options:
            lines.append(
                f"<li>{_escape(opt.get('key', ''))}. "
                f"{_escape(opt.get('text', ''))}</li>")
        lines.append("</ul>")
    lines.append(
        f"<div class='answer'>你的作答: "
        f"<span class='yours'>{_escape(detail.get('user_answer', ''))}"
        f"</span></div>")
    if detail.get("correct_answer"):
        lines.append(
            f"<div class='answer'>正确答案: "
            f"<span class='correct-ans'>"
            f"{_escape(detail.get('correct_answer', ''))}</span></div>")
    if detail.get("analysis"):
        lines.append(
            f"<div class='analysis'>解析: "
            f"{_escape(detail.get('analysis', ''))}</div>")
    lines.append("</div>")
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# 题库试卷导出(TODO 08:题干 + 选项 + 答题区,可打印纸质练习)
# ---------------------------------------------------------------------- #
def export_questions_html(questions: Sequence[Question], path: str,
                          title: str = "试卷",
                          show_answers: bool = False) -> str:
    """把题目列表导出为 HTML 试卷。

    Args:
        questions: 题目列表。
        path: 输出文件路径。
        title: 试卷标题。
        show_answers: 是否显示正确答案(练习版不显示,答题区可作答)。

    Returns:
        输出文件路径。

    Raises:
        OSError: 写入失败。
    """
    items = []
    for index, question in enumerate(questions, start=1):
        items.append(_render_paper_question(index, question, show_answers))
    body = (f"<h1>{_escape(title)}</h1>"
            f"<div class='meta'>共 {len(questions)} 题</div>\n"
            + "\n".join(items))
    return _write_page(path, title, body)


def _render_paper_question(index: int, question: Question,
                           show_answers: bool) -> str:
    """渲染试卷题目(选项带字母,含作答区)。"""
    lines = [
        f"<div class='q'>",
        f"<div class='qtext'>{index}. [{question.qtype.label}] "
        f"{_escape(question.text)}</div>",
    ]
    if question.options:
        lines.append("<ul class='options'>")
        for opt in question.options:
            lines.append(
                f"<li>{_escape(opt.key)}. {_escape(opt.text)}</li>")
        lines.append("</ul>")
        if question.qtype == QuestionType.MULTIPLE:
            lines.append("<div class='answer-area'>作答: "
                         "□ A  □ B  □ C  □ D</div>")
        else:
            lines.append("<div class='answer-area'>作答: ○ A  ○ B  "
                         "○ C  ○ D</div>")
    elif question.qtype == QuestionType.FILL:
        lines.append("<div class='answer-area'>作答: ______________</div>")
    else:  # 简答
        lines.append("<div class='answer-area'>作答: "
                     "____________________________</div>")
    if show_answers and question.answer:
        lines.append(
            f"<div class='answer'>答案: "
            f"<span class='correct-ans'>{_escape(question.answer_text())}"
            f"</span></div>")
    if show_answers and question.analysis:
        lines.append(
            f"<div class='analysis'>解析: "
            f"{_escape(question.analysis)}</div>")
    lines.append("</div>")
    return "\n".join(lines)


def _write_page(path: str, title: str, body: str) -> str:
    """写入 HTML 文件。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_page(title, body))
    return path
