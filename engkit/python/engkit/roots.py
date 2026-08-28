"""求根。零依赖——只用标准库 math。

教材型 App 的核心几乎总要解超越方程（选题闸第 1 项就是「算式闭式但非平凡」），
而每款都自己写一遍求根是纯粹的重复。

两个函数，覆盖实际需要：bisect 慢但绝不失败，brentq 快且同样有括号保证。
不提供 Newton 法——它需要导数，且在奇异点附近发散，而正典的 boundaries
字段标出来的恰恰就是那些点。
"""

import math


class NoBracket(ValueError):
    """f(a) 与 f(b) 同号：区间内不保证有根。"""


def _require_bracket(f, a, b):
    fa, fb = f(a), f(b)
    if fa == 0.0:
        return a, None, None
    if fb == 0.0:
        return b, None, None
    if fa * fb > 0:
        raise NoBracket(
            f"f({a}) = {fa} 与 f({b}) = {fb} 同号，区间内不保证有根。"
            f"多解结构应当在正典的 branching 字段里声明，并在界面上显性选择。"
        )
    return None, fa, fb


def bisect(f, a, b, *, xtol=1e-14, rtol=1e-15, maxiter=200):
    """二分法。慢，但只要有括号就绝不失败——用作 brentq 的对照基准。"""
    hit, fa, _ = _require_bracket(f, a, b)
    if hit is not None:
        return hit
    for _ in range(maxiter):
        m = 0.5 * (a + b)
        fm = f(m)
        if fm == 0.0 or (b - a) < max(xtol, rtol * abs(m)):
            return m
        if fa * fm < 0:
            b = m
        else:
            a, fa = m, fm
    return 0.5 * (a + b)


def brentq(f, a, b, *, xtol=1e-14, rtol=1e-15, maxiter=100):
    """Brent 法：反二次插值 + 二分兜底。收敛快且保持括号。"""
    hit, fa, fb = _require_bracket(f, a, b)
    if hit is not None:
        return hit

    c, fc = a, fa
    d = e = b - a
    for _ in range(maxiter):
        if fb * fc > 0:
            c, fc = a, fa
            d = e = b - a
        if abs(fc) < abs(fb):
            a, b, c = b, c, b
            fa, fb, fc = fb, fc, fb
        tol = 2.0 * rtol * abs(b) + 0.5 * xtol
        m = 0.5 * (c - b)
        if abs(m) <= tol or fb == 0.0:
            return b
        if abs(e) < tol or abs(fa) <= abs(fb):
            d = e = m                      # 退回二分
        else:
            s = fb / fa
            if a == c:
                p, q = 2.0 * m * s, 1.0 - s
            else:
                q, r = fa / fc, fb / fc
                p = s * (2.0 * m * q * (q - r) - (b - a) * (r - 1.0))
                q = (q - 1.0) * (r - 1.0) * (s - 1.0)
            if p > 0:
                q = -q
            p = abs(p)
            if 2.0 * p < min(3.0 * m * q - abs(tol * q), abs(e * q)):
                e, d = d, p / q
            else:
                d = e = m
        a, fa = b, fb
        b += d if abs(d) > tol else (tol if m > 0 else -tol)
        fb = f(b)
    return b


def safe_expm1(x):
    """exp(x) - 1，小 x 时不损失精度。规范 阶段 03 的数值调理纪律。"""
    return math.expm1(x)


def safe_log1p(x):
    """log(1 + x)，小 x 时不损失精度。"""
    return math.log1p(x)
