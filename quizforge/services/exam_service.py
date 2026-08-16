"""答题会话服务。

负责一次答题练习的完整生命周期:根据配置(题目范围、随机化开关)创建
会话、记录作答、自动评分与生成回看结果。随机化逻辑为纯函数,便于
单元测试与复用。
"""

from __future__ import annotations

import datetime
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from quizforge.models import Question, QuestionType


# ---------------------------------------------------------------------- #
# 随机化工具(纯函数)
# ---------------------------------------------------------------------- #
def shuffled(items: Sequence[str], rng: random.Random) -> List[str]:
    """返回打乱后的元素副本(不打乱原序列)。

    Args:
        items: 原始序列。
        rng: 随机源,便于测试时注入固定种子。

    Returns:
        打乱后的新列表。
    """
    result = list(items)
    rng.shuffle(result)
    return result


def draw_questions(questions: Sequence[Question],
                   specs: Dict[QuestionType, int],
                   seed: Optional[int] = None) -> List[Question]:
    """按题型数量从题目池中无放回抽取题目。

    抽取规则:
        * 每种题型的抽取数量不能超过该题型在池中的题目数(自动截断);
        * 同一道题不会被抽中两次(无放回抽样);
        * 最终题目顺序随机打乱;
        * 随机源默认使用系统熵(random.SystemRandom),保证每次抽取
          随机性;``seed`` 仅供测试注入固定种子。

    Args:
        questions: 题目池(如某个分类的全部题目)。
        specs: 题型 -> 抽取数量 的映射(数量为 0 或缺失表示不抽该题型)。
        seed: 随机种子(仅测试用)。

    Returns:
        抽取到的题目列表(无重复)。
    """
    rng = random.SystemRandom() if seed is None else random.Random(seed)
    by_type: Dict[QuestionType, List[Question]] = {}
    for question in questions:
        by_type.setdefault(question.qtype, []).append(question)

    result: List[Question] = []
    for qtype, count in specs.items():
        pool = by_type.get(qtype, [])
        count = max(0, min(int(count), len(pool)))
        if count:
            result.extend(rng.sample(pool, count))
    rng.shuffle(result)
    return result


# ---------------------------------------------------------------------- #
# 文件选题
# ---------------------------------------------------------------------- #
def load_questions_from_file(path: str, bank) -> List[Question]:
    """从文件读取要作答的题目(第二种选题方式)。

    支持的文件格式:
        * JSON::
            {"ids": ["题目id1", ...]}          # 按题目 id 跨分类匹配
            {"texts": ["题干1", ...]}          # 按题干精确匹配
            {"questions": [题目字典, ...]}      # 直接提供题目
            [题目字典, ...]                     # 题目字典列表
        * 纯文本:每行一个题干(精确匹配)。

    Args:
        path: 文件路径。
        bank: 题库服务(用于 id/题干匹配)。

    Returns:
        按文件顺序排列的题目列表。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 文件格式无法解析或未匹配到任何题目。
    """
    import json
    import os

    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")

    raw: object
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        raw = content  # 纯文本

    if isinstance(raw, dict):
        if "questions" in raw and isinstance(raw["questions"], list):
            return _questions_from_dicts(raw["questions"])
        if "ids" in raw and isinstance(raw["ids"], list):
            return _questions_from_ids(raw["ids"], bank)
        if "texts" in raw and isinstance(raw["texts"], list):
            return _questions_from_texts(raw["texts"], bank)
        raise ValueError("无法识别的 JSON 结构(支持 ids/texts/questions 字段)")
    if isinstance(raw, list):
        return _questions_from_dicts(raw)
    # 纯文本:每行一个题干。
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValueError("文件内容为空")
    return _questions_from_texts(lines, bank)


def _questions_from_dicts(items: list) -> List[Question]:
    """从题目字典列表构造题目。"""
    from quizforge.models import Question
    questions = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index + 1} 项不是题目对象")
        try:
            questions.append(Question.from_dict(item))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index + 1} 项题目字段非法: {exc}") from exc
    if not questions:
        raise ValueError("文件中没有题目")
    return questions


def _questions_from_ids(ids: list, bank) -> List[Question]:
    """按题目 id 跨分类匹配。"""
    questions = []
    for question_id in ids:
        question = bank.find_question_anywhere(str(question_id))
        if question is not None:
            questions.append(question)
    if not questions:
        raise ValueError("未能在题库中找到文件指定的题目(id 不存在)")
    return questions


def _questions_from_texts(texts: list, bank) -> List[Question]:
    """按题干精确匹配(允许同一题干出现多次时去重)。"""
    questions = []
    seen_ids = set()
    for text in texts:
        for question in bank.find_questions_by_text(str(text)):
            if question.id not in seen_ids:
                seen_ids.add(question.id)
                questions.append(question)
    if not questions:
        raise ValueError("未能在题库中找到文件指定的题目(题干不匹配)")
    return questions


# ---------------------------------------------------------------------- #
# 会话数据结构
# ---------------------------------------------------------------------- #
@dataclass
class ExamConfig:
    """一次答题的配置。

    Attributes:
        question_ids: 参与本次答题的题目 id 列表(原始顺序)。
        shuffle_questions: 是否随机打乱题目顺序。
        shuffle_options: 是否随机打乱选择题选项顺序。
        mode: 答题模式,``"exam"`` 普通答题 / ``"wrongbook"`` 错题重练。
        time_limit_seconds: 限时模拟考试时长(秒);0 表示不限时,
            到点自动交卷。
        category_id: 抽题来源分类(历史成绩记录用);文件选题为空。
    """

    question_ids: List[str] = field(default_factory=list)
    shuffle_questions: bool = False
    shuffle_options: bool = False
    mode: str = "exam"
    time_limit_seconds: int = 0
    category_id: str = ""


@dataclass
class ExamSession:
    """一次进行中的答题会话。

    Attributes:
        session_id: 会话唯一标识。
        config: 会话配置。
        order: 实际作答顺序(题目 id 列表)。
        option_order: 题目 id -> 打乱后的选项键顺序(未打乱时为原顺序)。
        answers: 题目 id -> 用户作答(选项键列表或答案文本列表)。
        started_at: 开始时间。
        finished_at: 结束时间(提交时写入)。
        elapsed_seconds: 累计已用秒数(暂停时不再累加)。
        _timer_base: 当前计时段的起点(monotonic);暂停时为 None。
        paused: 是否处于暂停状态。
    """

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    config: ExamConfig = field(default_factory=ExamConfig)
    order: List[str] = field(default_factory=list)
    option_order: Dict[str, List[str]] = field(default_factory=dict)
    answers: Dict[str, List[str]] = field(default_factory=dict)
    started_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat(
            timespec="seconds"))
    finished_at: Optional[str] = None
    elapsed_seconds: int = 0
    _timer_base: Optional[float] = None
    paused: bool = False

    # ------------------------------------------------------------------ #
    def start_timer(self) -> None:
        """开始计时(创建会话时调用)。"""
        if self._timer_base is None and not self.paused:
            self._timer_base = time.monotonic()

    def pause_timer(self) -> None:
        """暂停计时:把当前累计时间并入 elapsed_seconds。"""
        if self._timer_base is not None:
            self.elapsed_seconds += int(time.monotonic() - self._timer_base)
            self._timer_base = None
        self.paused = True

    def resume_timer(self) -> None:
        """继续计时。"""
        if self._timer_base is None:
            self._timer_base = time.monotonic()
        self.paused = False

    def current_elapsed(self) -> int:
        """当前累计已用秒数(含进行中的计时段)。"""
        total = self.elapsed_seconds
        if self._timer_base is not None:
            total += int(time.monotonic() - self._timer_base)
        return total

    def format_elapsed(self) -> str:
        """将已用时间格式化为 "MM:SS"(超过 1 小时为 "H:MM:SS")。"""
        total = self.current_elapsed()
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def time_remaining(self) -> int:
        """限时模拟考试的剩余秒数(>=0);不限时返回 -1。"""
        limit = self.config.time_limit_seconds
        if limit <= 0:
            return -1
        return max(0, limit - self.current_elapsed())

    def format_remaining(self) -> str:
        """将剩余时间格式化为倒计时 "MM:SS"(超过 1 小时为 "H:MM:SS")。"""
        remaining = self.time_remaining()
        if remaining < 0:
            return ""
        hours, remainder = divmod(remaining, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    # ------------------------------------------------------------------ #
    def question_index(self, question_id: str) -> int:
        """返回题目在作答顺序中的下标。

        Args:
            question_id: 题目 id。

        Returns:
            下标;不存在时返回 -1。
        """
        try:
            return self.order.index(question_id)
        except ValueError:
            return -1

    def is_answered(self, question_id: str) -> bool:
        """判断某题是否已作答。"""
        return bool(self.answers.get(question_id))

    def record_answer(self, question_id: str, keys: List[str]) -> None:
        """记录某题的作答(空列表表示清除作答)。"""
        if keys:
            self.answers[question_id] = keys
        else:
            self.answers.pop(question_id, None)


@dataclass
class QuestionResult:
    """单题评分结果。

    Attributes:
        question: 题目对象。
        user_answer: 用户作答(原始文本形式)。
        correct_answer: 正确答案(原始文本形式)。
        is_correct: 是否正确(简答题为 None,表示需人工评分)。
    """

    question: Question
    user_answer: str
    correct_answer: str
    is_correct: Optional[bool]


@dataclass
class ExamResult:
    """整场答题的评分结果。

    Attributes:
        session: 对应会话。
        results: 按作答顺序排列的单题结果。
        correct_count / wrong_count / unanswered_count: 各状态题数。
        no_answer_count: 未设置标准答案的题数(不参与自动评分)。
        auto_score: 自动评分得分(可自动评分题目的正确数)。
        auto_total: 可自动评分的题目总数。
    """

    session: ExamSession
    results: List[QuestionResult] = field(default_factory=list)
    correct_count: int = 0
    wrong_count: int = 0
    unanswered_count: int = 0
    no_answer_count: int = 0
    auto_score: int = 0
    auto_total: int = 0

    @property
    def short_question_count(self) -> int:
        """需人工评分的简答题数量。"""
        return sum(1 for r in self.results
                   if r.question.qtype == QuestionType.SHORT)


# ---------------------------------------------------------------------- #
# 会话服务
# ---------------------------------------------------------------------- #
class ExamService:
    """答题会话的创建、作答记录与评分。"""

    def create_session(self,
                       questions: Sequence[Question],
                       config: ExamConfig,
                       seed: Optional[int] = None) -> ExamSession:
        """根据配置创建新会话。

        Args:
            questions: 题目对象列表(与 config.question_ids 对应)。
            config: 会话配置。
            seed: 随机种子(仅测试用);None 时使用系统随机源。

        Returns:
            新会话,已按配置应用题目/选项随机化。
        """
        rng = random.Random(seed)
        # 拷贝一份题目 id,避免会话与外部配置共享同一列表
        # (外部修改 config.question_ids 会意外影响会话)。
        order = list(config.question_ids)
        if config.shuffle_questions:
            order = shuffled(order, rng)

        by_id = {q.id: q for q in questions}
        option_order: Dict[str, List[str]] = {}
        for question_id in order:
            question = by_id.get(question_id)
            if question is None:
                continue
            keys = [opt.key for opt in question.options]
            if config.shuffle_options and question.is_choice:
                keys = shuffled(keys, rng)
            option_order[question_id] = keys

        session = ExamSession(config=config, order=order,
                              option_order=option_order)
        session.start_timer()
        return session

    def grade(self, session: ExamSession,
              questions: Sequence[Question]) -> ExamResult:
        """对已完成会话评分。

        评分规则:
            * 单选/判断题:用户答案与标准答案一致即正确;
            * 多选题:用户答案集合与标准答案集合完全一致(可扩展为部分给分);
            * 填空题:用户答案文本与任一可接受答案一致(忽略首尾空白);
            * 简答题:不自动评分,is_correct 记为 None。

        Args:
            session: 已结束(或待结束)的会话。
            questions: 会话涉及的全部题目。

        Returns:
            评分结果。
        """
        by_id = {q.id: q for q in questions}
        result = ExamResult(session=session)
        for question_id in session.order:
            question = by_id.get(question_id)
            if question is None:
                continue
            user_keys = session.answers.get(question_id, [])
            correct = self._grade_one(question, user_keys)
            result.results.append(
                QuestionResult(
                    question=question,
                    user_answer=_format_answer(question, user_keys),
                    correct_answer=question.answer_text(),
                    is_correct=correct,
                ))
            if question.qtype == QuestionType.SHORT:
                continue  # 简答题不计入自动评分
            if not question.answer:
                result.no_answer_count += 1  # 未设置标准答案,不评分
                continue
            result.auto_total += 1
            if correct is True:
                result.correct_count += 1
                result.auto_score += 1
            elif correct is False:
                result.wrong_count += 1
            else:  # 未作答
                result.unanswered_count += 1
        return result

    # ------------------------------------------------------------------ #
    @staticmethod
    def _grade_one(question: Question, user_keys: List[str]) -> Optional[bool]:
        """对单题评分,返回 True/False/None(未作答或不可评分)。"""
        if not user_keys:
            return None
        if question.qtype == QuestionType.SHORT:
            return None
        if not question.answer:
            return None  # 未设置标准答案,无法自动评分
        if question.qtype == QuestionType.FILL:
            normalized = [k.strip() for k in user_keys if k.strip()]
            if not normalized:
                return None
            joined = "".join(normalized)
            return any(joined == a.strip() for a in question.answer)
        # 选择题(单选/多选/判断)。
        user_set = set(user_keys)
        correct_set = set(question.answer)
        if question.qtype == QuestionType.SINGLE and len(user_set) != 1:
            return False
        return user_set == correct_set


def _format_answer(question: Question, keys: List[str]) -> str:
    """将作答渲染为文本:选择题显示选项内容,其他题型显示原文。"""
    if not keys:
        return "(未作答)"
    if question.is_choice:
        mapping = question.option_map
        return " / ".join(f"{key}. {mapping.get(key, '')}" for key in keys)
    return " / ".join(keys)
