"""题库文件管理：分类创建、删除，题库文件 CRUD，批量导入。"""
import os
import json
import shutil
from typing import List, Dict, Optional, Tuple

from config import BANKS_DIR, HTML_EXTENSIONS
from html_parser import HtmlParser
from utils import safe_filename, load_json_fast


class BankManager:
    """管理 question_banks 目录下的分类及题库 JSON 文件。"""

    def __init__(self):
        self.parser = HtmlParser()
        self._ensure_root()

    # ---------- 目录相关 ----------
    @staticmethod
    def _ensure_root() -> None:
        if not os.path.exists(BANKS_DIR):
            os.makedirs(BANKS_DIR)

    @staticmethod
    def list_categories() -> List[str]:
        if not os.path.exists(BANKS_DIR):
            return []
        return sorted(d for d in os.listdir(BANKS_DIR)
                      if os.path.isdir(os.path.join(BANKS_DIR, d)))

    @staticmethod
    def category_path(category: str) -> str:
        return os.path.join(BANKS_DIR, category)

    @staticmethod
    def create_category(name: str) -> str:
        path = BankManager.category_path(name)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @staticmethod
    def delete_category(name: str) -> None:
        path = BankManager.category_path(name)
        if os.path.exists(path):
            shutil.rmtree(path)

    # ---------- 题库文件操作 ----------
    @staticmethod
    def list_bank_files(category: str) -> List[str]:
        path = BankManager.category_path(category)
        if not os.path.exists(path):
            return []
        return sorted(f[:-5] for f in os.listdir(path) if f.endswith('.json'))

    @staticmethod
    def load_bank(category: str, filename: str) -> List[Dict]:
        path = os.path.join(BankManager.category_path(category),
                            f"{filename}.json")
        if os.path.exists(path):
            return load_json_fast(path)
        return []

    @staticmethod
    def save_bank(category: str, filename: str, questions: List[Dict]) -> None:
        cat_path = BankManager.category_path(category)
        if not os.path.exists(cat_path):
            os.makedirs(cat_path)
        path = os.path.join(cat_path, f"{filename}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)

    @staticmethod
    def delete_bank(category: str, filename: str) -> None:
        path = os.path.join(BankManager.category_path(category),
                            f"{filename}.json")
        if os.path.exists(path):
            os.remove(path)

    @staticmethod
    def load_all_in_category(category: str) -> List[Dict]:
        all_qs = []
        for fname in BankManager.list_bank_files(category):
            all_qs.extend(BankManager.load_bank(category, fname))
        return all_qs

    # ---------- 导入功能 ----------
    def import_html_file(self, category, html_path, existing_files, auto_confirm=False):
        """导入单个 HTML，返回 (成功标志/auto, 题数, 文件名, 错误题号列表) 或 None"""
        try:
            questions, wrong_nums = self.parser.parse(html_path)
            if not questions:
                print(f"  跳过 {html_path}：未提取到题目。")
                return False, 0, None, []
        except Exception as e:
            print(f"  解析失败 {html_path}：{e}")
            return False, 0, None, []

        base_name = safe_filename(html_path)
        if base_name in existing_files:
            if auto_confirm:
                self.save_bank(category, base_name, questions)
                return True, len(questions), base_name, wrong_nums
            confirm = input(
                f"  文件 {base_name}.json 已存在，是否覆盖？"
                f"(y/n/a=全部覆盖/q=取消): "
            ).strip().lower()
            if confirm == 'a':
                return 'auto', len(questions), base_name, wrong_nums
            if confirm == 'q':
                return False, 0, None, []
            if confirm != 'y':
                print(f"  跳过 {html_path}")
                return False, 0, None, []
        self.save_bank(category, base_name, questions)
        return True, len(questions), base_name, wrong_nums

    def import_from_folder(self, category, folder_path):
        """批量导入文件夹中所有 HTML 文件。"""
        html_files = []
        for root, dirs, files in os.walk(folder_path):
            for f in files:
                if os.path.splitext(f)[1].lower() in HTML_EXTENSIONS:
                    html_files.append(os.path.join(root, f))
        if not html_files:
            print("该文件夹下没有 HTML 文件。")
            return
        print(f"找到 {len(html_files)} 个 HTML 文件，开始导入...")
        total_imported = 0
        auto_mode = False
        existing = set(self.list_bank_files(category))
        for html_file in html_files:
            print(f"\n处理: {os.path.basename(html_file)}")
            success, count, fname, wrong_list = self.import_html_file(
                category, html_file, existing, auto_confirm=auto_mode
            )
            if success == 'auto':
                auto_mode = True
                qs, wrong_list = self.parser.parse(html_file)
                if qs:
                    fname = safe_filename(html_file)
                    self.save_bank(category, fname, qs)
                    print(f"  导入 {len(qs)} 题 -> {fname}.json (已覆盖)")
                    if wrong_list:
                        print(f"    错误题号：{', '.join(wrong_list)}")
                    total_imported += len(qs)
                    existing.add(fname)
            elif success is True:
                print(f"  导入 {count} 题 -> {fname}.json")
                if wrong_list:
                    print(f"    错误题号：{', '.join(wrong_list)}")
                total_imported += count
                existing.add(fname)
        print(f"\n批量导入完成，共导入 {total_imported} 道题目。")