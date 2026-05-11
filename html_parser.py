"""
HTML 题目解析器：从作业/考试详情页提取标准化题目列表。
通过继承或配置可以适配不同平台。
"""
import re
from typing import List, Tuple, Dict, Optional
from bs4 import BeautifulSoup, Tag
from config import HTML_CLASSES, TYPE_PATTERN


class HtmlParser:
    """负责解析题目 HTML，返回字典列表及错误题号。"""

    def __init__(self):
        self._cls = HTML_CLASSES  # 可动态替换

    def parse(self, html_file_path: str) -> Tuple[List[Dict], List[str]]:
        """主解析方法，返回 (题目列表, 错误题号列表)。"""
        with open(html_file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')

        questions = []
        wrong_numbers = []
        question_divs = soup.find_all(
            'div', class_=lambda c: c and self._cls["question_container"] in c
        )

        for qdiv in question_divs:
            q_data = self._parse_single(qdiv)
            if q_data is None:
                continue
            if q_data["correct_answer"] is None and q_data["number"]:
                wrong_numbers.append(q_data["number"])
            questions.append(q_data)

        return questions, wrong_numbers

    # ---------- 单个题目解析 ----------
    def _parse_single(self, qdiv: Tag) -> Optional[Dict]:
        """解析单个题目 div 为字典。"""
        qid = qdiv.get('id', '')
        h3 = qdiv.find('h3', class_=self._cls["title_header"])
        if not h3:
            return None

        title_text = h3.get_text(strip=True)
        number = self._extract_number(title_text)
        question_type = self._extract_type(h3)
        question_text = self._extract_question_text(qdiv)
        options = self._extract_options(qdiv)
        my_answer = self._extract_user_answer(qdiv)
        correct_answer = self._determine_correct(qdiv, my_answer)

        return {
            'id': qid,
            'number': number,
            'type': question_type,
            'question': question_text,
            'options': options,
            'correct_answer': correct_answer,
        }

    # ---------- 子提取方法（可单独覆盖） ----------
    @staticmethod
    def _extract_number(title: str) -> str:
        """从标题中提取题号，如 '1.单选题...' 返回 '1'。"""
        parts = title.split('.', 1)
        return parts[0].strip() if len(parts) == 2 else ''

    def _extract_type(self, h3: Tag) -> str:
        """清洗题型文本，返回纯题型名称（如 '单选题'）。"""
        type_span = h3.find('span', class_=self._cls["type_span"])
        if not type_span:
            return ''
        raw = type_span.get_text(strip=True)
        match = re.search(TYPE_PATTERN, raw)
        if match:
            return match.group(1)
        # 降级清洗
        return re.sub(r'[()（）,，\d.\s分]', '', raw).strip()

    def _extract_question_text(self, qdiv: Tag) -> str:
        """提取题干文本。"""
        qt_span = qdiv.find('span', class_=self._cls["question_content"])
        return qt_span.get_text(strip=True) if qt_span else ''

    def _extract_options(self, qdiv: Tag) -> List[str]:
        """提取选项列表，保持原始文本。"""
        ul = qdiv.find('ul', class_=self._cls["options_list"])
        if not ul:
            return []
        return [li.get_text(strip=True) for li in ul.find_all('li') if li.get_text(strip=True)]

    def _extract_user_answer(self, qdiv: Tag) -> str:
        """提取用户已填答案。"""
        stu_span = qdiv.find('span', class_=self._cls["user_answer"])
        return stu_span.get_text(strip=True) if stu_span else ''

    def _determine_correct(self, qdiv: Tag, my_answer: str) -> Optional[str]:
        """根据页面类型确定正确答案（作业页直接有，考试页根据对错推断）。"""
        right_span = qdiv.find('span', class_=self._cls["correct_answer"])
        if right_span:
            return right_span.get_text(strip=True)
        judge = qdiv.find('div', class_=self._cls["judge_div"])
        if judge:
            if judge.find('span', class_=self._cls["correct_mark"]):
                return my_answer
            if judge.find('span', class_=self._cls["wrong_mark"]):
                return None
        return None