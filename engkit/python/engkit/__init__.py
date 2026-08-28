"""EngKit —— 七款 App 共用的零依赖工具层。

**版本纪律**：语义化版本，每个 App pin 一个具体 tag，不用 main。否则改动
EngKit 会同时打破七个 App，而你不会知道是哪一次改动干的。

**零依赖**：这里只用标准库 math。EngKit 会被 import 进各 App 的 kernel 上层，
如果它自己带依赖，架构不变量 1 就名存实亡了。
"""

__version__ = "0.1.0"

from .roots import brentq, bisect, NoBracket  # noqa: F401
from .interp import linear, bilinear, OutOfRange  # noqa: F401
from .units import to_si, from_si, round_trip_error, UnitError  # noqa: F401
from .spec import Spec, SpecError, load, strip_for_ship  # noqa: F401
