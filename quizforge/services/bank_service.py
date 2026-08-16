"""题库业务服务(多分类)。

题库按学科/课程分类,每分类独立 JSON 文件(见 storage.CategoryStore)。
本服务负责:
    * 分类管理(增删改查);
    * 各分类题目增删改查、检索、导入去重;
    * 内存控制:分类按需加载并缓存,最多同时保留 ``_CACHE_LIMIT`` 个
      分类(LRU),避免同时载入全部题库;
    * 文件一致性:访问时校验文件签名,文件被外部删除/修改自动重载。

界面层通过本服务访问题库,不直接操作存储文件。
"""

from __future__ import annotations

import copy
import datetime
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from quizforge.models import OPTION_KEYS, Option, Question, QuestionType
from quizforge.storage import (DEFAULT_CATEGORY_ID, CategoryStore)

#: 内存中最多同时保留的分类数(超过时按最近使用释放)。
_CACHE_LIMIT = 4

#: 题库文件超过该大小时记录加载警告(约 200MB)。
_LARGE_FILE_WARN_BYTES = 200 * 1024 * 1024

#: 错题子分类 id 前缀(虚拟分类,不落盘;如 "wrongbook:虚拟化id")。
WRONGBOOK_PREFIX = "wrongbook:"

#: 模块级日志。
_LOGGER = logging.getLogger(__name__)


def is_wrongbook_id(category_id: str) -> bool:
    """判断是否为「错题」虚拟分类 id(如 wrongbook:abc123)。"""
    return isinstance(category_id, str) and \
        category_id.startswith(WRONGBOOK_PREFIX)


def wrongbook_id_of(category_id: str) -> str:
    """返回某真实分类对应的「错题」虚拟分类 id。"""
    return f"{WRONGBOOK_PREFIX}{category_id}"


def real_category_of(category_id: str) -> Optional[str]:
    """错题虚拟分类 -> 其真实分类 id;非错题分类返回 None。"""
    if is_wrongbook_id(category_id):
        return category_id[len(WRONGBOOK_PREFIX):]
    return None


@dataclass
class CategoryInfo:
    """分类信息。

    Attributes:
        id: 分类 id。
        name: 分类名称。
        count: 该分类题目数量。
    """

    id: str
    name: str
    count: int


def _now() -> str:
    """返回当前本地时间的 ISO 字符串。"""
    return datetime.datetime.now().isoformat(timespec="seconds")


class QuestionBankService:
    """分类化题库服务(单例使用)。

    Attributes:
        store: 底层分类存储。
    """

    def __init__(self, store: CategoryStore) -> None:
        """初始化题库服务。

        Args:
            store: 底层分类存储。
        """
        self.store = store
        self._cache: Dict[str, List[Question]] = {}
        self._signatures: Dict[str, Optional[tuple]] = {}
        self._order: List[str] = []

    # ================================================================== #
    # 分类管理
    # ================================================================== #
    def list_categories(self) -> List[CategoryInfo]:
        """返回分类列表(含各分类题目数)。

        题目数优先读缓存;未缓存分类直接从文件统计,不载入内存缓存,
        避免遍历全部分类时突破缓存上限。

        每个真实分类后追加其「错题」虚拟分类(如「虚拟化」之后是
        「虚拟化错题」),聚合该分类的错题索引,可像普通分类一样
        参与抽题/答题。
        """
        result: List[CategoryInfo] = []
        for meta in self.store.list_categories():
            category_id = meta["id"]
            if category_id in self._cache:
                count = len(self._cache[category_id])
            else:
                count = len(self.store.load_questions(category_id))
            result.append(CategoryInfo(
                id=category_id, name=meta["name"], count=count))
            result.append(CategoryInfo(
                id=wrongbook_id_of(category_id),
                name=f"{meta['name']}错题",
                count=len(self._wrong_questions(category_id))))
        return result

    def get_category(self, category_id: str) -> Optional[CategoryInfo]:
        """按 id 获取分类信息(含「错题」虚拟分类)。"""
        real_id = real_category_of(category_id)
        if real_id is not None:
            meta = self.store.get_category(real_id)
            if meta is None:
                return None
            return CategoryInfo(
                id=category_id, name=f"{meta['name']}错题",
                count=len(self._wrong_questions(real_id)))
        meta = self.store.get_category(category_id)
        if meta is None:
            return None
        return CategoryInfo(id=meta["id"], name=meta["name"],
                            count=self.count(category_id))

    def create_category(self, name: str) -> CategoryInfo:
        """创建分类(同名分类存在时复用)。"""
        meta = self.store.create_category(name)
        return CategoryInfo(id=meta["id"], name=meta["name"], count=0)

    def rename_category(self, category_id: str, name: str) -> None:
        """重命名分类。"""
        self.store.rename_category(category_id, name)

    def delete_category(self, category_id: str) -> bool:
        """删除分类(连同题目文件)。"""
        if self.store.delete_category(category_id):
            self._cache.pop(category_id, None)
            self._signatures.pop(category_id, None)
            if category_id in self._order:
                self._order.remove(category_id)
            return True
        return False

    # ================================================================== #
    # 内部:分类加载/缓存/文件一致性
    # ================================================================== #
    def _ensure_category(self, category_id: str) -> None:
        """确保分类存在,否则抛 KeyError。"""
        real_id = real_category_of(category_id)
        if real_id is not None:
            category_id = real_id
        if self.store.get_category(category_id) is None:
            raise KeyError(f"分类不存在: {category_id}")

    def _load(self, category_id: str) -> List[Question]:
        """加载分类题目(带缓存与 LRU 释放)。

        「错题」虚拟分类不缓存,每次实时读取真实分类的错题索引。
        文件被外部删除/修改时自动重新加载。
        """
        real_id = real_category_of(category_id)
        if real_id is not None:
            return self._wrong_questions(real_id)
        signature = self.store.file_signature(category_id)
        if category_id in self._cache:
            if signature == self._signatures.get(category_id):
                # 命中缓存:更新最近使用顺序。
                self._order.remove(category_id)
                self._order.append(category_id)
                return self._cache[category_id]
            self._cache.pop(category_id, None)  # 文件已变化,重新加载

        questions = self.store.load_questions(category_id)
        self._cache[category_id] = questions
        self._signatures[category_id] = self.store.file_signature(category_id)
        if category_id in self._order:
            self._order.remove(category_id)
        self._order.append(category_id)
        self._evict_if_needed(category_id)
        self._warn_if_large(category_id)
        return questions

    def _wrong_questions(self, category_id: str) -> List[Question]:
        """按真实分类的错题索引加载错题题目(已删除的题目跳过)。"""
        by_id = {q.id: q for q in self._load(category_id)}
        result: List[Question] = []
        for question_id in self.store.load_wrong_ids(category_id):
            question = by_id.get(question_id)
            if question is not None:
                result.append(copy.deepcopy(question))
        return result

    def _evict_if_needed(self, keep_id: str) -> None:
        """缓存超过上限时,释放最久未使用的分类(保留当前)。"""
        while len(self._cache) > _CACHE_LIMIT and len(self._order) > 1:
            oldest = self._order[0]
            if oldest == keep_id:
                oldest = self._order[1]
            self._cache.pop(oldest, None)
            self._signatures.pop(oldest, None)
            self._order.remove(oldest)

    def _save(self, category_id: str) -> None:
        """将分类题目写盘并刷新签名与索引统计。"""
        questions = self._cache.get(category_id)
        if questions is None:
            questions = self.store.load_questions(category_id)
        self.store.save_questions(category_id, questions)
        self._signatures[category_id] = self.store.file_signature(category_id)
        self.store.update_index_stats(category_id, len(questions))

    def _warn_if_large(self, category_id: str) -> None:
        """分类题库文件过大时记录警告。"""
        try:
            size = os.path.getsize(self.store.category_file(category_id))
        except (OSError, KeyError):
            return
        if size > _LARGE_FILE_WARN_BYTES:
            _LOGGER.warning(
                "分类 [%s] 题库文件较大(%.0f MB),JSON 全量加载与保存可能"
                "较慢且占用较多内存;GB 级题库建议拆分导入或改用数据库存储",
                category_id, size / 1024 / 1024)

    # ================================================================== #
    # 查询
    # ================================================================== #
    def questions(self, category_id: str) -> List[Question]:
        """返回指定分类的全部题目(副本)。"""
        return [copy.deepcopy(q) for q in self._load(category_id)]

    def list_questions(self) -> List[Question]:
        """返回"未分类"分类的题目(兼容旧调用)。"""
        return self.questions(DEFAULT_CATEGORY_ID)

    def get_question(self, question_id: str,
                     category_id: str = DEFAULT_CATEGORY_ID) -> Optional[Question]:
        """按 id 查找题目(指定分类)。"""
        for question in self._load(category_id):
            if question.id == question_id:
                return copy.deepcopy(question)
        return None

    def count(self, category_id: str = DEFAULT_CATEGORY_ID) -> int:
        """指定分类的题目总数。"""
        return len(self._load(category_id))

    def count_by_type(self,
                      category_id: str = DEFAULT_CATEGORY_ID) -> dict:
        """按题型统计题目数量,返回 {题型: 数量}。"""
        stats = {qtype: 0 for qtype in QuestionType}
        for question in self._load(category_id):
            stats[question.qtype] += 1
        return stats

    def search(self,
               keyword: str = "",
               qtype: Optional[QuestionType] = None,
               category_id: str = DEFAULT_CATEGORY_ID,
               limit: Optional[int] = None,
               offset: int = 0) -> List[Question]:
        """按关键词与题型过滤题目(支持分页)。

        Args:
            keyword: 关键词,匹配题干/选项/答案/解析/来源;空串表示不过滤。
            qtype: 题型过滤;None 表示不过滤。
            category_id: 目标分类。
            limit: 单页条数上限;None 不限。
            offset: 跳过前 N 条匹配结果(与 limit 配合分页)。

        Returns:
            匹配的题目列表(第 offset+1 ~ offset+limit 条)。
        """
        result = []
        skipped = 0
        for question in self._load(category_id):
            if qtype is not None and question.qtype != qtype:
                continue
            if not question.match_keyword(keyword):
                continue
            if skipped < offset:
                skipped += 1
                continue
            result.append(copy.deepcopy(question))
            if limit is not None and len(result) >= limit:
                break
        return result

    def count_matches(self,
                      keyword: str = "",
                      qtype: Optional[QuestionType] = None,
                      category_id: str = DEFAULT_CATEGORY_ID) -> int:
        """统计匹配关键词与题型的题目总数(分页时用于计算总页数)。"""
        total = 0
        for question in self._load(category_id):
            if qtype is not None and question.qtype != qtype:
                continue
            if not question.match_keyword(keyword):
                continue
            total += 1
        return total

    def find_question_anywhere(self, question_id: str) -> Optional[Question]:
        """跨分类按 id 查找题目(文件选题时使用)。"""
        for meta in self.store.list_categories():
            question = self.get_question(question_id, meta["id"])
            if question is not None:
                return question
        return None

    def find_category_of(self, question_id: str) -> Optional[str]:
        """按 id 跨分类定位题目所属分类(错题按分类记录时使用)。

        Returns:
            分类 id;题目不存在时返回 None。
        """
        for meta in self.store.list_categories():
            if self.get_question(question_id, meta["id"]) is not None:
                return meta["id"]
        return None

    # ================================================================== #
    # 错题记录(按分类,存放在分类文件内部 wrong_ids 字段)
    # ================================================================== #
    def wrong_ids(self, category_id: str) -> List[str]:
        """返回指定分类的错题 id 列表(按加入顺序)。

        「XX错题」虚拟分类委派到其真实分类。
        """
        real_id = real_category_of(category_id) or category_id
        self._ensure_category(real_id)
        return self.store.load_wrong_ids(real_id)

    def add_wrong(self, category_id: str, question_id: str) -> bool:
        """把题目加入指定分类的错题记录(去重)。

        Returns:
            是否新增(已存在返回 False)。
        """
        ids = self.wrong_ids(category_id)
        if question_id in ids:
            return False
        ids.append(question_id)
        self.store.save_wrong_ids(category_id, ids)
        return True

    def add_wrong_many(self, category_id: str,
                       question_ids: List[str]) -> int:
        """批量加入错题记录(去重)。

        Returns:
            新增数量。
        """
        ids = self.wrong_ids(category_id)
        added = 0
        for question_id in question_ids:
            if question_id not in ids:
                ids.append(question_id)
                added += 1
        if added:
            self.store.save_wrong_ids(category_id, ids)
        return added

    def remove_wrong(self, category_id: str, question_id: str) -> bool:
        """从错题记录中移除题目。

        Returns:
            是否存在并被移除。
        """
        ids = self.wrong_ids(category_id)
        if question_id in ids:
            ids.remove(question_id)
            self.store.save_wrong_ids(category_id, ids)
            return True
        return False

    def clear_wrong(self, category_id: str) -> None:
        """清空指定分类的错题记录。"""
        self._ensure_category(category_id)
        self.store.save_wrong_ids(category_id, [])

    def wrong_questions(self, category_id: str) -> List[Question]:
        """返回指定分类错题记录对应的题目对象列表。

        错题 id 对应的题目已从题库删除时自动跳过(记录保留,重练时
        自然清理,不回写)。「XX错题」虚拟分类委派到其真实分类。
        """
        real_id = real_category_of(category_id)
        if real_id is not None:
            return self._wrong_questions(real_id)
        return self._wrong_questions(category_id)

    def find_questions_by_text(self, text: str) -> List[Question]:
        """跨分类按题干精确匹配题目(文件选题时使用)。"""
        text = text.strip()
        if not text:
            return []
        result: List[Question] = []
        for meta in self.store.list_categories():
            for question in self._load(meta["id"]):
                if question.text.strip() == text:
                    result.append(copy.deepcopy(question))
        return result

    # ================================================================== #
    # 增删改
    # ================================================================== #
    def add_question(self, question: Question,
                     category_id: str = DEFAULT_CATEGORY_ID) -> Question:
        """新增题目到指定分类并持久化。"""
        questions = self._load(category_id)
        question = self._normalize(question)
        # 防御:id 冲突时重新生成(理论上 uuid 冲突概率极低)。
        existing_ids = {q.id for q in questions}
        while question.id in existing_ids:
            question.id = uuid.uuid4().hex
        questions.append(question)
        self._save(category_id)
        return copy.deepcopy(question)

    def update_question(self, question_id: str, question: Question,
                        category_id: str = DEFAULT_CATEGORY_ID) -> Question:
        """按 id 更新指定分类中的题目。

        允许保留无正确答案的题目(如从学习通导入、答案缺失的题):
        编辑这类题时即使未补答案也应能保存,避免"编辑保存即报错"。
        """
        questions = self._load(category_id)
        question = self._normalize(question, require_answer=False)
        for index, existing in enumerate(questions):
            if existing.id == question_id:
                question.id = question_id
                questions[index] = question
                self._save(category_id)
                return copy.deepcopy(question)
        raise KeyError(f"题目不存在: {question_id}")

    def delete_question(self, question_id: str,
                        category_id: str = DEFAULT_CATEGORY_ID) -> bool:
        """按 id 删除指定分类中的题目。

        若该题在错题记录中,一并移除(避免残留失效错题 id)。
        """
        questions = self._load(category_id)
        for index, question in enumerate(questions):
            if question.id == question_id:
                del questions[index]
                self._save(category_id)
                self.remove_wrong(category_id, question_id)
                return True
        return False

    def merge_questions(self, questions: List[Question],
                        category_id: str = DEFAULT_CATEGORY_ID) -> "ImportSummary":
        """将题目合并进指定分类,按(题型, 题干)去重。

        导入的题目允许没有正确答案(如学习通作业页常不显示答案)。

        Returns:
            导入统计信息(新增数 / 跳过数 / 跳过题目题干)。
        """
        existing = self._load(category_id)
        existing_keys = {(q.qtype, q.text.strip()) for q in existing}
        added = 0
        skipped = 0
        skipped_questions: List[str] = []
        for raw in questions:
            try:
                question = self._normalize(raw, require_answer=False)
            except ValueError:
                skipped += 1
                raw_text = getattr(raw, "text", "")
                if raw_text and len(skipped_questions) < \
                        ImportSummary.MAX_SKIPPED_DETAILS:
                    skipped_questions.append(str(raw_text).strip()[:60])
                continue
            key = (question.qtype, question.text.strip())
            if key in existing_keys:
                skipped += 1
                if len(skipped_questions) < \
                        ImportSummary.MAX_SKIPPED_DETAILS:
                    skipped_questions.append(question.text[:60])
                continue
            existing_keys.add(key)
            existing.append(question)
            added += 1
        if added:
            self._save(category_id)
        return ImportSummary(added=added, skipped=skipped,
                             skipped_questions=skipped_questions)

    # ================================================================== #
    # 内部工具
    # ================================================================== #
    def _normalize(self, question: Question,
                   require_answer: bool = True) -> Question:
        """规范化题目:去空白、生成选项键、判断题固定选项、写入时间戳。"""
        normalized = copy.deepcopy(question)
        normalized.text = normalized.text.strip()
        normalized.analysis = normalized.analysis.strip()
        normalized.source = normalized.source.strip()

        if normalized.qtype == QuestionType.JUDGE:
            normalized.options = [Option("A", "对"), Option("B", "错")]
        elif normalized.is_choice:
            # 重建选项键为 A/B/C...(按顺序),并同步映射答案键,
            # 否则外部导入的非常规选项键(如 1/2/3)会导致答案
            # 校验失败而被静默跳过,题目丢失。
            cleaned = [opt for opt in normalized.options if opt.text.strip()]
            old_to_new = {
                opt.key: OPTION_KEYS[index]
                for index, opt in enumerate(cleaned)
            }
            normalized.options = [
                Option(OPTION_KEYS[index], opt.text.strip())
                for index, opt in enumerate(cleaned)
            ]
            normalized.answer = [
                old_to_new.get(a, a) for a in normalized.answer
            ]

        normalized.answer = [str(a).strip() for a in normalized.answer]
        normalized.answer = [a for a in normalized.answer if a]
        normalized.validate(require_answer=require_answer)
        normalized.updated_at = _now()
        return normalized


class ImportSummary:
    """导入结果统计。

    Attributes:
        added: 成功新增的题目数。
        skipped: 被跳过的题目数(重复或数据不合法)。
        skipped_questions: 被跳过题目的题干列表(重复/非法,便于
            发现"作业更新了但题库没变");非法条目记录原始题干
            (若能取得)。
    """

    #: 跳过详情最多记录的条数(避免超大题量时内存/渲染膨胀)。
    MAX_SKIPPED_DETAILS = 50

    def __init__(self, added: int, skipped: int,
                 skipped_questions: Optional[List[str]] = None) -> None:
        self.added = added
        self.skipped = skipped
        self.skipped_questions = list(skipped_questions or [])

    def skipped_detail_text(self) -> str:
        """把跳过的题目格式化为可读文本(截断到上限,附总数)。"""
        if not self.skipped_questions:
            return ""
        lines = []
        for text in self.skipped_questions[:self.MAX_SKIPPED_DETAILS]:
            lines.append(f"  - {text}")
        remaining = len(self.skipped_questions) - self.MAX_SKIPPED_DETAILS
        if remaining > 0:
            lines.append(f"  … 其余 {remaining} 条略")
        return "\n".join(lines)
