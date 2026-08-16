"""领域模型定义。

本模块定义题库的核心领域模型:题型枚举(QuestionType)、选项(Option)与
题目(Question)。模型与存储、界面完全解耦:持久化与界面展示都通过
``to_dict`` / ``from_dict`` 与 JSON 互转完成,后续新增题型只需扩展枚举
与校验逻辑,不影响其他层。
"""

from __future__ import annotations

import datetime
import enum
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 题目选项的键由字母组成。
OPTION_KEYS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _now() -> str:
    """返回当前本地时间的 ISO 格式字符串(用于 created_at / updated_at)。"""
    return datetime.datetime.now().isoformat(timespec="seconds")


class QuestionType(str, enum.Enum):
    """题型枚举(字符串枚举,值可直接用于 JSON 序列化)。

    支持的值:
        single   单选题
        multiple 多选题
        judge    判断题
        fill     填空题
        short    简答题
    """

    SINGLE = "single"
    MULTIPLE = "multiple"
    JUDGE = "judge"
    FILL = "fill"
    SHORT = "short"

    @property
    def label(self) -> str:
        """题型的中文显示名。"""
        return _TYPE_LABELS[self]

    @property
    def is_choice(self) -> bool:
        """是否为选择题(单选/多选/判断)。"""
        return self in (QuestionType.SINGLE, QuestionType.MULTIPLE,
                        QuestionType.JUDGE)

    @classmethod
    def from_label(cls, label: str) -> "QuestionType":
        """根据中文显示名反查题型,找不到时抛出 ValueError。"""
        for member in cls:
            if member.label == label:
                return member
        raise ValueError(f"未知题型: {label}")


#: 题型 -> 中文显示名 映射。
_TYPE_LABELS: Dict[QuestionType, str] = {
    QuestionType.SINGLE: "单选题",
    QuestionType.MULTIPLE: "多选题",
    QuestionType.JUDGE: "判断题",
    QuestionType.FILL: "填空题",
    QuestionType.SHORT: "简答题",
}


@dataclass
class Option:
    """选择题选项。

    Attributes:
        key: 选项键,如 "A"、"B"。
        text: 选项文本内容。
    """

    key: str
    text: str

    def to_dict(self) -> Dict[str, str]:
        """转为可 JSON 序列化的字典。"""
        return {"key": self.key, "text": self.text}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Option":
        """从字典构造选项。"""
        return cls(key=str(data.get("key", "")), text=str(data.get("text", "")))


@dataclass
class Question:
    """一道题目。

    Attributes:
        id: 全局唯一标识(uuid4 十六进制)。
        qtype: 题型。
        text: 题干文本。
        options: 选项列表,仅选择题(含判断题)使用;填空题/简答题为空。
        answer: 答案。选择题为选项键列表(如 ["A"]、["A","C"]);
            判断题固定为 ["A"](对)或 ["B"](错);
            填空题/简答题为可接受答案文本列表。
        analysis: 题目解析(可选)。
        source: 题目来源,如 "超星学习通-课程-作业名"(可选)。
        created_at: 创建时间(ISO 字符串)。
        updated_at: 最后修改时间(ISO 字符串)。
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    qtype: QuestionType = QuestionType.SINGLE
    text: str = ""
    options: List[Option] = field(default_factory=list)
    answer: List[str] = field(default_factory=list)
    analysis: str = ""
    source: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    # ------------------------------------------------------------------ #
    # 便捷属性
    # ------------------------------------------------------------------ #
    @property
    def is_choice(self) -> bool:
        """是否为选择题(单选/多选/判断)。"""
        return self.qtype in (QuestionType.SINGLE, QuestionType.MULTIPLE,
                              QuestionType.JUDGE)

    @property
    def option_map(self) -> Dict[str, str]:
        """选项键 -> 选项文本 的映射,便于快速展示。"""
        return {opt.key: opt.text for opt in self.options}

    def answer_text(self) -> str:
        """将答案渲染为人类可读文本。

        选择题返回选项键对应的文本(如 "A. 北京"),填空题/简答题返回
        答案文本本身;未设置标准答案时返回"未设置"(全系统统一兜底,
        避免空串在各处显示成空白)。
        """
        if not self.answer:
            return "未设置"
        if self.qtype == QuestionType.JUDGE:
            mapping = self.option_map
            return " / ".join(f"{key}. {mapping.get(key, '')}"
                              for key in self.answer)
        if self.is_choice:
            mapping = self.option_map
            return " / ".join(f"{key}. {mapping.get(key, '')}"
                              for key in self.answer)
        return " / ".join(self.answer)

    # ------------------------------------------------------------------ #
    # 序列化
    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return {
            "id": self.id,
            "qtype": self.qtype,
            "text": self.text,
            "options": [opt.to_dict() for opt in self.options],
            "answer": list(self.answer),
            "analysis": self.analysis,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Question":
        """从字典构造题目(字段缺失时使用默认值,保持向后兼容)。"""
        qtype_raw = str(data.get("qtype", QuestionType.SINGLE))
        try:
            qtype = QuestionType(qtype_raw)
        except ValueError:
            qtype = QuestionType.SINGLE
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            qtype=qtype,
            text=str(data.get("text", "")),
            options=[Option.from_dict(opt) for opt in data.get("options", [])],
            answer=[str(a) for a in data.get("answer", [])],
            analysis=str(data.get("analysis", "")),
            source=str(data.get("source", "")),
            created_at=str(data.get("created_at") or _now()),
            updated_at=str(data.get("updated_at") or _now()),
        )

    # ------------------------------------------------------------------ #
    # 校验
    # ------------------------------------------------------------------ #
    def validate(self, require_answer: bool = True) -> None:
        """校验题目数据合法性,不合法时抛出 ValueError。

        校验规则:
            * 题干不能为空;
            * 单选/多选至少两个选项,且答案必须来自选项键;
            * 单选/判断题答案只能有一个;
            * 多选题答案至少一个;
            * 判断题使用固定的"对/错"两个选项;
            * 填空题答案至少一个;
            * 简答题答案可以为空(表示无标准答案)。

        Args:
            require_answer: 是否强制要求答案非空。从外部导入(如学习通)
                的题目可能没有正确答案,此时传 False 允许跳过答案校验。
        """
        if not self.text or not self.text.strip():
            raise ValueError("题干不能为空")

        if self.qtype == QuestionType.JUDGE:
            self.options = [Option("A", "对"), Option("B", "错")]
            if require_answer and (len(self.answer) != 1 or
                                   self.answer[0] not in ("A", "B")):
                raise ValueError("判断题答案必须为: 对 或 错")
            return

        if self.qtype in (QuestionType.SINGLE, QuestionType.MULTIPLE):
            if len(self.options) < 2:
                raise ValueError("选择题至少需要两个选项")
            keys = [opt.key for opt in self.options]
            if len(set(keys)) != len(keys):
                raise ValueError("选项键不能重复")
            if require_answer and not self.answer:
                raise ValueError("选择题必须设置答案")
            invalid = [key for key in self.answer if key not in keys]
            if invalid:
                raise ValueError(f"答案包含不存在的选项: {', '.join(invalid)}")
            if require_answer and self.qtype == QuestionType.SINGLE \
                    and len(self.answer) != 1:
                raise ValueError("单选题只能有一个答案")
            return

        if self.qtype == QuestionType.FILL:
            if require_answer and not self.answer:
                raise ValueError("填空题必须设置答案")
            return

        # 简答题:答案允许为空。

    def match_keyword(self, keyword: str) -> bool:
        """判断题目是否包含关键词(用于检索)。

        匹配范围:题干、选项文本、答案文本、解析、来源,忽略大小写。
        """
        keyword = keyword.strip().lower()
        if not keyword:
            return True
        haystack = " ".join([
            self.text,
            " ".join(opt.text for opt in self.options),
            self.answer_text(),
            self.analysis,
            self.source,
        ]).lower()
        return keyword in haystack


def normalize_answer_text(raw: str) -> str:
    """规范化用户输入的答案文本。

    将中文逗号、顿号、空白等分隔符统一为英文逗号并去重空段,
    例如 "a、C ,b" -> "A,C,B"。
    """
    parts = re.split(r"[，,、;；\s]+", raw.strip().upper())
    return ",".join(part for part in parts if part)
