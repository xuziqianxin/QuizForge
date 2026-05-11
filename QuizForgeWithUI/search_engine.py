"""题目搜索引擎：支持内部题库与外部 JSON 文件/文件夹的关键词检索。"""
from typing import List, Tuple, Dict
from pathlib import Path
from bank_manager import BankManager
from utils import load_json_fast


class SearchEngine:
    """处理题目搜索逻辑，不涉及界面交互。"""

    @staticmethod
    def search_internal(keyword: str) -> List[Tuple[str, str, Dict]]:
        """在所有分类题库中搜索，返回 [(分类, 文件名, 题目), ...]"""
        results = []
        for cat in BankManager.list_categories():
            for fname in BankManager.list_bank_files(cat):
                questions = BankManager.load_bank(cat, fname)
                for q in questions:
                    if keyword in q.get('question', ''):
                        results.append((cat, fname, q))
        return results

    @staticmethod
    def search_external(path_str: str, keyword: str) -> List[Tuple[str, Dict]]:
        """搜索外部 JSON 文件或文件夹，返回 [(文件路径, 题目), ...]"""
        p = Path(path_str)
        if not p.exists():
            raise FileNotFoundError(f"路径不存在: {path_str}")
        json_files = []
        if p.is_file() and p.suffix.lower() == '.json':
            json_files.append(p)
        elif p.is_dir():
            json_files.extend(p.glob('*.json'))
            json_files.extend(p.glob('*.JSON'))
        else:
            raise ValueError("路径不是 JSON 文件或文件夹")
        results = []
        for file_path in json_files:
            try:
                questions = load_json_fast(str(file_path))
                for q in questions:
                    if keyword in q.get('question', ''):
                        results.append((str(file_path), q))
            except Exception as e:
                print(f"  加载文件失败 {file_path}: {e}")
        return results