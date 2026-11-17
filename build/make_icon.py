#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_icon.py —— 纯标准库生成 .ico，不依赖 Pillow。

为什么要自己画：打包成品需要一个图标（exe 图标、快捷方式、卸载列表都用它），
为这一个文件装一个图像库不值得。ICO 从 Vista 起支持内嵌 PNG，所以直接
生成 PNG 再套 ICONDIR 结构即可，几十行搞定。
"""
import os
import struct
import zlib

# 配色与看板一致：深底 + 蓝青波形
BG = (15, 22, 32, 255)
EDGE = (42, 58, 77, 255)
CYAN = (56, 189, 248, 255)
VIOLET = (192, 132, 252, 255)
GRID = (30, 41, 56, 255)


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))


def draw(size):
    """返回 size×size 的 RGBA 像素行列表。坐标全部按比例缩放，任意尺寸都成立。"""
    px = [[(0, 0, 0, 0) for _ in range(size)] for _ in range(size)]
    s = float(size)

    r = s * 0.22                     # 圆角半径
    inset = s * 0.045                # 外边距
    l, t, rt, b = inset, inset, s - inset, s - inset

    def in_round_rect(x, y):
        cx = min(max(x, l + r), rt - r)
        cy = min(max(y, t + r), b - r)
        dx, dy = x - cx, y - cy
        return dx * dx + dy * dy <= r * r

    # 背景圆角矩形 + 1px 描边
    for y in range(size):
        for x in range(size):
            fx, fy = x + 0.5, y + 0.5
            if in_round_rect(fx, fy):
                px[y][x] = BG
                # 贴边一圈画描边
                if not all(in_round_rect(fx + ddx, fy + ddy)
                           for ddx, ddy in ((-1.2, 0), (1.2, 0), (0, -1.2), (0, 1.2))):
                    px[y][x] = EDGE

    # 两条水平网格线，暗示"仪表盘"
    for gy in (0.38, 0.62):
        yy = int(s * gy)
        for x in range(int(s * 0.18), int(s * 0.82)):
            if 0 <= yy < size and px[yy][x][3] == 255:
                px[yy][x] = GRID

    # 波形折线：低-高-低-中-高，用粗线画（距离场近似）
    pts = [(0.17, 0.60), (0.31, 0.44), (0.45, 0.68), (0.59, 0.34), (0.72, 0.52), (0.84, 0.42)]
    pts = [(x * s, y * s) for x, y in pts]
    thick = max(1.0, s * 0.055)

    def dist_seg(px_, py_, a, b_):
        ax, ay = a
        bx, by = b_
        vx, vy = bx - ax, by - ay
        wx, wy = px_ - ax, py_ - ay
        L2 = vx * vx + vy * vy
        tt = 0.0 if L2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
        dx, dy = wx - tt * vx, wy - tt * vy
        return (dx * dx + dy * dy) ** 0.5, tt

    for i in range(len(pts) - 1):
        a, b_ = pts[i], pts[i + 1]
        color = _lerp(CYAN, VIOLET, i / max(1, len(pts) - 2))
        x0 = int(max(0, min(a[0], b_[0]) - thick - 1))
        x1 = int(min(size, max(a[0], b_[0]) + thick + 2))
        y0 = int(max(0, min(a[1], b_[1]) - thick - 1))
        y1 = int(min(size, max(a[1], b_[1]) + thick + 2))
        for y in range(y0, y1):
            for x in range(x0, x1):
                d, _ = dist_seg(x + 0.5, y + 0.5, a, b_)
                if d <= thick / 2 and px[y][x][3] == 255:
                    px[y][x] = color

    return px


def png_bytes(px, size):
    raw = bytearray()
    for row in px:
        raw.append(0)                      # filter type 0
        for p in row:
            raw.extend(p)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)   # 8bit RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def build(path, sizes=(256, 128, 64, 48, 32, 16)):
    images = [(n, png_bytes(draw(n), n)) for n in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for n, data in images:
        # 256 在 ICONDIR 里必须写 0
        entries += struct.pack("<BBBBHHII", 0 if n >= 256 else n, 0 if n >= 256 else n,
                               0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    with open(path, "wb") as f:
        f.write(header + entries + blobs)
    return os.path.getsize(path)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    print("icon.ico 生成:", build(out), "字节 ->", out)
