"""二维码终端渲染工具。

使用半块字符(▀ ▄ █)在终端中绘制二维码,可直接用学习通 App 扫码。
依赖 ``qrcode`` 库(仅计算模块矩阵,不生成图片文件)。
"""

from __future__ import annotations

from typing import List


def render_qr_block(url: str, quiet: int = 2) -> str:
    """将 URL 渲染为终端半块字符二维码。

    Args:
        url: 二维码承载的内容(学习通扫码登录地址)。
        quiet: 静区宽度(模块数)。

    Returns:
        多行字符串形式的二维码,每两个原始模块行合成一行字符。

    Raises:
        ImportError: 未安装 qrcode 库。
    """
    try:
        import qrcode
    except ImportError as exc:  # pragma: no cover - 依赖缺失时提示
        raise ImportError("缺少 qrcode 库,请执行 pip install qrcode") from exc

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=quiet,
    )
    qr.add_data(url)
    qr.make(fit=True)

    modules: List[List[bool]] = qr.modules  # type: ignore[assignment]
    lines: List[str] = []
    for row_index in range(0, len(modules), 2):
        top = modules[row_index]
        bottom = modules[row_index + 1] if row_index + 1 < len(modules) else \
            [False] * len(top)
        line_chars: List[str] = []
        for top_bit, bottom_bit in zip(top, bottom):
            if top_bit and bottom_bit:
                line_chars.append("█")
            elif top_bit:
                line_chars.append("▀")
            elif bottom_bit:
                line_chars.append("▄")
            else:
                line_chars.append(" ")
        lines.append("".join(line_chars))
    return "\n".join(lines)
