import json
import os
import random
import re
import sys
from bs4 import BeautifulSoup

# ---------- 全局配置 ----------
BANKS_DIR = "question_banks"
ITEMS_PER_ROW = 10

# ---------- 拼音处理 ----------
try:
    from pypinyin import lazy_pinyin, Style
    def chinese_to_pinyin(text):
        result = []
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                py = lazy_pinyin(char, style=Style.FIRST_LETTER)[0]
                result.append(py if py else '_')
            else:
                result.append(char)
        return ''.join(result).lower()
except ImportError:
    def chinese_to_pinyin(text):
        import hashlib
        return 'cn_' + hashlib.md5(text.encode()).hexdigest()[:8]

def safe_filename(html_path):
    base = os.path.splitext(os.path.basename(html_path))[0]
    if re.match(r'^[a-zA-Z0-9_.-]+$', base):
        return base
    else:
        return chinese_to_pinyin(base) or 'import'

# ---------- HTML 提取函数 ----------
def extract_from_html(html_file_path):
    with open(html_file_path, 'r', encoding='utf-8') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    questions = []
    question_divs = soup.find_all('div', class_=lambda x: x and 'questionLi' in x)
    for qdiv in question_divs:
        qid = qdiv.get('id', '')
        h3 = qdiv.find('h3', class_='mark_name')
        if not h3:
            continue
        title_text = h3.get_text(strip=True)
        parts = title_text.split('.', 1)
        number = parts[0].strip() if len(parts) == 2 else ''
        type_span = h3.find('span', class_='colorShallow')
        if type_span:
            raw_type = type_span.get_text(strip=True)
            question_type = raw_type.strip('()')
        else:
            question_type = ''
        qt_span = qdiv.find('span', class_='qtContent')
        question_text = qt_span.get_text(strip=True) if qt_span else ''
        options = []
        ul = qdiv.find('ul', class_='mark_letter')
        if ul:
            for li in ul.find_all('li'):
                opt_text = li.get_text(strip=True)
                if opt_text:
                    options.append(opt_text)
        right_answer_span = qdiv.find('span', class_='rightAnswerContent')
        correct_answer = right_answer_span.get_text(strip=True) if right_answer_span else ''
        question_data = {
            'id': qid,
            'number': number,
            'type': question_type,
            'question': question_text,
            'options': options,
            'correct_answer': correct_answer
        }
        questions.append(question_data)
    return questions

# ---------- 文件系统辅助 ----------
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def ensure_banks_dir():
    if not os.path.exists(BANKS_DIR):
        os.makedirs(BANKS_DIR)

def list_categories():
    if not os.path.exists(BANKS_DIR):
        return []
    return sorted([d for d in os.listdir(BANKS_DIR) if os.path.isdir(os.path.join(BANKS_DIR, d))])

def category_path(category):
    return os.path.join(BANKS_DIR, category)

def list_bank_files(category):
    path = category_path(category)
    if not os.path.exists(path):
        return []
    files = [f[:-5] for f in os.listdir(path) if f.endswith('.json')]
    return sorted(files)

def load_bank_file(category, filename):
    path = os.path.join(category_path(category), f"{filename}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_bank_file(category, filename, questions):
    cat_path = category_path(category)
    if not os.path.exists(cat_path):
        os.makedirs(cat_path)
    path = os.path.join(cat_path, f"{filename}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

def delete_bank_file(category, filename):
    path = os.path.join(category_path(category), f"{filename}.json")
    if os.path.exists(path):
        os.remove(path)

def load_all_questions_in_category(category):
    all_qs = []
    for fname in list_bank_files(category):
        all_qs.extend(load_bank_file(category, fname))
    return all_qs

# ---------- 导入辅助 ----------
def import_single_html(category, html_path, existing_files, auto_confirm=False):
    """导入单个HTML文件，返回 (成功, 导入题目数, 文件名)"""
    try:
        questions = extract_from_html(html_path)
        if not questions:
            print(f"  跳过 {html_path}：未提取到题目。")
            return False, 0, None
        base_name = safe_filename(html_path)
        if base_name in existing_files:
            if auto_confirm:
                # 自动覆盖模式（用户选择“全部覆盖”时使用）
                save_bank_file(category, base_name, questions)
                return True, len(questions), base_name
            else:
                confirm = input(f"  文件 {base_name}.json 已存在，是否覆盖？(y/n/a=全部覆盖/q=取消导入): ").strip().lower()
                if confirm == 'a':
                    # 返回特殊标记，让调用者切换为自动覆盖模式
                    return 'auto', len(questions), base_name
                elif confirm == 'q':
                    return False, 0, None
                elif confirm != 'y':
                    print(f"  跳过 {html_path}")
                    return False, 0, None
        save_bank_file(category, base_name, questions)
        return True, len(questions), base_name
    except Exception as e:
        print(f"  导入 {html_path} 失败：{e}")
        return False, 0, None

# ---------- 分类管理菜单 ----------
def manage_category(category):
    while True:
        clear_screen()
        print(f"===== 管理分类：【{category}】 =====")
        files = list_bank_files(category)
        print(f"现有题库文件 ({len(files)} 个)：")
        if files:
            for i, f in enumerate(files):
                qs = load_bank_file(category, f)
                print(f"  {i+1}. {f}.json  ({len(qs)} 题)")
        else:
            print("  (暂无题库文件)")
        print("\n1. 从 HTML 导入（支持文件或文件夹）")
        print("2. 删除题库文件")
        print("3. 查看题库文件内容")
        print("4. 返回上级菜单")
        choice = input("请选择: ").strip()

        if choice == '1':
            path = input("请输入HTML文件或文件夹路径: ").strip()
            if not os.path.exists(path):
                print("路径不存在。")
                input("按 Enter 继续...")
                continue

            if os.path.isfile(path):
                # 单文件导入
                success, count, fname = import_single_html(category, path, files)
                if success:
                    print(f"成功导入 {count} 题，保存为 {fname}.json")
                elif success == 'auto':
                    save_bank_file(category, fname, extract_from_html(path))
                    print(f"成功导入 {count} 题，保存为 {fname}.json (自动覆盖模式)")
                else:
                    print("导入取消或失败。")
            else:
                # 文件夹导入
                html_files = []
                for root, dirs, filenames in os.walk(path):
                    for f in filenames:
                        if f.lower().endswith(('.html', '.htm')):
                            html_files.append(os.path.join(root, f))
                if not html_files:
                    print("该文件夹下没有 .html 或 .htm 文件。")
                    input("按 Enter 继续...")
                    continue
                print(f"找到 {len(html_files)} 个HTML文件，开始导入...")
                total_imported = 0
                auto_mode = False
                existing = set(files)
                for html_file in html_files:
                    print(f"\n处理: {os.path.basename(html_file)}")
                    if auto_mode:
                        # 自动覆盖模式
                        try:
                            qs = extract_from_html(html_file)
                            if qs:
                                fname = safe_filename(html_file)
                                save_bank_file(category, fname, qs)
                                print(f"  导入 {len(qs)} 题 -> {fname}.json (已覆盖)")
                                total_imported += len(qs)
                                existing.add(fname)
                            else:
                                print("  未提取到题目，跳过。")
                        except Exception as e:
                            print(f"  导入失败：{e}")
                    else:
                        success, count, fname = import_single_html(category, html_file, existing)
                        if success == 'auto':
                            auto_mode = True
                            # 保存当前文件
                            qs = extract_from_html(html_file)
                            save_bank_file(category, fname, qs)
                            print(f"  导入 {len(qs)} 题 -> {fname}.json (已覆盖)")
                            total_imported += len(qs)
                            existing.add(fname)
                        elif success:
                            print(f"  导入 {count} 题 -> {fname}.json")
                            total_imported += count
                            existing.add(fname)
                print(f"\n批量导入完成，共导入 {total_imported} 道题目。")
            input("按 Enter 继续...")

        elif choice == '2':
            if not files:
                print("没有文件可删除。")
                input("按 Enter 返回...")
                continue
            try:
                idx = int(input("请输入要删除的文件序号: ")) - 1
                if 0 <= idx < len(files):
                    fname = files[idx]
                    confirm = input(f"确定删除 {fname}.json 吗？(y/n): ").strip().lower()
                    if confirm == 'y':
                        delete_bank_file(category, fname)
                        print("文件已删除。")
                else:
                    print("序号无效。")
            except ValueError:
                print("请输入数字。")
            input("按 Enter 继续...")

        elif choice == '3':
            if not files:
                print("没有文件可查看。")
                input("按 Enter 返回...")
                continue
            try:
                idx = int(input("请输入要查看的文件序号: ")) - 1
                if 0 <= idx < len(files):
                    fname = files[idx]
                    qs = load_bank_file(category, fname)
                    clear_screen()
                    print(f"===== {fname}.json 题目列表 =====")
                    for i, q in enumerate(qs):
                        print(f"{i+1}. [{q['number']}] {q['type']} - {q['question'][:40]}...")
                    input("\n按 Enter 返回...")
                else:
                    print("序号无效。")
            except ValueError:
                print("请输入数字。")
            input("按 Enter 继续...")

        elif choice == '4':
            break
        else:
            print("无效选择。")
            input("按 Enter 继续...")

def category_manager_menu():
    ensure_banks_dir()
    while True:
        clear_screen()
        print("===== 分类管理 =====")
        categories = list_categories()
        if categories:
            print("现有分类：")
            for i, cat in enumerate(categories):
                print(f"  {i+1}. {cat}")
        else:
            print("暂无分类。")
        print("\nN. 新建分类")
        print("D. 删除分类")
        print("Q. 返回主菜单")
        choice = input("请选择 (序号/名称/N/D/Q): ").strip()

        if choice.upper() == 'Q':
            break
        elif choice.upper() == 'N':
            name = input("请输入新分类名称: ").strip()
            if not name:
                print("名称不能为空。")
                input("按 Enter 继续...")
                continue
            path = category_path(name)
            if os.path.exists(path):
                print("分类已存在，将进入管理。")
            else:
                os.makedirs(path)
            manage_category(name)
        elif choice.upper() == 'D':
            if not categories:
                print("没有分类可删除。")
                input("按 Enter 继续...")
                continue
            name = input("请输入要删除的分类名称: ").strip()
            if name not in categories:
                print("分类不存在。")
                input("按 Enter 继续...")
                continue
            confirm = input(f"确定删除分类 '{name}' 及其所有题库文件吗？(y/n): ").strip().lower()
            if confirm == 'y':
                import shutil
                shutil.rmtree(category_path(name))
                print("分类已删除。")
            else:
                print("取消删除。")
            input("按 Enter 继续...")
        else:
            selected = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(categories):
                    selected = categories[idx]
            else:
                if choice in categories:
                    selected = choice
            if selected:
                manage_category(selected)
            else:
                print("无效选择。")
                input("按 Enter 继续...")

# ---------- 答题模块 ----------
def shuffle_options(q):
    """随机打乱题目选项，返回新选项列表和新正确选项字母串"""
    # 提取选项文本（去除字母前缀）
    opt_texts = []
    for opt in q['options']:
        # 匹配形如 "A. " 或 "A." 的前缀
        match = re.match(r'^[A-Z]\.\s*', opt)
        if match:
            text = opt[len(match.group()):].strip()
        else:
            text = opt.strip()
        opt_texts.append(text)

    # 生成新字母序列（数量与选项数相同）
    letters = [chr(ord('A') + i) for i in range(len(opt_texts))]
    shuffled_indices = list(range(len(opt_texts)))
    random.shuffle(shuffled_indices)

    # 构建新选项列表（带字母前缀）
    new_options = []
    for i, idx in enumerate(shuffled_indices):
        letter = letters[i]
        new_options.append(f"{letter}. {opt_texts[idx]}")

    # 映射：原始字母 -> 新字母
    orig_letters = [chr(ord('A') + i) for i in range(len(opt_texts))]
    mapping = {}
    for new_i, orig_i in enumerate(shuffled_indices):
        mapping[orig_letters[orig_i]] = letters[new_i]

    # 转换正确答案
    orig_correct = q['correct_answer'].upper()
    new_correct_letters = []
    for ch in orig_correct:
        if ch in mapping:
            new_correct_letters.append(mapping[ch])
        else:
            new_correct_letters.append(ch)  # 非字母保留
    new_correct = ''.join(new_correct_letters)

    return new_options, new_correct

def format_answers_aligned(answers, label, items_per_row=ITEMS_PER_ROW):
    rows = [answers[i:i+items_per_row] for i in range(0, len(answers), items_per_row)]
    num_cols = max(len(row) for row in rows) if rows else 0
    col_widths = [0] * num_cols
    for row in rows:
        for col_idx, ans in enumerate(row):
            col_widths[col_idx] = max(col_widths[col_idx], len(ans))
    col_widths = [w + 1 for w in col_widths]
    print(f"\n{label}:")
    for row in rows:
        formatted_row = ""
        for col_idx, ans in enumerate(row):
            formatted_row += ans.ljust(col_widths[col_idx])
        print(formatted_row.rstrip())

def show_answered_list(answered_dict, question_map, shuffled):
    clear_screen()
    print("=" * 50)
    print("已作答题目列表：")
    if not answered_dict:
        print("  (暂无已作答题目)")
    else:
        display_index_map = {q['id']: idx+1 for idx, q in enumerate(shuffled)}
        sorted_items = sorted(answered_dict.items(),
                             key=lambda item: display_index_map.get(item[0], 9999))
        for qid, ans in sorted_items:
            q = question_map[qid]
            idx = display_index_map.get(qid, '?')
            print(f"  [{idx:>3}] 题号 {q['number']} ({q['type']}): {ans}")
    print("=" * 50)
    input("\n按 Enter 键返回当前题目...")

def confirm_submit(missing_count):
    print(f"\n警告：还有 {missing_count} 道题目未作答。")
    confirm = input("确定要提交吗？(y/n): ").strip().lower()
    return confirm == 'y'

def find_next_unanswered(shuffled, user_answers, start_idx):
    total = len(shuffled)
    for offset in range(total):
        idx = (start_idx + offset) % total
        if shuffled[idx]['id'] not in user_answers:
            return idx
    return None

def run_quiz(questions, shuffle_enabled=False):
    if not questions:
        print("题库为空，无法答题。")
        return
    import uuid
    for q in questions:
        if 'id' not in q:
            q['id'] = str(uuid.uuid4())
            
    # 随机打乱每道题的选项顺序
    if shuffle_enabled:
        for q in questions:
            new_options, new_correct = shuffle_options(q)
            q['options'] = new_options
            q['correct_answer'] = new_correct

    shuffled = questions.copy()
    random.shuffle(shuffled)
    total = len(shuffled)
    q_map = {q['id']: q for q in questions}
    user_answers = {}

    current_idx = 0
    jump_back_idx = None

    print(f"\n开始答题（共 {total} 题，随机顺序）")
    input("按 Enter 开始...")

    while True:
        if len(user_answers) == total:
            print("\n所有题目已完成！自动提交。")
            break
        if current_idx >= total:
            current_idx = 0
        q = shuffled[current_idx]
        qid = q['id']

        clear_screen()
        print("=" * 50)
        print(f"第 {current_idx+1}/{total} 题")
        print(f"题号: {q['number']}  {q['type']}")
        print(f"题目: {q['question']}")
        print("\n选项:")
        for opt in q['options']:
            print(f"  {opt}")
        print("-" * 50)
        print("(输入答案，或使用指令: j 序号 / j back / list / submit)")
        if qid in user_answers:
            print(f"当前已存答案: {user_answers[qid]}")

        user_input = input("请输入: ").strip()

        if user_input.lower().startswith('j'):
            parts = user_input.split()
            if len(parts) == 2 and parts[1].lower() == 'back':
                if jump_back_idx is None:
                    print("没有可返回的上一个位置。")
                    input("按 Enter 继续...")
                else:
                    current_idx = jump_back_idx
                    jump_back_idx = None
                continue
            elif len(parts) == 2:
                try:
                    target_display = int(parts[1])
                except ValueError:
                    print("序号必须为数字。")
                    input("按 Enter 继续...")
                    continue
                if target_display < 1 or target_display > total:
                    print(f"序号超出范围，应为 1 到 {total}。")
                    input("按 Enter 继续...")
                    continue
                jump_back_idx = current_idx
                current_idx = target_display - 1
                continue
            else:
                print("格式错误，应为: j 序号 或 j back")
                input("按 Enter 继续...")
                continue

        elif user_input.lower() == 'list':
            show_answered_list(user_answers, q_map, shuffled)
            continue

        elif user_input.lower() == 'submit':
            missing = total - len(user_answers)
            if missing > 0:
                if not confirm_submit(missing):
                    continue
            break

        else:
            if user_input == "":
                print("答案不能为空，请重新输入。")
                input("按 Enter 继续...")
                continue
            user_answers[qid] = user_input.upper()
            print(f"已记录答案: {user_answers[qid]}")
            jump_back_idx = None
            if len(user_answers) == total:
                continue
            next_idx = find_next_unanswered(shuffled, user_answers, current_idx + 1)
            if next_idx is not None:
                current_idx = next_idx

    clear_screen()
    print("=" * 60)
    print("答题结束！答案对照：")
    print("=" * 60)

    final_user_answers = []
    final_correct_answers = []
    for q in shuffled:
        ans = user_answers.get(q['id'], "未作答")
        final_user_answers.append(ans)
        final_correct_answers.append(q['correct_answer'].upper())

    format_answers_aligned(final_user_answers, "你的答案")
    format_answers_aligned(final_correct_answers, "正确答案")

    correct_count = sum(1 for u, c in zip(final_user_answers, final_correct_answers) if u == c)
    score_percent = correct_count / total * 100 if total > 0 else 0
    print(f"\n得分: {correct_count}/{total}  (正确率: {score_percent:.1f}%)")
    print("=" * 60)

def select_bank_files_in_category(category):
    files = list_bank_files(category)
    if not files:
        print(f"分类 '{category}' 下没有任何题库文件。")
        input("按 Enter 返回...")
        return []

    clear_screen()
    print(f"===== 选择题库：【{category}】 =====")
    print("可用题库文件：")
    for i, f in enumerate(files):
        qs = load_bank_file(category, f)
        print(f"  {i+1}. {f}.json  ({len(qs)} 题)")
    print("\nA. 所有题库（加载该分类下全部题目）")
    print("Q. 返回上级")
    choice = input("请选择 (序号/序号组合/A/Q): ").strip()

    if choice.upper() == 'Q':
        return None
    if choice.upper() == 'A':
        return files

    selected_files = []
    try:
        indices = [int(x) for x in choice.split()]
        for i in indices:
            if 1 <= i <= len(files):
                selected_files.append(files[i-1])
            else:
                print(f"序号 {i} 无效，已忽略。")
    except ValueError:
        print("输入格式错误，请输入数字序号。")
        input("按 Enter 继续...")
        return select_bank_files_in_category(category)

    if not selected_files:
        print("没有选中任何题库。")
        input("按 Enter 继续...")
        return select_bank_files_in_category(category)
    return selected_files

def quiz_mode_menu():
    ensure_banks_dir()
    categories = list_categories()
    if not categories:
        print("当前没有任何分类，请先创建分类并导入题目。")
        input("按 Enter 返回...")
        return

    while True:
        clear_screen()
        print("===== 答题模式 =====")
        print("可用的分类：")
        for i, cat in enumerate(categories):
            total_q = sum(len(load_bank_file(cat, f)) for f in list_bank_files(cat))
            print(f"  {i+1}. {cat} ({total_q} 题)")
        print("\nQ. 返回主菜单")
        choice = input("请选择分类序号: ").strip()

        if choice.upper() == 'Q':
            break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(categories):
                selected_category = categories[idx]
            else:
                print("序号无效。")
                input("按 Enter 继续...")
                continue
        except ValueError:
            print("请输入数字。")
            input("按 Enter 继续...")
            continue

        selected_files = select_bank_files_in_category(selected_category)
        if selected_files is None:
            continue
        if not selected_files:
            continue

        all_questions = []
        for fname in selected_files:
            all_questions.extend(load_bank_file(selected_category, fname))
        print(f"共加载 {len(all_questions)} 道题目。")
        if not all_questions:
            input("按 Enter 返回...")
            continue

        # 询问是否打乱选项顺序
        choice_shuffle = input("是否随机打乱题目选项顺序？(y/n，默认 n): ").strip().lower()
        shuffle_enabled = (choice_shuffle == 'y')

        run_quiz(all_questions, shuffle_enabled)
        input("\n答题结束，按 Enter 返回分类选择...")

# ---------- 主程序 ----------
def main():
    ensure_banks_dir()
    while True:
        clear_screen()
        print("===== 题库管理与答题系统 =====")
        print("1. 分类管理（导入/删除题库文件）")
        print("2. 答题模式")
        print("3. 退出")
        choice = input("请选择: ").strip()
        if choice == '1':
            category_manager_menu()
        elif choice == '2':
            quiz_mode_menu()
        elif choice == '3':
            print("感谢使用，再见！")
            break
        else:
            print("无效选择，请重新输入。")
            input("按 Enter 继续...")

if __name__ == "__main__":
    main()