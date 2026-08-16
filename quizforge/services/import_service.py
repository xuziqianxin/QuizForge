"""题目导入导出服务。

支持三种数据来源:
    * JSON 文件导入(兼容"题目字典列表"或 {"questions": [...]} 两种格式);
    * JSON 文件导出;
    * 学习通拉取结果导入(直接复用合并逻辑,由 UI 层调用)。

所有导入最终都通过 ``QuestionBankService.merge_questions`` 去重合并,
保证规则单一。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from quizforge.models import Question
from quizforge.services.bank_service import ImportSummary, QuestionBankService


class ImportFormatError(ValueError):
    """JSON 文件格式不符合要求时抛出。"""


class ImportService:
    """题库导入导出服务。"""

    def __init__(self, bank: QuestionBankService) -> None:
        """初始化导入服务。

        Args:
            bank: 目标题库服务。
        """
        self.bank = bank

    # ------------------------------------------------------------------ #
    def import_json_file(self, path: str,
                         category_id: str = "default") -> ImportSummary:
        """从 JSON 文件导入题目到指定分类。

        支持的顶层结构::

            [题目字典, ...]                     # 直接是列表
            {"questions": [题目字典, ...]}      # 带版本包装

        Args:
            path: JSON 文件路径。
            category_id: 目标分类 id(默认"未分类")。

        Returns:
            导入统计。

        Raises:
            ImportFormatError: 文件不存在或格式无法解析。
        """
        if not os.path.isfile(path):
            raise ImportFormatError(f"文件不存在: {path}")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            raise ImportFormatError(f"无法解析 JSON 文件: {exc}") from exc

        items = raw.get("questions", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            raise ImportFormatError("JSON 顶层必须是题目列表或包含 "
                                    "'questions' 字段的对象")
        questions: List[Question] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ImportFormatError(f"第 {index + 1} 项不是对象")
            try:
                questions.append(Question.from_dict(item))
            except (TypeError, ValueError) as exc:
                raise ImportFormatError(
                    f"第 {index + 1} 项字段非法: {exc}") from exc
        return self.bank.merge_questions(questions, category_id)

    # ------------------------------------------------------------------ #
    def export_json_file(self, path: str, questions: List[Question]) -> int:
        """将题目导出为 JSON 文件。

        Args:
            path: 输出文件路径。
            questions: 待导出的题目。

        Returns:
            导出的题目数量。
        """
        payload = {
            "version": 1,
            "questions": [q.to_dict() for q in questions],
        }
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return len(questions)


def parse_question_dict(data: Dict[str, Any]) -> Question:
    """将外部字典解析为题目对象(供学习通解析器等复用)。

    Args:
        data: 题目字典。

    Returns:
        题目对象。
    """
    return Question.from_dict(data)
