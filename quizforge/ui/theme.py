"""Textual 主题样式(CSS)。

所有屏幕共用的样式集中在这里,按"屏幕 -> 控件 id"组织,便于统一
调整外观。
"""

THEME_CSS = """
Screen {
    background: $surface;
}

/* ------------------------------------------------------------------ */
/* 自适应:窗口较小时内容可滚动,控件不会被裁切                          */
/* ------------------------------------------------------------------ */
/* 每个屏幕的根容器可纵向滚动(窗口矮时滚动到下方控件)。 */
Screen > Vertical {
    overflow-y: auto;
}

/* ------------------------------------------------------------------ */
/* 通用                                                               */
/* ------------------------------------------------------------------ */
.title {
    text-style: bold;
    color: $accent;
    content-align: center middle;
}

.subtitle {
    color: $text-muted;
    content-align: center middle;
}

.hint {
    color: $text-muted;
    text-align: center;
}

/* 按钮行:窗口窄时可横向滚动,按钮不会被裁切。 */
.button-row {
    height: 3;
    align: center middle;
    overflow-x: auto;
}

.button-row Button {
    margin: 0 1;
}

/* 模态框 */
.modal-box {
    width: 64;
    height: auto;
    max-height: 80%;
    border: round $accent;
    background: $surface;
    padding: 1 2;
    overflow-y: auto;
}

.modal-box .title {
    height: 3;
}

.modal-box #modal_message {
    height: auto;
    padding: 0 1 1 1;
}

/* 抽题设置:题型数量行(两列布局) */
#draw_outer {
    max-height: 80%;
}

#draw_scroll {
    height: auto;
    max-height: 60%;
}

.draw-row {
    height: 3;
    align: center middle;
    padding: 0 1;
}

.draw-row Label {
    width: 8;
    margin-right: 1;
}

.draw-row Input {
    width: 12;
    margin-right: 1;
}

.draw-limit {
    width: 5;
    color: $text-muted;
}

#draw_template_row {
    height: 3;
    align: center middle;
    padding: 0 1;
}

#draw_template_row Select {
    width: 1fr;
    margin-right: 1;
}

#draw_control_row, #file_control_row {
    height: 3;
    align: center middle;
    padding: 0 1;
}

#file_control_row Input {
    width: 1fr;
    min-width: 30;
    margin-right: 1;
}

#draw_control_row Button, #file_control_row Button {
    min-width: 10;
    margin-right: 1;
}

#draw_summary, #file_summary {
    color: $text-muted;
    padding: 0 1;
}

/* ------------------------------------------------------------------ */
/* 主菜单                                                             */
/* ------------------------------------------------------------------ */
#menu_title {
    height: 2;
    text-style: bold;
    color: $accent;
    content-align: center middle;
}

#menu_subtitle {
    height: 1;
    color: $text-muted;
    content-align: center middle;
}

#menu_stats {
    height: 1;
    color: $text-muted;
    content-align: center middle;
}

#menu_buttons {
    height: auto;
    align: center middle;
    padding: 1 6;
}

#menu_buttons Button {
    width: 28;
    margin: 0 2 0 2;
}

/* ------------------------------------------------------------------ */
/* 题库管理                                                           */
/* ------------------------------------------------------------------ */
#bank_category_bar {
    height: 3;
    padding: 0 1;
    align: center middle;
    overflow-x: auto;
}

#bank_category_bar Select {
    width: 30;
    min-width: 12;
    margin-right: 1;
}

#bank_category_bar Button {
    min-width: 10;
}

#bank_search_bar {
    height: 3;
    padding: 0 1;
    overflow-x: auto;
}

#bank_search_bar Input {
    width: 1fr;
    min-width: 24;
    margin-right: 1;
}

#bank_search_bar Select {
    min-width: 16;
}

#bank_toolbar {
    height: 3;
    padding: 0 1;
    overflow-x: auto;
}

#bank_toolbar Button {
    min-width: 7;
    margin: 0 1;
}

#bank_table {
    height: 1fr;
    margin: 0 1;
}

#bank_pager, #search_pager, #history_pager {
    height: 3;
    padding: 0 1;
    align: center middle;
}

#bank_pager Button, #search_pager Button, #history_pager Button {
    min-width: 12;
    margin: 0 1;
}

#bank_page_info, #search_page_info, #history_page_info {
    width: auto;
    color: $text-muted;
    margin: 0 1;
}

#bank_footer {
    height: 1;
    color: $text-muted;
    text-align: center;
}

/* ------------------------------------------------------------------ */
/* 题目编辑                                                           */
/* ------------------------------------------------------------------ */
#edit_form {
    padding: 0 2;
}

#edit_form Label {
    margin-top: 1;
    color: $text-muted;
}

#edit_type {
    width: 20;
}

#edit_text, #edit_options, #edit_analysis {
    height: 3;
}

/* ------------------------------------------------------------------ */
/* 答题                                                               */
/* ------------------------------------------------------------------ */
#exam_progress {
    height: 3;
    text-style: bold;
    content-align: center middle;
}

#exam_meta {
    height: 1;
    color: $text-muted;
    text-align: center;
}

#exam_stem {
    height: auto;
    max-height: 10;
    padding: 0 2;
    border: round $primary;
    margin: 0 1;
    overflow-y: auto;
}

#exam_options {
    height: 1fr;
    padding: 1 2;
}

#exam_hint {
    height: 1;
    color: $text-muted;
    text-align: center;
}

/* ------------------------------------------------------------------ */
/* 答题卡                                                             */
/* ------------------------------------------------------------------ */
#sheet_title {
    height: 3;
    text-style: bold;
    color: $accent;
    content-align: center middle;
}

#sheet_table {
    height: 1fr;
    max-height: 60%;
    margin: 0 1;
}

/* ------------------------------------------------------------------ */
/* 回看                                                               */
/* ------------------------------------------------------------------ */
#review_summary {
    height: 4;
    content-align: center middle;
    text-style: bold;
}

#review_list {
    width: 30%;
    height: 1fr;
    border: round $primary;
    margin: 0 1;
}

#review_detail {
    width: 1fr;
    height: 1fr;
    border: round $primary;
    margin: 0 1;
    padding: 0 1;
}

/* ------------------------------------------------------------------ */
/* 查题                                                               */
/* ------------------------------------------------------------------ */
#search_bar {
    height: 3;
    padding: 0 1;
    overflow-x: auto;
}

#search_bar Select {
    min-width: 16;
    margin-right: 1;
}

#search_bar Input {
    width: 1fr;
    min-width: 24;
    margin-right: 1;
}

/* ------------------------------------------------------------------ */
/* 答题设置                                                           */
/* ------------------------------------------------------------------ */
/* 选题方式切换容器:高度按内容收缩,否则会撑满屏幕把下方按钮挤出。 */
#mode_switcher {
    height: auto;
}

#view_draw, #view_file {
    height: auto;
}

#setup_preview {
    height: auto;
    min-height: 2;
    max-height: 10;
    border: round $primary;
    margin: 0 1;
}

#setup_preview_text {
    padding: 0 1;
}

#search_table {
    height: 1fr;
    margin: 0 1;
}

#history_table {
    height: 1fr;
    margin: 0 1;
}

#history_summary {
    height: 1;
    color: $text-muted;
    text-align: center;
}

#search_detail {
    height: 10;
    border: round $primary;
    margin: 0 1;
    padding: 0 1;
}

/* ------------------------------------------------------------------ */
/* 设置                                                               */
/* ------------------------------------------------------------------ */
.settings-row {
    height: 3;
    align: center middle;
    padding: 0 2;
}

.settings-row Label {
    width: 1fr;
}

.section-title {
    color: $text-muted;
    padding: 0 2;
    margin-top: 1;
}

#cx_status_row {
    height: 3;
    align: center middle;
    padding: 0 2;
}

#cx_status_row Label {
    width: 1fr;
}

#settings_info {
    color: $text-muted;
    padding: 0 2;
    margin-top: 1;
}

/* ------------------------------------------------------------------ */
/* 学习通                                                             */
/* ------------------------------------------------------------------ */
#cx_status {
    height: 3;
    color: $text-muted;
    content-align: center middle;
}

#cx_qr {
    content-align: center middle;
    color: $text;
    padding: 1;
}

#cx_welcome {
    height: 3;
    color: $accent;
    content-align: center middle;
}

#cx_courses, #cx_works {
    height: 8;
    border: round $primary;
    margin: 0 1;
}

#cx_preview {
    height: auto;
    max-height: 6;
    color: $text-muted;
    padding: 0 1;
}
"""
