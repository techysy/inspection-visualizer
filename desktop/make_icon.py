# -*- coding: utf-8 -*-
"""生成应用图标:渐变圆角方块 + 白色放大镜 + 镜内柱状图(呼应巡检数据可视化)
输出 desktop/icon.png(512) 与 desktop/icon.ico(多尺寸)。
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).parent
S = 512


def rounded_gradient_bg(size):
    """垂直渐变的圆角方块背景"""
    top = (79, 140, 255)    # #4F8CFF
    bottom = (34, 195, 166)  # #22C3A6
    grad = Image.new('RGB', (1, size))
    for y in range(size):
        t = y / (size - 1)
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    grad = grad.resize((size, size))

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    return img


def draw_mag_chart(img):
    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    # 放大镜镜圈
    cx, cy, r = 226, 226, 128
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=white, width=44)
    # 镜柄(左上到右下的斜柄)
    d.line([cx + int(r * 0.72), cy + int(r * 0.72), 432, 432], fill=white, width=58)
    hx, hy = 432, 432
    d.ellipse([hx - 29, hy - 29, hx + 29, hy + 29], fill=white)
    # 镜内三根柱状图(高度错落)
    base = cy + 62
    for i, (dx, h) in enumerate([(-64, 70), (0, 108), (64, 44)]):
        x0 = cx + dx - 17
        x1 = cx + dx + 17
        d.rounded_rectangle([x0, base - h, x1, base], radius=10, fill=white)
    return img


def main():
    img = rounded_gradient_bg(S)
    img = draw_mag_chart(img)
    img.save(OUT_DIR / 'icon.png')

    img.save(OUT_DIR / 'icon.ico', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print('icon.png / icon.ico written to', OUT_DIR)


if __name__ == '__main__':
    main()
