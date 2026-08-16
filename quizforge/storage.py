"""分类化题库存储层。

题库按学科/课程分为多个分类,每个分类一个独立的 JSON 文件,互不影响:

    data/
      bank/
        index.json     分类索引 {version, categories: [{id, name, file}]}
        <id>.json      每分类一个题库文件 {version, questions: [...]}
      backup/          数据自动备份(每次写入前保留最近若干份)

好处:
    * 不同学科互不干扰,删除/导入只影响对应分类文件;
    * 单个文件体积小,加载快,避免超大文件一次性载入内存;
    * 旧版本的单文件题库(data/questions.json)首次启动时自动迁移为
      "未分类"分类;
    * 所有数据文件在写入前自动备份到 data/backup/,防止不可逆操作
      导致数据损坏(误删/误改后可从备份恢复)。

所有写入均采用"临时文件 + 原子替换",避免中途崩溃损坏数据。
"""

from __future__ import annotations

import datetime
import glob
import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from quizforge.models import Question

#: 题库格式版本。
STORE_VERSION = 1

#: 分类索引文件名。
INDEX_FILE_NAME = "index.json"

#: 默认分类。
DEFAULT_CATEGORY_ID = "default"
DEFAULT_CATEGORY_NAME = "默认分类"

#: 自动备份目录名(相对数据目录)。
BACKUP_DIR_NAME = "backup"

#: 每个文件保留的最近备份份数。
MAX_BACKUPS = 5

#: 模块级日志。
_LOGGER = logging.getLogger(__name__)


def backup_file(path: str, backup_dir: str,
                max_backups: int = MAX_BACKUPS) -> None:
    """写入前备份现有文件,保留最近若干份。

    仅在目标文件存在时备份;备份文件带时间戳命名,超出保留份数的旧
    备份自动清理。备份失败不阻断写入(记录警告),避免备份问题导致
    正常保存失败。

    Args:
        path: 待备份的文件路径。
        backup_dir: 备份目录。
        max_backups: 每个文件保留的最近备份份数。
    """
    if not os.path.isfile(path):
        return
    try:
        os.makedirs(backup_dir, exist_ok=True)
        basename = os.path.basename(path)
        # 毫秒级时间戳:同一秒内多次写入各自独立备份,不互相覆盖。
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S%f")
        backup_path = os.path.join(backup_dir, f"{basename}.{timestamp}.bak")
        shutil.copy2(path, backup_path)
        # 清理旧备份,只保留最近 N 份。
        backups = sorted(glob.glob(
            os.path.join(backup_dir, f"{basename}.*.bak")))
        for old in backups[:-max_backups]:
            try:
                os.unlink(old)
            except OSError:
                pass
    except OSError:
        # 备份失败不应阻断正常写入。
        _LOGGER.warning("备份失败(不影响本次写入): %s", path)


#: 位于数据根目录(而非 data/bank/)的数据文件名集合。
_ROOT_DATA_FILES = ("config.json", "templates.json", "chaoxing_cookies.json")


@dataclass
class BackupEntry:
    """备份文件条目(用于备份恢复界面)。

    Attributes:
        original_name: 原始数据文件名(如 ``default.json``)。
        timestamp: 备份时间戳字符串(如 ``20260815_123456789012``)。
        path: 备份文件完整路径。
        size: 备份文件字节数。
        target: 恢复目标文件完整路径。
    """

    original_name: str
    timestamp: str
    path: str
    size: int
    target: str


def list_backups(data_dir: str) -> List[BackupEntry]:
    """列出 ``data/backup/`` 中全部备份文件(按文件名+时间排序)。

    Args:
        data_dir: 数据根目录(备份目录为 ``data_dir/backup``)。

    Returns:
        备份条目列表,按原始文件名分组、时间升序排列。
    """
    backup_dir = os.path.join(data_dir, BACKUP_DIR_NAME)
    entries: List[BackupEntry] = []
    for path in sorted(glob.glob(os.path.join(backup_dir, "*.bak"))):
        basename = os.path.basename(path)
        # 备份命名 <原名>.<时间戳>.bak,时间戳为 8位日期_6位时分秒+6位微秒。
        match = re.match(r"^(?P<orig>.+)\.(?P<ts>\d{8}_\d{6}\d{6})\.bak$",
                         basename)
        if not match:
            continue
        original_name = match.group("orig")
        timestamp = match.group("ts")
        entries.append(BackupEntry(
            original_name=original_name,
            timestamp=timestamp,
            path=path,
            size=os.path.getsize(path),
            target=backup_target_path(data_dir, original_name),
        ))
    return entries


def backup_target_path(data_dir: str, original_name: str) -> str:
    """根据原始数据文件名推导恢复目标路径。

    ``config.json`` / ``templates.json`` / ``chaoxing_cookies.json`` 位于
    数据根目录;其余(分类题库 ``<id>.json``、``index.json``)位于
    ``data/bank/``。
    """
    if original_name in _ROOT_DATA_FILES:
        return os.path.join(data_dir, original_name)
    return os.path.join(data_dir, "bank", original_name)


def restore_backup(entry: BackupEntry, data_dir: str) -> str:
    """将一份备份恢复到其目标位置。

    恢复前自动备份当前目标文件(写入 ``data/backup/``),恢复失败时
    当前文件不受影响。若恢复的是分类索引,顺带刷新其统计信息
    (按恢复后的分类文件实读 count/total)。

    Args:
        entry: 备份条目(list_backups 返回)。
        data_dir: 数据根目录。

    Returns:
        恢复后的目标文件路径。

    Raises:
        OSError: 复制失败。
    """
    backup_dir = os.path.join(data_dir, BACKUP_DIR_NAME)
    # 恢复前备份当前文件,误恢复后可再还原。
    backup_file(entry.target, backup_dir)
    os.makedirs(os.path.dirname(entry.target), exist_ok=True)
    # 备份当前文件后,最旧备份可能被清理(保留上限);若所选备份已
    # 被清理,回退到该原始文件仍存在的任一备份,保证恢复可用。
    source_path = entry.path
    if not os.path.isfile(source_path):
        candidates = sorted(glob.glob(os.path.join(
            backup_dir, f"{entry.original_name}.*.bak")))
        if candidates:
            source_path = candidates[-1]
        else:
            raise OSError(f"备份文件不存在且无其他可用备份: "
                          f"{entry.original_name}")
    shutil.copy2(source_path, entry.target)
    # 若恢复的是分类索引,按恢复后的分类文件实读刷新统计。
    if os.path.basename(entry.target) == INDEX_FILE_NAME:
        _refresh_index_stats_from_disk(entry.target, data_dir)
    return entry.target


def _refresh_index_stats_from_disk(index_path: str, data_dir: str) -> None:
    """按磁盘上的分类题库文件就地刷新 index.json 的统计信息。"""
    try:
        with open(index_path, "r", encoding="utf-8") as fh:
            index = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(index, dict):
        return
    total = 0
    bank_dir = os.path.join(data_dir, "bank")
    for meta in index.get("categories", []):
        try:
            with open(os.path.join(bank_dir, meta["file"]),
                      "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            items = raw.get("questions", []) if isinstance(raw, dict) else []
            count = len(items) if isinstance(items, list) else 0
        except (OSError, json.JSONDecodeError, KeyError):
            count = 0
        meta["count"] = count
        total += count
    index["total"] = total
    try:
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(index_path), suffix=".tmp",
            prefix="index_")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, index_path)
    except OSError:
        pass


class CategoryStore:
    """分类化题库文件读写器。

    Attributes:
        data_dir: 数据根目录。
        bank_dir: 分类题库目录(data_dir/bank)。
        index_path: 分类索引文件路径。
    """

    def __init__(self, data_dir: str) -> None:
        """初始化分类存储。

        Args:
            data_dir: 数据根目录。
        """
        self.data_dir = data_dir
        self.bank_dir = os.path.join(data_dir, "bank")
        self.index_path = os.path.join(self.bank_dir, INDEX_FILE_NAME)
        self._migrate_legacy()

    # ------------------------------------------------------------------ #
    # 分类索引
    # ------------------------------------------------------------------ #
    def list_categories(self) -> List[Dict[str, str]]:
        """返回全部分类元信息 [{id, name, file}, ...]。"""
        return self._read_index().get("categories", [])

    def get_category(self, category_id: str) -> Optional[Dict[str, str]]:
        """按 id 查找分类;不存在返回 None。"""
        for meta in self.list_categories():
            if meta["id"] == category_id:
                return dict(meta)
        return None

    def create_category(self, name: str) -> Dict[str, str]:
        """创建分类(名称已存在时复用同名分类)。

        Args:
            name: 分类名称(学习通导入时使用课程名)。

        Returns:
            分类元信息。
        """
        name = name.strip()
        if not name:
            raise ValueError("分类名称不能为空")
        for meta in self.list_categories():
            if meta["name"] == name:
                return dict(meta)
        category_id = uuid.uuid4().hex[:12]
        meta = {
            "id": category_id,
            "name": name,
            "file": f"{category_id}.json",
        }
        index = self._read_index()
        index["categories"].append(meta)
        self._write_index(index)
        # 初始化空题库文件。
        self.save_questions(category_id, [])
        return dict(meta)

    def rename_category(self, category_id: str, name: str) -> None:
        """重命名分类。"""
        name = name.strip()
        if not name:
            raise ValueError("分类名称不能为空")
        index = self._read_index()
        for meta in index["categories"]:
            if meta["id"] == category_id:
                meta["name"] = name
                self._write_index(index)
                return
        raise KeyError(f"分类不存在: {category_id}")

    def delete_category(self, category_id: str) -> bool:
        """删除分类(连同题库文件,错题索引随文件一并删除)。

        删除是不可逆操作:删除分类文件前自动备份,误删后可从
        ``data/backup/`` 恢复。

        默认分类(未分类)是题库的兜底分类,不可删除。
        """
        if category_id == DEFAULT_CATEGORY_ID:
            return False
        index = self._read_index()
        for pos, meta in enumerate(index["categories"]):
            if meta["id"] == category_id:
                path = os.path.join(self.bank_dir, meta["file"])
                backup_file(path,
                            os.path.join(self.data_dir, BACKUP_DIR_NAME))
                del index["categories"][pos]
                self._write_index(index)
                try:
                    os.unlink(path)
                except OSError:
                    pass
                return True
        return False

    # ------------------------------------------------------------------ #
    # 题目文件
    # ------------------------------------------------------------------ #
    def category_file(self, category_id: str) -> str:
        """返回分类题库文件路径。"""
        meta = self.get_category(category_id)
        if meta is None:
            raise KeyError(f"分类不存在: {category_id}")
        return os.path.join(self.bank_dir, meta["file"])

    def load_questions(self, category_id: str) -> List[Question]:
        """加载指定分类的题目。

        Returns:
            题目列表;文件不存在或损坏时返回空列表(跳过非法条目,
            避免崩溃)。
        """
        path = self.category_file(category_id)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        items = raw.get("questions", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        questions: List[Question] = []
        for item in items:
            if isinstance(item, dict):
                questions.append(Question.from_dict(item))
        return questions

    def save_questions(self, category_id: str,
                       questions: List[Question]) -> None:
        """将题目列表原子写入指定分类文件(写入前自动备份)。

        保留该分类的错题索引字段(``wrong_ids``),题目增删改不影响
        错题记录。
        """
        path = self.category_file(category_id)
        backup_file(path, os.path.join(self.data_dir, BACKUP_DIR_NAME))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = json.dumps(
            {
                "version": STORE_VERSION,
                "questions": [q.to_dict() for q in questions],
                "wrong_ids": self.load_wrong_ids(category_id),
            },
            ensure_ascii=False,
            indent=2,
        )
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(path), suffix=".tmp", prefix="bank_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def file_signature(self, category_id: str) -> Optional[tuple]:
        """返回分类题库文件的签名(大小, 修改时间);不存在返回 None。"""
        try:
            stat = os.stat(self.category_file(category_id))
            return (stat.st_size, stat.st_mtime_ns)
        except (OSError, KeyError):
            return None

    # ------------------------------------------------------------------ #
    # 错题索引(存放在分类题库文件内部的 wrong_ids 字段,只存题目 id)
    # ------------------------------------------------------------------ #
    def load_wrong_ids(self, category_id: str) -> List[str]:
        """加载指定分类的错题索引(题目 id 列表,按加入顺序)。

        Returns:
            错题 id 列表;文件不存在或损坏时返回空列表。
        """
        try:
            with open(self.category_file(category_id), "r",
                      encoding="utf-8") as fh:
                raw = json.load(fh)
            ids = raw.get("wrong_ids", []) if isinstance(raw, dict) else []
            return [str(i) for i in ids if isinstance(i, str)]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def save_wrong_ids(self, category_id: str, ids: List[str]) -> None:
        """原子写入分类错题索引(写入前自动备份)。

        错题索引只记录题目 id(去重后),不复制题目内容,加载错题时
        按 id 从题库文件读取,题目增删改后自动跟随最新内容。
        """
        path = self.category_file(category_id)
        backup_file(path, os.path.join(self.data_dir, BACKUP_DIR_NAME))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = json.dumps(
            {
                "version": STORE_VERSION,
                "questions": [q.to_dict() for q in
                              self.load_questions(category_id)],
                "wrong_ids": list(ids),
            },
            ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(path), suffix=".tmp", prefix="bank_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def _read_index(self) -> Dict:
        """读取分类索引(文件不存在时返回默认结构)。

        索引文件损坏时将其备份为 ``index.json.corrupt`` 后返回默认
        结构——避免后续写入索引时覆盖丢失原有分类元信息(分类文件
        仍在磁盘,可通过备份手动恢复)。
        """
        try:
            with open(self.index_path, "r", encoding="utf-8") as fh:
                index = json.load(fh)
            if isinstance(index, dict) and isinstance(
                    index.get("categories"), list):
                changed = False
                # 旧版默认分类名为"未分类",统一改为"默认分类"(仅改显示名,
                # id 不变,不影响数据文件)。
                for meta in index["categories"]:
                    if meta.get("id") == DEFAULT_CATEGORY_ID and \
                            meta.get("name") == "未分类":
                        meta["name"] = DEFAULT_CATEGORY_NAME
                        changed = True
                # 兜底:索引缺少默认分类时补入(旧数据/外部修改可能
                # 丢失 default 项,导致下拉框看不到默认分类)。
                if not any(meta.get("id") == DEFAULT_CATEGORY_ID
                           for meta in index["categories"]):
                    index["categories"].insert(0, {
                        "id": DEFAULT_CATEGORY_ID,
                        "name": DEFAULT_CATEGORY_NAME,
                        "file": f"{DEFAULT_CATEGORY_ID}.json",
                    })
                    changed = True
                if changed:
                    self._write_index(index)
                # 兜底:默认分类题库文件缺失时直接初始化空文件。
                # 不调用 save_questions(其内部经 category_file ->
                # get_category -> _read_index 会无限递归)。单独捕获,
                # 避免被外层异常处理吞掉。
                try:
                    default_path = os.path.join(
                        self.bank_dir, f"{DEFAULT_CATEGORY_ID}.json")
                    if not os.path.isfile(default_path):
                        os.makedirs(self.bank_dir, exist_ok=True)
                        payload = json.dumps(
                            {"version": STORE_VERSION, "questions": []},
                            ensure_ascii=False, indent=2)
                        fd, tmp_path = tempfile.mkstemp(
                            dir=self.bank_dir, suffix=".tmp",
                            prefix="bank_")
                        try:
                            with os.fdopen(fd, "w",
                                           encoding="utf-8") as fh:
                                fh.write(payload)
                            os.replace(tmp_path, default_path)
                        except OSError:
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                            raise
                except OSError:
                    _LOGGER.warning(
                        "默认分类题库文件初始化失败(不影响启动)")
                return index
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            if os.path.isfile(self.index_path) and not isinstance(
                    exc, FileNotFoundError):
                try:
                    os.replace(self.index_path, self.index_path + ".corrupt")
                except OSError:
                    pass
        return {
            "version": STORE_VERSION,
            "categories": [
                {"id": DEFAULT_CATEGORY_ID,
                 "name": DEFAULT_CATEGORY_NAME,
                 "file": f"{DEFAULT_CATEGORY_ID}.json"}
            ],
        }

    def _write_index(self, index: Dict) -> None:
        """原子写入分类索引(写入前自动备份)。

        写入前刷新统计信息:每个分类的 ``count``(题目数)与顶层
        ``total``(总题目数),保证索引中的数字与题库一致。
        """
        backup_file(self.index_path,
                    os.path.join(self.data_dir, BACKUP_DIR_NAME))
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        self._refresh_stats(index)
        self._dump_index(index)

    def update_index_stats(self, category_id: str, count: int) -> None:
        """题目增删后轻量更新索引统计(不备份,避免频繁写盘噪音)。

        分类结构变化(新建/重命名/删除)时由 ``_write_index`` 全量刷新;
        题目增删时调用本方法只更新受影响分类的 ``count`` 与顶层
        ``total``。
        """
        try:
            index = self._read_index()
        except (FileNotFoundError, OSError):
            return
        total = 0
        changed = False
        for meta in index.get("categories", []):
            if meta.get("id") == category_id:
                meta["count"] = count
                changed = True
            total += int(meta.get("count", 0))
        if changed:
            index["total"] = total
            self._dump_index(index)

    def _refresh_stats(self, index: Dict) -> None:
        """就地刷新索引中的题目统计(分类 count + 顶层 total)。

        直接按 index 中的 file 字段统计,不经过 category_file ->
        get_category -> list_categories -> _read_index 链路,避免与
        _write_index 互相递归。
        """
        total = 0
        for meta in index.get("categories", []):
            try:
                path = os.path.join(self.bank_dir, meta["file"])
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                items = raw.get("questions", []) if isinstance(raw, dict) \
                    else []
                count = len(items) if isinstance(items, list) else 0
            except (OSError, json.JSONDecodeError, KeyError):
                count = 0
            meta["count"] = count
            total += count
        index["total"] = total

    def _dump_index(self, index: Dict) -> None:
        """原子写入索引 JSON(不含备份)。"""
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.index_path), suffix=".tmp",
            prefix="index_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(index, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.index_path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _migrate_legacy(self) -> None:
        """迁移旧版单文件题库(data/questions.json)到"未分类"分类。"""
        legacy_path = os.path.join(self.data_dir, "questions.json")
        if not os.path.isfile(legacy_path):
            return
        try:
            with open(legacy_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            items = raw.get("questions", []) if isinstance(raw, dict) else raw
            if not isinstance(items, list):
                return
        except (json.JSONDecodeError, OSError):
            return
        # 仅当默认分类尚为空时迁移,避免覆盖。
        if self.load_questions(DEFAULT_CATEGORY_ID):
            return
        questions = [Question.from_dict(item) for item in items
                     if isinstance(item, dict)]
        if questions:
            self.save_questions(DEFAULT_CATEGORY_ID, questions)
        # 迁移完成后重命名旧文件,避免重复迁移;重命名失败不阻止启动
        # (默认分类非空保护可避免重复迁移)。
        try:
            os.replace(legacy_path, legacy_path + ".bak")
        except OSError:
            try:
                os.rename(legacy_path, legacy_path + ".bak")
            except OSError:
                pass


#: 抽题模板默认文件名。
TEMPLATE_FILE_NAME = "templates.json"


class TemplateStore:
    """答题抽题配置模板存储(data/templates.json)。

    模板格式::

        {"version": 1, "templates": {
            "模板名": {"single": 5, "multiple": 3, "judge": 2,
                       "fill": 1, "short": 0}
        }}
    """

    def __init__(self, data_dir: str) -> None:
        """初始化模板存储。

        Args:
            data_dir: 数据根目录。
        """
        self.path = os.path.join(data_dir, TEMPLATE_FILE_NAME)

    def list_templates(self) -> Dict[str, dict]:
        """返回全部模板 {名称: 题型数量映射}。"""
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            templates = raw.get("templates", {}) if isinstance(raw, dict) \
                else {}
            return {name: dict(specs) for name, specs in templates.items()
                    if isinstance(specs, dict)}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def save_template(self, name: str, specs: Dict[str, int]) -> None:
        """保存(或覆盖)一个模板。"""
        templates = self.list_templates()
        templates[name.strip()] = {k: int(v) for k, v in specs.items()}
        self._write(templates)

    def delete_template(self, name: str) -> bool:
        """删除一个模板。"""
        templates = self.list_templates()
        if name in templates:
            del templates[name]
            self._write(templates)
            return True
        return False

    def _write(self, templates: Dict[str, dict]) -> None:
        """原子写入模板文件(写入前自动备份)。"""
        backup_file(self.path, os.path.join(
            os.path.dirname(os.path.abspath(self.path)), BACKUP_DIR_NAME))
        os.makedirs(os.path.dirname(os.path.abspath(self.path)),
                    exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(os.path.abspath(self.path)),
            suffix=".tmp", prefix="templates_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "templates": templates}, fh,
                          ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


#: 历史成绩默认文件名。
HISTORY_FILE_NAME = "history.json"

#: 历史成绩最多保留的记录条数。
HISTORY_MAX_RECORDS = 200


class HistoryStore:
    """答题历史成绩存储(data/history.json)。

    每次提交答题后追加一条记录(自动分/总分/正确率/用时/题型分布),
    供「历史成绩」界面查看(按时间倒序)与删除:

        {"version": 1, "records": [{...}, ...]}
    """

    def __init__(self, data_dir: str) -> None:
        """初始化历史成绩存储。

        Args:
            data_dir: 数据根目录。
        """
        self.path = os.path.join(data_dir, HISTORY_FILE_NAME)

    def list_records(self) -> List[Dict]:
        """返回全部历史成绩记录(按时间倒序,最新在前)。

        Returns:
            记录字典列表;文件不存在或损坏时返回空列表。
        """
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            records = raw.get("records", []) if isinstance(raw, dict) else []
            if not isinstance(records, list):
                return []
            valid = [r for r in records if isinstance(r, dict)]
            # 倒序:最新在前。
            return sorted(valid, key=lambda r: r.get("timestamp", ""),
                          reverse=True)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def add(self, record: Dict) -> None:
        """追加一条历史成绩记录(超出上限丢弃最旧)。"""
        records = self.list_records()  # 倒序
        records.insert(0, record)
        records = records[:HISTORY_MAX_RECORDS]
        self._write(records)

    def remove(self, timestamp: str) -> bool:
        """按时间戳删除一条记录。"""
        records = self.list_records()
        remaining = [r for r in records
                     if r.get("timestamp") != timestamp]
        if len(remaining) == len(records):
            return False
        self._write(remaining)
        return True

    def clear(self) -> None:
        """清空全部历史成绩。"""
        self._write([])

    def count(self) -> int:
        """历史记录条数。"""
        return len(self.list_records())

    def _write(self, records: List[Dict]) -> None:
        """原子写入历史成绩(写入前自动备份)。"""
        backup_file(self.path, os.path.join(
            os.path.dirname(os.path.abspath(self.path)), BACKUP_DIR_NAME))
        os.makedirs(os.path.dirname(os.path.abspath(self.path)),
                    exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(os.path.abspath(self.path)),
            suffix=".tmp", prefix="history_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "records": records}, fh,
                          ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
