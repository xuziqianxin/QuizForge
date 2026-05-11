"""
通用工具函数：拼音转换、文件名清洗、高性能 JSON 加载、清屏。
"""
import os
import re
import hashlib
import json
from typing import List, Dict, Any

# 可选高性能 JSON 库
try:
    import orjson
    _ORJSON_AVAILABLE = True
except ImportError:
    _ORJSON_AVAILABLE = False

# 可选中文拼音库
try:
    from pypinyin import lazy_pinyin, Style
    _PYPINYIN_AVAILABLE = True
except ImportError:
    _PYPINYIN_AVAILABLE = False

from config import SAFE_FILENAME_PATTERN, PINYIN_FALLBACK_LENGTH


def load_json_fast(filepath: str) -> List[Dict[str, Any]]:
    """高性能 JSON 加载，优先使用 orjson，否则回退标准库。"""
    if _ORJSON_AVAILABLE:
        with open(filepath, 'rb') as f:
            return orjson.loads(f.read())
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def chinese_to_pinyin(text: str) -> str:
    """中文字符串转拼音首字母小写，非中文保留原字符。"""
    if _PYPINYIN_AVAILABLE:
        result = []
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                py = lazy_pinyin(char, style=Style.FIRST_LETTER)[0]
                result.append(py if py else '_')
            else:
                result.append(char)
        return ''.join(result).lower()
    # 降级方案：MD5 缩写
    return 'cn_' + hashlib.md5(text.encode()).hexdigest()[:PINYIN_FALLBACK_LENGTH]


def safe_filename(html_path: str) -> str:
    """从 HTML 文件路径生成安全的题库文件名（去除扩展名）。"""
    base = os.path.splitext(os.path.basename(html_path))[0]
    if re.match(SAFE_FILENAME_PATTERN, base):
        return base
    return chinese_to_pinyin(base) or 'import'


def clear_screen() -> None:
    """跨平台清屏。"""
    os.system('cls' if os.name == 'nt' else 'clear')