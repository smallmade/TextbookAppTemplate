"""正典载入、校验与出货剥离。零依赖。

**架构不变量 3**：Swift 与 Python 读同一份 specification.json，哈希相同。
这个模块负责 Python 侧；Swift 侧对应 EngKit/Spec.swift，两边都对同一文件
求 SHA-256，值必须一致。

**strip_for_ship 是法律隔离的第一道防线**（规范 阶段 06 三道防线之首）：
打包进 App 的正典副本必须剥掉 citation 与受版权来源信息。
"""

import hashlib
import json
from pathlib import Path
from typing import Any


class SpecError(ValueError):
    pass


class Spec:
    def __init__(self, data: dict, source: Path | None = None):
        self.data = data
        self.source = source

    @property
    def modules(self) -> list[dict]:
        return self.data.get("modules", [])

    def module(self, module_id: str) -> dict:
        for m in self.modules:
            if m.get("id") == module_id:
                return m
        raise SpecError(f"正典里没有 module {module_id!r}")

    def meaning(self, symbol: str) -> str:
        try:
            return self.data["meanings"][symbol]
        except KeyError:
            raise SpecError(
                f"符号 {symbol!r} 没有 meanings 条目 —— "
                f"Gate 01 要求每个出现在 entries/outputs 的符号都有一句白话"
            ) from None

    def digest(self) -> str:
        """规范化 JSON 的 SHA-256。两端比对这个值（架构不变量 3）。"""
        canonical = json.dumps(self.data, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load(path: str | Path) -> Spec:
    p = Path(path)
    try:
        return Spec(json.loads(p.read_text(encoding="utf-8")), p)
    except FileNotFoundError:
        raise SpecError(f"找不到正典：{p}") from None
    except json.JSONDecodeError as e:
        raise SpecError(f"正典不是合法 JSON：{e}") from None


def _drop_path(data: Any, path: str) -> None:
    """按 build.strip_on_ship 里的路径表达式剥离，如 sources[].author。"""
    if "[]" in path:
        head, _, tail = path.partition("[].")
        for item in data.get(head, []):
            item.pop(tail, None)
    else:
        if isinstance(data, dict):
            data.pop(path, None)
        for m in data.get("modules", []):
            m.pop(path, None)


def strip_for_ship(spec: Spec) -> Spec:
    """产生出货副本。**这是打包时必须走的一步，不是可选项。**

    citation 保留在开发正典里（它是维护与验证的唯一依据），但永不出货：
    一款 App 会用到多部教材，界面引用任何一部都不恰当，且有法律风险。

    **sources 的剥离是按许可判断的，不是一刀切。** 受版权来源剥掉
    author/title；公有领域来源（NACA / NASA / NIST / IAPWS / CODATA）**保留
    并且应当具名**——规范 阶段 06 三层规则明确写着「具名它们反而增强可信度
    且零风险」。第一版在这里一刀切，把 NIST 的署名也剥掉了，方向正好反了。
    """
    out = json.loads(json.dumps(spec.data))  # 深拷贝

    for path in out.get("build", {}).get("strip_on_ship", []):
        if path.startswith("sources[]"):
            continue          # sources 由下面的许可判断处理，不走一刀切
        _drop_path(out, path)

    for source in out.get("sources", []):
        if source.get("licence") == "copyrighted":
            source.pop("author", None)
            source.pop("title", None)
    return Spec(out)
