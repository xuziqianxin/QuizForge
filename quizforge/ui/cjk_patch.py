"""CJK 渲染补丁(已撤销)。

历史
----
早期版本为修复 Textual 8.2.5 下拉框中文选项缺字(rich ``_split_cells``
在切点落在双宽字符内部时把字符替换为空格),曾 monkey-patch
``rich.segment.Segment._split_cells``,把双宽字符完整保留到左侧段。

为什么撤销
----------
该补丁破坏了 rich 的宽度记账契约:双宽字符完整保留后,左侧段实际宽度
比切割点 cut 多 1 列,而 ``Strip.divide`` / ``Strip.crop`` 按
``cut - pos`` 记账,导致 Compositor 拼接浮层(Toast 提示框等)时各段
错位重叠——即**渲染重影**,点击全量重绘后才暂时恢复。重影比缺字
严重得多。

结论
----
* **缺字**(下拉框中文在某些窗口宽度少一个字符):是 rich 官方设计
  (``split_cells`` 文档明示"双宽字符被切时变成两个空格"),可容忍;
* **重影**:由破坏宽度契约的自定义补丁引起,必须消除。

因此本模块不再做任何 monkey-patch,``apply_cjk_patch()`` 为幂等 no-op,
保留入口仅为兼容旧调用(``app.py`` 启动时仍会调用,但什么都不改)。
rich 的 ``_cell_widths.CELL_WIDTHS`` 表(wcwidth 数据)已内置于 rich,
宽度计算本身是正确的,不需要也不应该重写。
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


def apply_cjk_patch() -> None:
    """应用 CJK 渲染补丁(已撤销,现为 no-op)。

    保留此函数仅为兼容旧调用点;实际不做任何修改,确保 rich/Textual
    使用官方宽度契约,避免渲染重影。
    """
    _LOGGER.info("CJK 补丁已撤销:使用 rich 官方宽度契约(接受极少数窗口宽度下下拉框中文缺字,换取无重影)")
