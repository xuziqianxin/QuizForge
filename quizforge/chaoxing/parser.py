"""学习通作业页面 HTML 解析器。

包含两部分:
    * ``parse_work_list``:解析作业列表页(``/work/getAllWork``),得到
      作业的基本信息(名称、workId、作答 id、截止时间、状态等);
    * ``parse_work_page``:解析作业题目页(``/work/selectWorkQuestionYiPiYue``
      回看页或 ``/work/doHomeWorkNew`` 作答表单页),得到题目列表。

解析器对两种页面结构均做兼容处理(作答表单页含 input 控件,回看页为
纯文本渲染),解析不到题目时抛出 ``ParseError`` 并给出提示。

注意:学习通页面会随版本调整,如遇解析失败,优先检查本文件的选择器。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, Tag

from quizforge.chaoxing.client import Course, Work
from quizforge.models import Option, Question, QuestionType

#: 题干开头的题号标记,如 "1"、"1."、"1、" 等。
_STEM_NUMBER_PATTERN = re.compile(r"^\s*\d{1,3}\s*[.、．\)）]?\s*")

#: 题干末尾的分值标记,如 "(100.0分)" / "（5分）"。
_STEM_SCORE_PATTERN = re.compile(r"\s*[\(（]\s*\d+(\.\d+)?\s*分\s*[\)）]\s*$")

#: 选择题选项键标记,如 "A."、"B、" 等。
_OPTION_KEY_PATTERN = re.compile(r"^([A-Ha-h])\s*[.、．\)）]?\s*(.*)$")

#: 回看页中"正确答案"区块的内容(选择题为字母组合)。
_CHOICE_ANSWER_PATTERN = re.compile(r"^\s*([A-Ha-h][A-Ha-h,，、\s]*)\s*$")

#: 判断题答案写法。
_JUDGE_ANSWER_PATTERNS = ("对", "错", "√", "×", "正确", "错误")

#: 填空题横线/括号占位。
_BLANK_PATTERNS = (r"_{2,}", r"（\s*）", r"\(\s*\)", r"【\s*】")

#: 题干中的题型提示词(学习通常在题干中标注题型)。
#: 按优先级排列,先匹配更具体的"多项选择",避免与"单选"混淆。
_TYPE_HINT_PATTERNS: List[tuple[QuestionType, re.Pattern]] = [
    (QuestionType.MULTIPLE, re.compile(
        r"多选题|多项选择题|多项选择|\(多选\)|（多选）|【多选】|\[多选\]")),
    (QuestionType.SINGLE, re.compile(
        r"单选题|单项选择题|单项选择|\(单选\)|（单选）|【单选】|\[单选\]")),
    (QuestionType.JUDGE, re.compile(r"判断题|判断正误|\(判断\)|（判断）")),
    (QuestionType.FILL, re.compile(r"填空题|\(填空\)|（填空）")),
    (QuestionType.SHORT, re.compile(r"简答题|\(简答\)|（简答）|问答题")),
]


class ParseError(ValueError):
    """作业页面无法解析出题目时抛出。"""


# ====================================================================== #
# 作业列表解析
# ====================================================================== #
#: 作业列表页的分页信息,如 page.showPage(1, 3, "changePage", ...)。
#: 第二个参数为总页数。
_TOTAL_PAGES_PATTERN = re.compile(r"page\.showPage\(\s*\d+\s*,\s*(\d+)")


def parse_total_pages(html: str) -> int:
    """从作业列表页 HTML 提取总页数。

    Args:
        html: 作业列表页 HTML。

    Returns:
        总页数(解析失败时按 1 处理,保证至少抓取第一页)。
    """
    match = _TOTAL_PAGES_PATTERN.search(html)
    if not match:
        return 1
    try:
        return max(1, int(match.group(1)))
    except ValueError:
        return 1


def parse_work_list(html: str, course: Course) -> List[Work]:
    """解析作业列表页 HTML。

    Args:
        html: 作业列表页 HTML。
        course: 所属课程(用于填充 Work 的课程信息)。

    Returns:
        作业列表;页面完全没有作业条目时返回空列表。

    Raises:
        ParseError: 页面存在作业条目但均无法解析(可能页面结构已改版)。
    """
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("li.lookLi")
    works: List[Work] = []
    for item in items:
        work = _parse_work_item(item, course)
        if work is not None:
            works.append(work)
    if not works:
        if items:
            raise ParseError(
                "作业列表页存在条目但解析失败,学习通页面可能改版,"
                "请检查 quizforge/chaoxing/parser.py")
        return []  # 课程没有作业
    return works


def _parse_work_item(item: Tag, course: Course) -> Optional[Work]:
    """解析单个作业条目。

    workId 可能是纯数字(常规作业),也可能是 32 位十六进制字符串
    (viewWork 类作业),因此按 ``[0-9a-fA-F]+`` 匹配。
    """
    link = item.select_one("a[href*='workId=']")
    if link is None:
        return None
    href = str(link.get("href", ""))
    work_id_match = re.search(r"workId=([0-9a-fA-F]+)", href)
    if not work_id_match:
        return None
    work_id = work_id_match.group(1)

    name = str(link.get("title") or link.get_text(" ", strip=True)).strip()
    enc_match = re.search(r"enc=([0-9a-fA-F]+)", href)
    answer_match = re.search(r"workAnswerId=(\d+)", href)
    if "selectWorkQuestionYiPiYue" in href:
        kind = "review"
    elif "doHomeWorkNew" in href:
        kind = "form"
    else:
        kind = "view"  # viewWork 等只读页面
    view_id_match = re.search(r"[?&]id=(\d+)", href)

    deadline = _span_label(item, "截止时间")
    status = _span_label(item, "作业状态")

    return Work(
        work_id=work_id,
        name=name or f"作业 {work_id}",
        course_id=course.course_id,
        clazz_id=course.clazz_id,
        cpi=course.cpi,
        deadline=deadline,
        status=status,
        enc=enc_match.group(1) if enc_match else "",
        work_answer_id=answer_match.group(1) if answer_match else "",
        view_id=view_id_match.group(1) if view_id_match else "",
        kind=kind,
    )


def _span_label(item: Tag, label: str) -> str:
    """提取条目中 "标签:" 后的文本,如 "截止时间：2026-05-31 10:44"。"""
    for span in item.select("span.pt5"):
        text = span.get_text(" ", strip=True)
        if text.startswith(label):
            return text[len(label):].lstrip("：: \t")
    return ""


# ====================================================================== #
# 作业题目解析
# ====================================================================== #
def parse_work_page(html: str, source: str = "") -> List[Question]:
    """解析作业题目页 HTML。

    Args:
        html: 作业题目页 HTML。
        source: 题目来源描述(如 "超星学习通 - 作业名")。

    Returns:
        题目列表(不含 id 与时间戳,由题库服务在合并时规范化)。

    Raises:
        ParseError: 页面中未找到题目块。
    """
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div.TiMu")
    if not blocks:
        raise ParseError(
            "未在作业页面中找到题目(div.TiMu),学习通页面可能改版,"
            "请检查 quizforge/chaoxing/parser.py")

    questions: List[Question] = []
    for block in blocks:
        question = _parse_question_block(block, source)
        if question is not None:
            questions.append(question)
    if not questions:
        raise ParseError("作业页面结构无法识别,请检查学习通页面是否已改版")
    return questions


def _parse_question_block(block: Tag, source: str) -> Optional[Question]:
    """解析单个题目块,失败时返回 None。"""
    stem_element = (block.select_one(".Zy_TItle")
                    or block.select_one(".zy_tit"))
    if stem_element is None:
        return None
    stem_text = _clean_text(stem_element.get_text(" ", strip=True))
    stem_text = _STEM_NUMBER_PATTERN.sub("", stem_text)
    stem_text = _STEM_SCORE_PATTERN.sub("", stem_text).strip()
    if not stem_text:
        return None

    qtype, options = _detect_type_and_options(block, stem_text)
    answer = _extract_correct_answer(block, qtype)

    # 回看页无 input 时,单选/多选需根据答案字母数量修正。
    if qtype == QuestionType.SINGLE and len(answer) > 1:
        qtype = QuestionType.MULTIPLE

    if qtype == QuestionType.JUDGE:
        options = [Option("A", "对"), Option("B", "错")]

    if qtype.is_choice and len(options) < 2:
        return None

    return Question(qtype=qtype, text=stem_text, options=options,
                    answer=answer, source=source)


def _detect_type_and_options(block: Tag,
                             stem_text: str) -> tuple[QuestionType,
                                                      List[Option]]:
    """推断题型并提取选项(兼容表单页与回看页)。

    判定优先级:
        1. 题干中的题型提示词(如"(多选)"),最可靠,直接决定题型;
        2. 表单页 input 控件(checkbox -> 多选,radio -> 单选/判断);
        3. 回看页文本选项(结合答案字母数,由调用方修正单选/多选)。
    """
    hint = _detect_type_hint(stem_text)

    # 1) 表单页:按 input 控件判断。
    radios = block.select("input[type='radio']")
    checkboxes = block.select("input[type='checkbox']")
    if radios or checkboxes:
        options = _options_from_inputs(radios, checkboxes)
        if checkboxes:
            return QuestionType.MULTIPLE, options
        if hint == QuestionType.JUDGE or (
                len(radios) == 2 and _is_judge_options(options)):
            return QuestionType.JUDGE, options
        if hint == QuestionType.MULTIPLE:
            return QuestionType.MULTIPLE, options
        return QuestionType.SINGLE, options

    # 2) 回看页:无 input,按文本中的选项键判断。
    text_options = _options_from_text(block)
    if text_options:
        if hint == QuestionType.JUDGE or (
                len(text_options) == 2 and _is_judge_options(text_options)):
            return QuestionType.JUDGE, text_options
        if hint == QuestionType.MULTIPLE:
            return QuestionType.MULTIPLE, text_options
        # 单选/多选需结合答案字母数量判断(见 _extract_correct_answer
        # 之后由调用方修正);这里先按单选处理。
        return QuestionType.SINGLE, text_options

    # 3) 无选项:题干提示词直接定题型,否则填空/简答。
    if hint is not None:
        return hint, []
    if _looks_like_fill(stem_text):
        return QuestionType.FILL, []
    return QuestionType.SHORT, []


def _detect_type_hint(stem_text: str) -> Optional[QuestionType]:
    """按题干中的题型提示词推断题型;无提示词返回 None。

    注意:题干提示词优先于结构推断,可避免"回看页答案提取失败导致
    多选题被误判为单选"等问题。
    """
    for qtype, pattern in _TYPE_HINT_PATTERNS:
        if pattern.search(stem_text):
            return qtype
    return None


def _options_from_inputs(radios: List[Tag],
                         checkboxes: List[Tag]) -> List[Option]:
    """从 input 控件提取选项。"""
    options: List[Option] = []
    inputs = radios or checkboxes
    for index, input_el in enumerate(inputs):
        key = str(input_el.get("value") or "").strip().upper()
        # input 的 value 可能是数字索引等非法选项键,回退为字母键。
        if len(key) != 1 or key not in "ABCDEFGH":
            key = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[index]
        # 选项文本:优先 li 内 label;input 直接位于 label 内时取外层
        # label;否则取父元素文本兜底。
        parent = input_el.find_parent("li") or input_el.parent
        label = parent.select_one("label") if parent is not None else None
        if label is None:
            label = input_el.find_parent("label")
        if label is not None:
            text = _clean_text(label.get_text(" ", strip=True))
        elif parent is not None:
            text = _clean_text(parent.get_text(" ", strip=True))
        else:
            text = ""
        text = _OPTION_KEY_PATTERN.sub(r"\2", text).strip()
        options.append(Option(key=key, text=text or key))
    return options


def _options_from_text(block: Tag) -> List[Option]:
    """从回看页的 li 文本中提取选项。"""
    lis = block.select("ul li")
    texts = [_clean_text(li.get_text(" ", strip=True)) for li in lis]
    texts = [text for text in texts if text]
    if not texts:
        return []
    # 判断题:选项为"对/错"或"√/×"(无字母键)。
    if set(texts) == {"对", "错"} or set(texts) == {"√", "×"}:
        return [Option("A", "对"), Option("B", "错")]
    # 选择题:带字母键的选项。
    options: List[Option] = []
    for text in texts:
        match = _OPTION_KEY_PATTERN.match(text)
        if match:
            options.append(Option(key=match.group(1).upper(),
                                  text=match.group(2).strip() or match.group(1)))
    return options


def _is_judge_options(options: List[Option]) -> bool:
    """判断选项是否为"对/错"。"""
    texts = {opt.text.strip() for opt in options}
    return texts == {"对", "错"} or texts == {"√", "×"}


def _looks_like_fill(stem_text: str) -> bool:
    """判断题干是否像填空题(含横线或括号占位)。"""
    return any(re.search(pattern, stem_text) for pattern in _BLANK_PATTERNS)


def _extract_correct_answer(block: Tag,
                            qtype: QuestionType) -> List[str]:
    """提取正确答案。

    兼容两种页面结构:
        1. ``div.Py_tk`` 容器(无 id 的第一个);
        2. 直接内联文本 ``正确答案： B``(无容器)。
    """
    answer_text = ""

    # 方式一:Py_tk 容器。
    answer_block = None
    for div in block.select("div.Py_tk"):
        if not div.get("id"):
            answer_block = div
            break
    if answer_block is not None:
        answer_text = _clean_text(answer_block.get_text(" ", strip=True))
        answer_text = re.sub(r"^正确答案[：:]?\s*", "", answer_text)
    else:
        # 方式二:直接匹配内联"正确答案："文本。
        block_text = block.get_text(" ", strip=True)
        if qtype in (QuestionType.SINGLE, QuestionType.MULTIPLE):
            match = re.search(
                r"正确答案[：:]\s*([A-Ha-h][A-Ha-h,，、\s]*)", block_text)
        elif qtype == QuestionType.JUDGE:
            match = re.search(
                r"正确答案[：:]\s*(对|错|√|×|正确|错误)", block_text)
        else:  # 填空/简答
            match = re.search(
                r"正确答案[：:]\s*(.*?)(?=\s*我的答案|\s*$)",
                block_text, re.S)
        answer_text = match.group(1).strip() if match else ""

    if not answer_text:
        return []
    if qtype == QuestionType.JUDGE:
        for token in _JUDGE_ANSWER_PATTERNS:
            if token in answer_text:
                return ["A"] if token in ("对", "√", "正确") else ["B"]
        return []
    if qtype in (QuestionType.SINGLE, QuestionType.MULTIPLE):
        keys: List[str] = []
        match = _CHOICE_ANSWER_PATTERN.match(answer_text)
        if match:
            # 兼容无分隔符答案(如 "AC" = A、C 两个选项):
            # 分隔符拆分后,每个 token 再逐字母展开。
            tokens = re.split(r"[,，、\s]+", match.group(1).upper())
            for token in tokens:
                if token:
                    keys.extend(list(token))
        else:
            # 答案文本非纯字母组合(如含"解析"等杂质):回退提取其中
            # 的全部字母,提高鲁棒性。
            keys = [ch.upper() for ch in re.findall(r"[A-Ha-h]",
                                                    answer_text)]
        return [key for key in keys if key in "ABCDEFGH"]
    # 填空/简答:答案文本整体保存(多个可接受答案以 | 分隔)。
    return [answer_text]


def _clean_text(text: str) -> str:
    """压缩空白并去除首尾空白。"""
    return re.sub(r"\s+", " ", text).strip()
