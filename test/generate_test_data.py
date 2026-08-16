"""生成 QuizForge 测试题库 JSON(1500 题)。

产出文件: data/test_1500.json
格式符合 quizforge.models.Question.to_dict() 的字段要求,
可直接在「题库管理 -> 导入」中按「题型 + 题干」去重导入。

题型分布:
    single   单选题   600 题
    multiple 多选题   300 题
    judge    判断题   300 题
    fill     填空题   200 题
    short    简答题   100 题
"""

from __future__ import annotations

import datetime
import json
import os
import random
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quizforge.models import Option, Question, QuestionType  # noqa: E402

TOTAL = 1500
OUT_PATH = os.path.join("data", "test_1500.json")

#: 题干前缀池(学科风格,保证内容多样)。
_TOPICS = [
    "数学", "高等数学", "线性代数", "概率论", "大学英语", "英语语法",
    "计算机基础", "数据结构", "操作系统", "计算机网络", "数据库原理",
    "大学物理", "化学基础", "中国近代史", "马克思主义原理",
]

#: 通用选项文本池。
_OPTION_TEXT = [
    "正确", "错误", "以上说法都对", "以上说法都不对",
    "大约增加一倍", "保持不变", "大约减少一半", "无法确定",
    "质数", "合数", "偶数", "奇数",
    "栈", "队列", "二叉树", "哈希表",
    "TCP", "UDP", "HTTP", "FTP",
    "主键", "外键", "索引", "视图",
    "定义", "定理", "公理", "推论",
    "金属", "非金属", "稀有气体", "化合物",
]

#: 填空/简答文本模板。
_FILL_TEMPLATES = [
    "{}中,{}{}的典型值是 {}",
    "在{}课程中,核心概念之一是 {},它主要用于 {}",
    "{}的{}等于 {},这是考试高频考点",
    "简述{}中 {} 的基本原理,并举例说明",
    "请写出{}中关于 {} 的一个定义,并解释其含义",
    "{}中,{} 与 {} 的区别是什么",
]

#: 来源池。
_SOURCES = ["超星学习通 - 期中测试", "超星学习通 - 单元测验",
            "超星学习通 - 期末复习", "教师自编", "历年真题"]


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _make_single(rng: random.Random, idx: int) -> Question:
    topic = rng.choice(_TOPICS)
    options = rng.sample(_OPTION_TEXT, 4)
    return Question(
        qtype=QuestionType.SINGLE,
        text=f"单选题{idx:04d}·{topic}:下列选项中哪一个是正确的?",
        options=[Option(key, text) for key, text in
                 zip("ABCD", options)],
        answer=[rng.choice("ABCD")],
        analysis=f"本题考查{topic}的基础概念,正确答案依据教材第 {rng.randint(1, 12)} 章。",
        source=rng.choice(_SOURCES),
    )


def _make_multiple(rng: random.Random, idx: int) -> Question:
    topic = rng.choice(_TOPICS)
    options = rng.sample(_OPTION_TEXT, 4)
    answer_keys = [key for key in "ABCD"
                   if rng.random() < 0.5][:3]
    if len(answer_keys) < 2:
        answer_keys = ["A", "B"]
    return Question(
        qtype=QuestionType.MULTIPLE,
        text=f"多选题{idx:04d}·{topic}:以下哪些说法是正确的?(多选)",
        options=[Option(key, text) for key, text in
                 zip("ABCD", options)],
        answer=answer_keys,
        analysis=f"本题为多选题,涉及{topic}的多个知识点,需选 {len(answer_keys)} 项。",
        source=rng.choice(_SOURCES),
    )


def _make_judge(rng: random.Random, idx: int) -> Question:
    topic = rng.choice(_TOPICS)
    value = rng.choice(["正确", "错误"])
    return Question(
        qtype=QuestionType.JUDGE,
        text=f"判断题{idx:04d}·{topic}:{topic}中的命题「{value}」成立。",
        options=[],
        answer=["A" if value == "正确" else "B"],
        analysis=f"判断题考察{topic}的定性结论,答案为「{value}」。",
        source=rng.choice(_SOURCES),
    )


def _make_fill(rng: random.Random, idx: int) -> Question:
    topic = rng.choice(_TOPICS)
    filler = rng.choice(["变量", "函数", "矩阵", "算法", "协议", "定理"])
    value = rng.choice(["0", "1", "π", "e", "O(n)", "3"])
    return Question(
        qtype=QuestionType.FILL,
        text=f"填空题{idx:04d}·{topic}:请填写 {topic} 中 {filler} 的数值/含义。",
        options=[],
        answer=[value],
        analysis=f"填空题参考答案为「{value}」,评分时忽略首尾空白。",
        source=rng.choice(_SOURCES),
    )


def _make_short(rng: random.Random, idx: int) -> Question:
    topic = rng.choice(_TOPICS)
    concept = rng.choice(["栈与队列", "死锁", "时间复杂度", "范数",
                          "条件概率", "范式"])
    template = rng.choice(_FILL_TEMPLATES)
    text = template.format(topic, concept, rng.choice(["本质", "定义",
                                                       "作用"]),
                           rng.choice(["稳定", "高效", "有限"]))
    return Question(
        qtype=QuestionType.SHORT,
        text=f"简答题{idx:04d}·{topic}:{text}",
        options=[],
        answer=["参考答案:按要点作答,言之成理即可"],
        analysis="简答题不自动评分,需人工核对。",
        source=rng.choice(_SOURCES),
    )


def main() -> None:
    """生成题库并写出 JSON。"""
    rng = random.Random(20260815)
    makers = [
        (QuestionType.SINGLE, 600, _make_single),
        (QuestionType.MULTIPLE, 300, _make_multiple),
        (QuestionType.JUDGE, 300, _make_judge),
        (QuestionType.FILL, 200, _make_fill),
        (QuestionType.SHORT, 100, _make_short),
    ]
    questions: list[Question] = []
    idx = 1
    seen_text: set = set()
    for qtype, count, maker in makers:
        made = 0
        while made < count:
            question = maker(rng, idx)
            idx += 1
            if question.text in seen_text:
                continue
            seen_text.add(question.text)
            question.id = uuid.uuid4().hex
            question.created_at = _now()
            question.updated_at = _now()
            questions.append(question)
            made += 1
        print(f"  {qtype.label}: {made} 题")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    payload = {
        "version": 1,
        "questions": [q.to_dict() for q in questions],
    }
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"已生成 {len(questions)} 题 -> {OUT_PATH} "
          f"({os.path.getsize(OUT_PATH) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
