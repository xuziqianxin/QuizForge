"""应用配置管理。

负责读写配置文件(默认 ``data/config.json``),保存答题随机化开关等
用户设置。配置文件采用 JSON 格式,首次运行时自动创建并写入默认值。
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict

#: 默认数据目录(相对于项目根目录)。
DEFAULT_DATA_DIR = "data"

#: 配置文件默认文件名。
CONFIG_FILE_NAME = "config.json"


@dataclass
class AppSettings:
    """用户可配置项。

    Attributes:
        shuffle_questions: 答题时是否随机打乱题目顺序,默认关闭。
        shuffle_options: 答题时是否随机打乱选择题选项顺序,默认关闭。
        exclude_no_answer: 分类抽题时是否排除无标准答案的题目,默认关闭。
        time_limit_minutes: 限时模拟考试时长(分钟),0 表示不限时。
        chaoxing_cookie_file: 学习通登录 Cookie 持久化文件名。
    """

    shuffle_questions: bool = False
    shuffle_options: bool = False
    exclude_no_answer: bool = False
    time_limit_minutes: int = 0
    chaoxing_cookie_file: str = "chaoxing_cookies.json"

    def to_dict(self) -> Dict[str, Any]:
        """转为字典以便序列化。"""
        return {
            "shuffle_questions": self.shuffle_questions,
            "shuffle_options": self.shuffle_options,
            "exclude_no_answer": self.exclude_no_answer,
            "time_limit_minutes": self.time_limit_minutes,
            "chaoxing_cookie_file": self.chaoxing_cookie_file,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        """从字典构造配置,缺失字段使用默认值。"""
        return cls(
            shuffle_questions=bool(data.get("shuffle_questions", False)),
            shuffle_options=bool(data.get("shuffle_options", False)),
            exclude_no_answer=bool(data.get("exclude_no_answer", False)),
            time_limit_minutes=max(
                0, int(data.get("time_limit_minutes", 0) or 0)),
            chaoxing_cookie_file=str(
                data.get("chaoxing_cookie_file", "chaoxing_cookies.json")),
        )


class ConfigManager:
    """配置文件读写管理器。

    提供默认值兜底、原子写入(临时文件 + 替换)与目录自动创建,
    避免配置损坏时应用无法启动。
    """

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR) -> None:
        """初始化配置管理器。

        Args:
            data_dir: 数据目录路径,配置文件存放在该目录下。
        """
        self.data_dir = data_dir
        self.config_path = os.path.join(data_dir, CONFIG_FILE_NAME)
        self._settings = self._load()

    # ------------------------------------------------------------------ #
    # 读取
    # ------------------------------------------------------------------ #
    @property
    def settings(self) -> AppSettings:
        """当前生效的应用配置。"""
        return self._settings

    def _load(self) -> AppSettings:
        """从磁盘加载配置;文件不存在或损坏时使用默认配置。"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            return AppSettings.from_dict(raw)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return AppSettings()

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    def save(self) -> None:
        """将当前配置原子写入磁盘(写入前自动备份)。"""
        from quizforge.storage import BACKUP_DIR_NAME, backup_file
        backup_file(self.config_path,
                    os.path.join(self.data_dir, BACKUP_DIR_NAME))
        os.makedirs(self.data_dir, exist_ok=True)
        payload = json.dumps(self._settings.to_dict(),
                             ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(
            dir=self.data_dir, suffix=".tmp", prefix="config_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, self.config_path)
        except OSError:
            # 写入失败时清理临时文件,避免残留。
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def update(self, **kwargs: Any) -> None:
        """批量更新配置项并立即保存。

        Args:
            **kwargs: 配置字段名 -> 新值,仅接受 AppSettings 的已知字段。
        """
        for key, value in kwargs.items():
            if hasattr(self._settings, key):
                setattr(self._settings, key, value)
            else:
                raise ValueError(f"未知配置项: {key}")
        self.save()
