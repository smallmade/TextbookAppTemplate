"""单位换算。零依赖。

规范 阶段 03 的 dimension 层纪律：**内部一律 SI，不流出去。** 换算只在
边界做一次——进来时转成 SI，出去时转回用户选的单位，中间层完全不知道
单位的存在。

这一条使得 kernel 可以逐行移植到 Swift：它不需要带一套单位系统过去。
"""


class UnitError(ValueError):
    pass


# 量纲 → {单位: (乘数, 偏移)}；SI 值 = 用户值 * 乘数 + 偏移
FACTORS: dict[str, dict[str, tuple[float, float]]] = {
    "length":      {"m": (1.0, 0.0), "mm": (1e-3, 0.0), "cm": (1e-2, 0.0),
                    "km": (1e3, 0.0), "in": (0.0254, 0.0), "ft": (0.3048, 0.0)},
    "mass":        {"kg": (1.0, 0.0), "g": (1e-3, 0.0), "lb": (0.45359237, 0.0)},
    "force":       {"N": (1.0, 0.0), "kN": (1e3, 0.0), "lbf": (4.4482216152605, 0.0)},
    "pressure":    {"Pa": (1.0, 0.0), "kPa": (1e3, 0.0), "MPa": (1e6, 0.0),
                    "GPa": (1e9, 0.0), "bar": (1e5, 0.0), "psi": (6894.757293168, 0.0),
                    "atm": (101325.0, 0.0)},
    "temperature": {"K": (1.0, 0.0), "degC": (1.0, 273.15),
                    "degF": (5.0 / 9.0, 255.3722222222222)},
    "energy":      {"J": (1.0, 0.0), "kJ": (1e3, 0.0), "MJ": (1e6, 0.0),
                    "cal": (4.184, 0.0), "BTU": (1055.05585262, 0.0)},
    "angle":       {"rad": (1.0, 0.0), "deg": (0.017453292519943295, 0.0)},
}


def _lookup(quantity: str, unit: str) -> tuple[float, float]:
    try:
        table = FACTORS[quantity]
    except KeyError:
        raise UnitError(f"未知量纲 {quantity!r}；已知：{sorted(FACTORS)}") from None
    try:
        return table[unit]
    except KeyError:
        raise UnitError(
            f"{quantity} 没有单位 {unit!r}；可用：{sorted(table)}") from None


def to_si(value: float, quantity: str, unit: str) -> float:
    mul, off = _lookup(quantity, unit)
    return value * mul + off


def from_si(value: float, quantity: str, unit: str) -> float:
    mul, off = _lookup(quantity, unit)
    return (value - off) / mul


def round_trip_error(value: float, quantity: str, unit: str) -> float:
    """换算往返误差。dimension 层的性质测试直接用它。"""
    return abs(from_si(to_si(value, quantity, unit), quantity, unit) - value)
