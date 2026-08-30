#!/usr/bin/env python3
"""闸门 —— 每一个 test_*.py 里必须真的有测试。

一个叫 `test_deflection_curve.py` 的空文件，看起来像弹性曲线被测过了。
它没有。**文件名不是覆盖率。**

这是「没有人写的 fixture，比较的是零」的文件级版本：目录里多一个文件，
`ls` 的输出更长，pytest 收集到零个用例而不会说一个字。coverage 也不会——
被别处的测试覆盖到的模块，照样是绿的。

顺带检查两件同类的事：
  * 只有 `pass` 或 `...` 的测试函数——名字在，断言不在；
  * 一个断言都没有的测试函数——跑得过，什么也没验证。

**「有断言」是【传递】判定的。** 一个测试可以把断言托付给同模块里的辅助
函数（`agrees(...)`、`PROBES[boundary]()`），那仍然是在验证。第一版只看
函数体里有没有 `assert` 字样，于是把九个真正在断言的测试报成「一个断言都
没有」——而规范自己写着：**一个会乱叫的闸门两天之内就会被关掉。**
所以这里跟着调用走：同模块内被调用的函数，它们的断言也算。

**同目录内的导入跟一层。** 第一版刻意不跟跨模块调用，理由是「需要真正的
导入解析」。但共享一个断言辅助（`from tests.support import
agrees_with_reference`）恰恰是对的设计——两份拷贝会漂——于是这道闸门把
53 个真正在断言的测试报成了「一个断言都没有」。**又一次乱叫。**

所以它现在解析 `from <同目录模块> import ...`，把那个模块里自带断言的函数
名也算进来。只跟同目录、只跟一层：再远就是被测代码本身了。
`--self-test` 交给它已知不合格的样本，两个方向都查。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _asserting_helpers(tree: ast.Module) -> set[str]:
    """模块里自己带断言的函数名。

    包括 lambda 之外的所有 def：辅助断言函数通常就叫 `agrees` / `check`，
    而把它们的名字写死在闸门里，就又变成一份手写清单了。
    """
    named: dict[str, ast.AST] = {
        node.name: node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {name for name, node in named.items()
            if any(isinstance(inner, (ast.Assert, ast.Raise))
                   for inner in ast.walk(node))}


def _imported_helpers(tree: ast.Module, directory: Path) -> set[str]:
    """自带断言的、从同目录模块导入进来的名字。

    `from tests.support import agrees_with_reference as agrees` 之后，
    测试里写的是 `agrees(...)`，而断言在 support.py 里。跟这一层，
    否则共享断言辅助这件事本身会被判成没有断言。
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        sibling = directory / f"{node.module.rsplit('.', 1)[-1]}.py"
        if not sibling.is_file():
            continue
        try:
            asserting = _asserting_helpers(ast.parse(
                sibling.read_text(encoding="utf-8")))
        except SyntaxError:
            continue
        for alias in node.names:
            if alias.name in asserting:
                found.add(alias.asname or alias.name)
    return found


def _registries(tree: ast.Module) -> dict[str, set[str]]:
    """模块级的 `{键: 函数名}` 字典 —— 探针登记表就是这个形状。

    `PROBES[boundary]()` 调用的不是 `PROBES`，是它的某个值。不解开这一层，
    整个「登记表 + 参数化」的写法都会被判成没有断言。
    """
    found: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            continue
        names = {v.id for v in value.values if isinstance(v, ast.Name)}
        if not names:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                found[target.id] = names
    return found


def _calls(test: ast.AST, registries: dict[str, set[str]]) -> set[str]:
    """这个测试调用了哪些名字（含 `d[key]()` 这种经由登记表的调用）。"""
    found: set[str] = set()
    for node in ast.walk(test):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Subscript):        # PROBES[boundary]()
            inner = target.value
            if isinstance(inner, ast.Name):
                found |= registries.get(inner.id, set())
                found.add(inner.id)
            continue
        if isinstance(target, ast.Name):
            found.add(target.id)
        elif isinstance(target, ast.Attribute):
            found.add(target.attr)
    return found


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "python/tests")
    empty_files: list[str] = []
    empty_tests: list[str] = []
    assertionless: list[str] = []
    total = 0

    for path in sorted(root.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            print(f"✗ {path.name} 无法解析：{error}")
            return 1
        tests = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name.startswith("test_")]
        if not tests:
            empty_files.append(path.name)
            continue
        total += len(tests)
        helpers = _asserting_helpers(tree) | _imported_helpers(tree, root)
        registries = _registries(tree)
        for test in tests:
            body = [node for node in test.body
                    if not (isinstance(node, ast.Expr)
                            and isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str))]
            if not body or all(isinstance(node, (ast.Pass, ast.Expr))
                               and not isinstance(getattr(node, "value", None),
                                                  ast.Call)
                               for node in body):
                empty_tests.append(f"{path.name}::{test.name}")
                continue
            has_check = any(isinstance(node, (ast.Assert, ast.Raise))
                            for node in ast.walk(test))
            calls_pytest = any(isinstance(node, ast.Attribute)
                               and node.attr in {"raises", "approx", "fail",
                                                 "warns", "skip", "xfail"}
                               for node in ast.walk(test))
            # 断言可以托付出去：调用同模块里一个自己带断言的函数，
            # 和把 assert 写在这里是同一件事。
            delegates = bool(_calls(test, registries) & (helpers - {test.name}))
            if not has_check and not calls_pytest and not delegates:
                assertionless.append(f"{path.name}::{test.name}")

    failed = False
    if empty_files:
        print(f"✗ {len(empty_files)} 个 test_*.py 里一个测试都没有：")
        for name in empty_files:
            print(f"    {name}")
        print("  文件名不是覆盖率。要么写进测试，要么把文件删掉。")
        failed = True
    if empty_tests:
        print(f"✗ {len(empty_tests)} 个测试函数是空的：")
        for name in empty_tests:
            print(f"    {name}")
        failed = True
    if assertionless:
        print(f"✗ {len(assertionless)} 个测试函数一个断言都没有：")
        for name in assertionless:
            print(f"    {name}")
        print("  跑得过不等于验证了什么。")
        failed = True

    if failed:
        return 1
    print(f"✓ {total} 个测试函数，全部在文件里、有内容、有断言"
          f"（含托付给同模块辅助函数的）")
    return 0


#: 已知不合格的样本，每一个都必须被抓到；外加两个必须【不】被抓到的，
#: 因为这道闸门上一次失效不是漏报，是误报。
SELF_TEST = [
    ("空文件", "", "empty_files"),
    ("只有 pass 的测试", "def test_a():\n    pass\n", "empty_tests"),
    ("只有 ... 的测试", "def test_a():\n    ...\n", "empty_tests"),
    ("没有断言的测试", "def test_a():\n    x = 1 + 1\n    print(x)\n",
     "assertionless"),
    ("直接断言", "def test_a():\n    assert 1 == 1\n", None),
    ("托付给辅助函数",
     "def agrees(a, b):\n    assert a == b\n\n"
     "def test_a():\n    agrees(1, 1)\n", None),
    ("经由字典下标调用探针",
     "def probe():\n    assert 1 == 1\n\nPROBES = {'x': probe}\n\n"
     "def test_a(k='x'):\n    PROBES[k]()\n", None),
    ("pytest.raises", "import pytest\n\ndef test_a():\n"
     "    with pytest.raises(ValueError):\n        int('x')\n", None),
]

#: 同目录导入的样本：一个 support 模块 + 一个用它的测试。
IMPORT_SELF_TEST = [
    ("从同目录导入断言辅助",
     "def agrees(a, b):\n    assert a == b\n",
     "from tests.support import agrees\n\ndef test_a():\n    agrees(1, 1)\n",
     False),
    ("导入了不断言的东西",
     "def helper(a):\n    return a + 1\n",
     "from tests.support import helper\n\ndef test_a():\n    helper(1)\n",
     True),
]


def self_test() -> int:
    import contextlib
    import io
    import tempfile
    ok = True
    for label, source, expected in SELF_TEST:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test_sample.py"
            path.write_text(source, encoding="utf-8")
            argv, sys.argv = sys.argv, ["check_test_files.py", tmp]
            try:
                # The inner run's own report would interleave with this one and
                # make a passing self-test look like a wall of failures.
                with contextlib.redirect_stdout(io.StringIO()):
                    code = main()
            finally:
                sys.argv = argv
        caught = code == 1
        want = expected is not None
        good = caught == want
        ok &= good
        verdict = "拒绝" if want else "放行"
        print(f"  {'PASS' if good else 'FAIL'}  {verdict:<4} {label}")
    for label, support_source, test_source, should_reject in IMPORT_SELF_TEST:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "support.py").write_text(support_source, encoding="utf-8")
            (Path(tmp) / "test_sample.py").write_text(test_source, encoding="utf-8")
            argv, sys.argv = sys.argv, ["check_test_files.py", tmp]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = main()
            finally:
                sys.argv = argv
        good = (code == 1) == should_reject
        ok &= good
        verdict = "拒绝" if should_reject else "放行"
        print(f"  {'PASS' if good else 'FAIL'}  {verdict}  {label}")

    print("\n自检通过——闸门既不漏报也不乱叫" if ok else "\n自检失败")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        print("check_test_files.py 自检")
        sys.exit(self_test())
    sys.exit(main())
