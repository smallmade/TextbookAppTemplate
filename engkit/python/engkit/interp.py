"""插值。零依赖。

查表插值是选题闸第 1 项列出的三种「非平凡」之一（蒸汽表、Moody 图、
物性表都是这个形状）。
"""

from bisect import bisect_right


class OutOfRange(ValueError):
    """插值点落在表格范围之外。

    刻意不做外插：教材表格的适用范围是物理的，越界外插会安静地给出
    一个看起来合理的错数。正典的 validity 字段就是用来声明这种护栏的。
    """


def linear(xs, ys, x, *, clamp=False):
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("xs 与 ys 长度须相同且至少两点")
    if x < xs[0] or x > xs[-1]:
        if not clamp:
            raise OutOfRange(f"{x} 落在表格范围 [{xs[0]}, {xs[-1]}] 之外")
        x = min(max(x, xs[0]), xs[-1])
    i = min(max(bisect_right(xs, x) - 1, 0), len(xs) - 2)
    x0, x1, y0, y1 = xs[i], xs[i + 1], ys[i], ys[i + 1]
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def bilinear(xs, ys, grid, x, y, *, clamp=False):
    """二维查表：grid[j][i] 对应 (xs[i], ys[j])。蒸汽表就是这个形状。"""
    row_at = lambda j: linear(xs, grid[j], x, clamp=clamp)
    if y < ys[0] or y > ys[-1]:
        if not clamp:
            raise OutOfRange(f"{y} 落在表格范围 [{ys[0]}, {ys[-1]}] 之外")
        y = min(max(y, ys[0]), ys[-1])
    j = min(max(bisect_right(ys, y) - 1, 0), len(ys) - 2)
    y0, y1 = ys[j], ys[j + 1]
    v0, v1 = row_at(j), row_at(j + 1)
    if y1 == y0:
        return v0
    return v0 + (v1 - v0) * (y - y0) / (y1 - y0)
