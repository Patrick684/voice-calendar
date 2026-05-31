"""生成应用图标 - 多尺寸日历样式 .ico 文件"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw, ImageFont


def create_calendar_icon(size: int) -> Image.Image:
    """生成指定尺寸的日历图标

    设计：白色背景圆角矩形，顶部蓝色条带，中间显示日期数字
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 尺寸比例
    pad = max(1, size // 16)
    radius = max(2, size // 8)
    header_h = max(4, size // 4)

    # 主体 - 白色圆角矩形
    body_rect = [pad, pad, size - pad - 1, size - pad - 1]
    draw.rounded_rectangle(body_rect, radius=radius, fill="#FFFFFF", outline="#E0E0E0", width=max(1, size // 32))

    # 顶部蓝色条带
    header_rect = [pad, pad, size - pad - 1, pad + header_h]
    draw.rounded_rectangle(header_rect, radius=radius, fill="#2563EB")
    # 底部覆盖圆角（让底边是直角）
    draw.rectangle([pad, pad + header_h - radius, size - pad - 1, pad + header_h], fill="#2563EB")

    # 日期数字 "31"
    font_size = max(8, size * 4 // 10)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()

    text = "31"
    text_y = pad + header_h + (size - pad * 2 - header_h - font_size) // 2
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_x = (size - text_w) // 2
    draw.text((text_x, text_y), text, fill="#1A1A1A", font=font)

    # 顶部两个挂钩（小圆柱）
    hook_w = max(2, size // 12)
    hook_h = max(3, size // 6)
    hook_y = pad - hook_h // 3
    for x_ratio in [0.3, 0.7]:
        hx = int(size * x_ratio) - hook_w // 2
        draw.rounded_rectangle(
            [hx, hook_y, hx + hook_w, hook_y + hook_h],
            radius=max(1, hook_w // 2),
            fill="#666666",
        )

    return img


def generate_ico(output_path: str):
    """生成包含多种尺寸的 .ico 文件"""
    sizes = [16, 32, 48, 64, 128, 256]
    images = [create_calendar_icon(s) for s in sizes]

    # ICO 格式需要将所有尺寸保存在一起
    images[0].save(
        output_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"图标已生成: {output_path}")
    print(f"包含尺寸: {', '.join(f'{s}x{s}' for s in sizes)}")


if __name__ == "__main__":
    output = Path(__file__).parent.parent / "assets" / "icon.ico"
    output.parent.mkdir(parents=True, exist_ok=True)
    generate_ico(str(output))
