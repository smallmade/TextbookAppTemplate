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

──────────────────────────────────────────────────────────────
[M-03] 两处新增。

**一、它数到 0 的时候必须变红。**

它接受一个位置参数（测试目录）。有人按别的闸门的习惯写了 `--root .`，
于是它去 `Path("--root").glob("test_*.py")` 里找，找到零个文件，打印
「✓ 0 个测试函数，全部在文件里、有内容、有断言」，退出 0。**在 2246 个
测试面前。** 这就是规范点名的最坏形态：查了零个对象，然后报通过。

现在两件事一起改：认 `--root`（从 ci.toml 读 tests_dir），以及
**N == 0 一律未通过**。

**二、「有断言」不等于「断言能失败」。**

上一版只问「有没有断言」。一个 `assert x or True` 有断言，永远绿，
什么也没验证。实测样本：MechanicsOne 的 `test_boundaries.py` 里
`assert (... ) or True` —— 加上 `or True` 之后整条断言恒真。

四类恒真断言，逐条报出文件:行：
  * `assert True` / `assert 1` / `assert "x"` —— 常数真值；
  * `assert <任何东西> or True` —— 短路到真；
  * `assert not False` 之类的常数取反；
  * **对可能为空的推导式做全称断言** —— `assert all(f(x) for x in xs)` 与
    `assert not any(...)` 在 `xs` 为空时恒真。这一类不判死：只有当这个测试
    **没有**任何一处断言那个集合非空（`assert xs`、`len(xs) > 0`、
    `assert xs, "..."`）时才报。空集合上的全称命题为真，是数理逻辑，
    不是缺陷——缺陷是没有人检查那个集合是不是空的。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402


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


#: 恒真的常数。`assert 0.0` 会失败，所以不能一律看 truthiness——
#: 只有真值为真的常数才是恒真断言。
def _always_true_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and bool(node.value)


def _tautological(test_node: ast.AST) -> str | None:
    """这条断言表达式恒真吗？返回一句说明，或 None。"""
    if _always_true_constant(test_node):
        return f"assert {ast.unparse(test_node)} —— 常数真值，永远不会失败"
    if isinstance(test_node, ast.BoolOp) and isinstance(test_node.op, ast.Or):
        for value in test_node.values:
            if _always_true_constant(value):
                return ("短路到 `or " + ast.unparse(value)
                        + "` —— 整条断言恒真，左边算什么都不影响")
    if (isinstance(test_node, ast.UnaryOp) and isinstance(test_node.op, ast.Not)
            and isinstance(test_node.operand, ast.Constant)
            and not test_node.operand.value):
        return f"assert {ast.unparse(test_node)} —— 常数取反，永远不会失败"
    return None


#: 全称量词。对空集合恒真。
UNIVERSAL = {"all"}
EXISTENTIAL = {"any"}


def _pins_nonempty(func: ast.AST, iterable: str) -> bool:
    """这个函数里有没有一条断言，能保证 `iterable` 不是空的？

    判据要具体到**同一个可迭代对象**，不能只问「这个测试里有没有出现过
    len(...)」——那样任何一条无关的长度断言都会替一条真正的空集漏洞背书。
    算数的四种写法：

        assert xs                      裸真值
        assert len(xs) > 0 / >= 1 / != 0 / == 3
        assert xs == <非空字面量>       等式钉死内容，顺带钉死非空
        assert y in xs                 成员关系蕴含非空
    """
    for node in ast.walk(func):
        if not isinstance(node, ast.Assert):
            continue
        expr = node.test
        if isinstance(expr, ast.Name) and expr.id == iterable:
            return True
        if not isinstance(expr, ast.Compare):
            continue
        left, right = ast.unparse(expr.left), [ast.unparse(c)
                                               for c in expr.comparators]
        # len(xs) <op> n
        if left == f"len({iterable})":
            for op, comparator in zip(expr.ops, expr.comparators):
                if isinstance(op, (ast.Gt, ast.GtE, ast.NotEq)):
                    return True
                if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) \
                        and isinstance(comparator.value, int) and comparator.value > 0:
                    return True
        # xs == <非空字面量>
        if left == iterable:
            for op, comparator in zip(expr.ops, expr.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) \
                        and isinstance(comparator, ast.Constant) \
                        and comparator.value not in ("", None) \
                        and bool(comparator.value):
                    return True
        # y in xs
        for op, comparator in zip(expr.ops, expr.comparators):
            if isinstance(op, ast.In) and ast.unparse(comparator) == iterable:
                return True
        if iterable in right and any(isinstance(op, (ast.Eq, ast.NotEq))
                                     for op in expr.ops):
            # <非空字面量> == xs，写反了的那一半
            if isinstance(expr.left, ast.Constant) and bool(expr.left.value):
                return True
    return False


def _vacuous_universals(func: ast.AST) -> list[str]:
    """全称断言作用在推导式上，而这个函数没有断言过那个集合非空。

    `assert all(f(x) for x in xs)` 与 `assert not any(...)` 在 xs 为空时
    恒真。空集合上的全称命题为真是数理逻辑，不是缺陷；缺陷是**没有人检查
    那个集合是不是空的**——`xs` 因为一个 bug 返回了空，这条测试照样绿。

    修法通常只有一行：在旁边加一句 `assert len(xs) == 3`。
    """
    found: list[str] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Assert):
            continue
        expr = node.test
        negated = False
        if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
            expr, negated = expr.operand, True
        if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)):
            continue
        name = expr.func.id
        if name not in (UNIVERSAL | EXISTENTIAL):
            continue
        if name in EXISTENTIAL and not negated:
            continue            # `assert any(...)` on an empty set FAILS. Fine.
        if not expr.args or not isinstance(
                expr.args[0], (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            continue
        generators = expr.args[0].generators
        if not generators:
            continue
        iterable = ast.unparse(generators[0].iter)
        if _pins_nonempty(func, iterable):
            continue
        found.append(f"line {node.lineno}: assert "
                     f"{'not ' if negated else ''}{name}(... for ... in "
                     f"{iterable[:48]}) —— 集合为空时恒真，"
                     f"而这个函数没有断言过它非空")
    return found


def scan(root: Path):
    """返回 (统计, 各类问题清单)。抽出来是为了自检能直接调它。"""
    empty_files: list[str] = []
    empty_tests: list[str] = []
    assertionless: list[str] = []
    tautologies: list[str] = []
    total = 0
    files = 0

    for path in sorted(root.glob("test_*.py")):
        files += 1
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

        # [M-03] 有断言 ≠ 断言能失败。
        #
        # 这一遍走**模块里的每一个函数**，不只是 test_*。理由与这道闸门
        # 上一次被迫放宽时一样：这个仓库把断言托付给同模块的探针
        # （`PROBES[boundary]()` 里那些 `m20_b3()`）。只看 test_* 的话，
        # 那个已知实例——`assert not any(...) or True`——就正好落在盲区里，
        # 而它就是本条判据的来源样本。
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if not isinstance(node, ast.Assert):
                    continue
                why = _tautological(node.test)
                if why:
                    tautologies.append(
                        f"{path.name}:{node.lineno}::{func.name}  {why}")
            for line in _vacuous_universals(func):
                tautologies.append(f"{path.name}::{func.name}  {line}")

    # 同一条 assert 可能被两个嵌套的函数各数一次，去重后再报。
    tautologies = sorted(set(tautologies))
    return (files, total), (empty_files, empty_tests, assertionless, tautologies)


def report(root: Path) -> int:
    (files, total), (empty_files, empty_tests, assertionless,
                     tautologies) = scan(root)

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
    if tautologies:
        print(f"✗ {len(tautologies)} 处断言【不可能失败】：")
        for line in tautologies:
            print(f"    {line}")
        print("  一条恒真的断言与一条被删掉的断言，在日志里长得一模一样，"
              "而前者还占着一行覆盖率。")
        failed = True

    print(checked(total, "个测试函数", f"{files} 个 test_*.py"))
    if total == 0:
        print("✗ 一个测试函数都没数到——这不是「全部合格」，这是没检查。")
        print("  路径给对了吗？位置参数是测试目录；--root 指项目根，"
              "由 ci.toml 的 tests_dir 决定看哪儿。")
        return 1
    if failed:
        return 1
    print(f"✓ {total} 个测试函数，全部在文件里、有内容、有能失败的断言"
          f"（含托付给同模块辅助函数的）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tests", nargs="?", type=Path, default=None,
                    help="测试目录；不给就从 ci.toml 的 tests_dir 读")
    ap.add_argument("--root", type=Path, default=None,
                    help="项目根，用来找 ci.toml")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_test_files.py 自检")
        return self_test()

    root = args.tests
    if root is None:
        project = args.root or Path(".")
        cfg = load_config(project)
        root = cfg.path("tests_dir") or (project / "python" / "tests")
    if not root.is_dir():
        print(f"尚不适用：还没有测试目录 {root}（阶段 02 之前正常）",
              file=sys.stderr)
        return 2
    return report(root)


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
    # [M-03] 恒真断言。头一条照抄 MechanicsOne 的实例
    # （python/tests/test_boundaries.py 里 `... or True` 那一条）。
    ("`or True` 结尾的断言",
     "def test_a():\n    x = 1\n    assert (x == 2) or True\n", "tautologies"),
    ("assert True", "def test_a():\n    assert True\n", "tautologies"),
    ("assert 1", "def test_a():\n    assert 1\n", "tautologies"),
    ("assert not False", "def test_a():\n    assert not False\n", "tautologies"),
    ("对可能为空的推导式做全称断言",
     "def test_a():\n    rows = load()\n"
     "    assert all(r > 0 for r in rows)\n", "tautologies"),
    ("同上，但先断言了集合非空",
     "def test_a():\n    rows = load()\n    assert len(rows) > 0\n"
     "    assert all(r > 0 for r in rows)\n", None),
    ("同上，非空由等式钉住（内容断言顺带钉死长度）",
     "def test_a():\n    text = render()\n    assert text == 'abc'\n"
     "    assert all(c.islower() for c in text)\n", None),
    ("同上，非空由无关集合的长度断言「背书」——不算数",
     "def test_a():\n    rows = load()\n    other = load2()\n"
     "    assert len(other) > 0\n"
     "    assert all(r > 0 for r in rows)\n", "tautologies"),
    ("`assert any(...)` —— 空集合上会失败，不是恒真",
     "def test_a():\n    rows = load()\n"
     "    assert any(r > 0 for r in rows)\n", None),
    ("assert 0 —— 常数，但会失败，不算恒真",
     "def test_a():\n    assert 0 == 0\n", None),
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

    # [M-03] 零对象。这是它上一次静默放行的确切形状：`--root .` 被当成
    # 位置参数，`Path("--root").glob(...)` 找到零个文件，报「✓ 0 个测试
    # 函数」并退出 0——在 2246 个测试面前。
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "not_a_test.py").write_text("x = 1\n", encoding="utf-8")
        argv, sys.argv = sys.argv, ["check_test_files.py", tmp]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = main()
        finally:
            sys.argv = argv
    good = code == 1
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  拒绝  一个测试函数都没数到"
          f"（0 个对象 ≠ 通过）")

    print("\n自检通过——闸门既不漏报也不乱叫" if ok else "\n自检失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
