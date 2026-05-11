"""全局配置常量，消除硬编码。"""
import os

# 题库根目录
BANKS_DIR = "question_banks"

# 答题结果展示每行答案数
ITEMS_PER_ROW = 10

# 多选题目类型列表（用于判断是否允许多选）
MULTI_SELECT_TYPES = {'多选题', '不定项选择题'}

# 支持导入的 HTML 文件名后缀
HTML_EXTENSIONS = {'.html', '.htm'}

# 外部搜索支持的 JSON 文件名后缀
JSON_EXTENSIONS = {'.json', '.JSON'}

# 文件名安全模式（纯英文/数字/下划线/点/连字符）
SAFE_FILENAME_PATTERN = r'^[a-zA-Z0-9_.\-]+$'

# 拼音回退时的 MD5 前缀长度
PINYIN_FALLBACK_LENGTH = 8

# 题型的正则表达式（匹配常见中文题型）
TYPE_PATTERN = (
    r'(单选题|多选题|判断题|填空题|简答题|论述题|名词解释|计算题|'
    r'综合题|不定项选择题|案例分析题)'
)

# HTML 解析用到的 CSS 类名（可根据学习平台变化修改）
HTML_CLASSES = {
    "question_container": "questionLi",
    "title_header": "mark_name",
    "type_span": "colorShallow",
    "question_content": "qtContent",
    "options_list": "mark_letter",
    "user_answer": "stuAnswerContent",
    "correct_answer": "rightAnswerContent",
    "judge_div": "mark_judge_name",
    "correct_mark": "marking_dui",
    "wrong_mark": "marking_cuo",
}

# 界面中使用的 Rich 样式标记（便于统一修改）
RICH_CORRECT_MARK = "✓ 正确"
RICH_WRONG_MARK = "✗ 错误"
RICH_WRONG_STYLE = "reverse red bold"
RICH_START_PROMPT = "[bold green]按 Enter 开始答题（共 {count} 题）[/bold green]"
RICH_SELECT_HINT = "[italic]请先选择题库文件[/italic]"