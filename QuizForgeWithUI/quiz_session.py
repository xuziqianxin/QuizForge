"""答题会话模块：管理抽题、答案记录、计分。支持打乱选项。"""
import random
import re
from typing import List, Dict, Tuple, Optional
from config import ITEMS_PER_ROW


class QuizSession:
    """一次完整的答题流程状态，不含界面。"""

    def __init__(self, questions: List[Dict], shuffle_options: bool = False):
        if not questions:
            raise ValueError("题库不能为空")
        self.questions = questions
        self._ensure_ids()
        if shuffle_options:
            self._apply_option_shuffle()
        self.order = random.sample(self.questions, len(self.questions))
        self.total = len(self.order)
        self.answers: Dict[str, str] = {}  # qid -> answer string
        self._id_map = {q['id']: q for q in self.questions}

    def _ensure_ids(self) -> None:
        """确保每道题有唯一 ID。"""
        for q in self.questions:
            if 'id' not in q:
                q['id'] = str(uuid.uuid4())

    def _apply_option_shuffle(self) -> None:
        """打乱所有题目的选项并更新正确答案。"""
        for q in self.questions:
            new_opts, new_correct = self._shuffle_single(q['options'], q['correct_answer'])
            q['options'] = new_opts
            q['correct_answer'] = new_correct

    @staticmethod
    def _shuffle_single(options: List[str], correct: Optional[str]) -> Tuple[List[str], str]:
        """打乱单个题目的选项，返回新选项列表和新正确答案。"""
        texts = []
        for opt in options:
            match = re.match(r'^[A-Z]\.\s*', opt)
            texts.append(opt[len(match.group()):].strip() if match else opt.strip())
        indices = list(range(len(texts)))
        random.shuffle(indices)
        letters = [chr(ord('A') + i) for i in range(len(texts))]
        new_options = [f"{letters[i]}. {texts[idx]}" for i, idx in enumerate(indices)]
        old_letters = [chr(ord('A') + i) for i in range(len(texts))]
        mapping = {old: letters[new_i] for new_i, old in enumerate(indices)}
        new_correct = ''.join(mapping.get(ch, ch) for ch in (correct or '').upper())
        return new_options, new_correct

    def get_question(self, index: int) -> Dict:
        """获取当前序列中的第 index 题。"""
        return self.order[index]

    def record_answer(self, qid: str, answer: str) -> None:
        """记录某题的答案（自动转大写）。"""
        self.answers[qid] = answer.upper()

    def is_all_answered(self) -> bool:
        return len(self.answers) == self.total

    def get_missing_count(self) -> int:
        return self.total - len(self.answers)

    def find_next_unanswered_index(self, start: int) -> Optional[int]:
        """从 start 开始循环查找第一个未答题的索引。"""
        for offset in range(self.total):
            idx = (start + offset) % self.total
            if self.order[idx]['id'] not in self.answers:
                return idx
        return None

    def compute_score(self) -> Tuple[int, float, List[str], List[str]]:
        """返回 (正确数, 百分比, 用户答案列表, 正确答案列表)。"""
        user_ans = []
        correct_ans = []
        for q in self.order:
            ua = self.answers.get(q['id'], "未作答")
            ca = (q['correct_answer'] or "未设置").upper()
            user_ans.append(ua)
            correct_ans.append(ca)
        correct_count = sum(1 for u, c in zip(user_ans, correct_ans) if u == c)
        percent = correct_count / self.total * 100 if self.total > 0 else 0.0
        return correct_count, percent, user_ans, correct_ans