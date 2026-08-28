import Foundation
import Testing
@testable import EngKit

/// 这些测试守的是**跨语言一致性**，不是「Swift 侧算得对」。
///
/// 后者由各 App 自己的 conformance fixture 负责，用的是层 2 高精度值
/// （20 位有效数字），而不是层 1 的四位印刷数字——四位分不出「正确的翻译」
/// 和「有细微失误的翻译」：一个 pow 写错、一个减法次序颠倒，会在第十二位
/// 显现，远早于第四位。

@Suite("求根")
struct RootTests {
    @Test("brentq 解 x²−2，精度到最后一位")
    func brentqSqrt2() throws {
        let root = try brentq({ $0 * $0 - 2 }, 0, 2)
        #expect(abs(root - 2.0.squareRoot()) < 1e-15)
    }

    @Test("bisect 与 brentq 收敛到同一个根")
    func agreement() throws {
        let f: (Double) -> Double = { cos($0) - $0 }
        let a = try brentq(f, 0, 1)
        let b = try bisect(f, 0, 1)
        #expect(abs(a - b) < 1e-12)
    }

    @Test("同号端点必须报错，不能静默返回一个数")
    func noBracketThrows() {
        // 多解结构应当在正典的 branching 字段里声明、在界面上显性选择，
        // 而不是由求根函数悄悄挑一个根返回。
        #expect(throws: RootError.self) {
            try brentq({ $0 * $0 + 1 }, 0, 2)
        }
    }
}

@Suite("单位")
struct UnitTests {
    @Test("数值与 Python 侧逐位一致")
    func matchesPython() throws {
        #expect(try toSI(100, "temperature", "degC") == 373.15)
        #expect(try abs(toSI(14.7, "pressure", "psi") - 101352.9322095696) < 1e-9)
        #expect(try toSI(1, "length", "in") == 0.0254)
    }

    @Test("往返无损")
    func roundTrip() throws {
        for (q, u, v) in [("pressure", "psi", 14.7),
                          ("temperature", "degF", 98.6),
                          ("length", "ft", 12.0)] {
            let back = try fromSI(try toSI(v, q, u), q, u)
            #expect(abs(back - v) < 1e-12)
        }
    }

    @Test("未知单位必须报错")
    func unknownUnit() {
        #expect(throws: UnitError.self) { try toSI(1, "pressure", "furlong") }
    }
}

@Suite("正典")
struct SpecTests {
    /// 架构不变量 3：两端读同一份正典，digest 必须相同。
    ///
    /// 这个测试只能证明 Swift 侧的规范化规则是稳定的；**真正的跨语言比对
    /// 要在 CI 里做**——把同一个 specification.json 分别喂给
    /// `python -c "from engkit import load; print(load(p).digest())"` 和
    /// 这里的 digest()，两个值必须一字不差。
    @Test("digest 稳定且不转义斜杠")
    func digestStable() throws {
        let json = #"{"b":2,"a":"x/y"}"#.data(using: .utf8)!
        let dict = try JSONSerialization.jsonObject(with: json) as! [String: Any]
        let d1 = try Spec(data: dict).digest()
        let d2 = try Spec(data: dict).digest()
        #expect(d1 == d2)
        #expect(d1.count == 64)
    }

    @Test("缺失符号必须报错，不能返回空串")
    func missingSymbolThrows() {
        let spec = Spec(data: ["meanings": ["M": "弯矩"]])
        #expect(throws: SpecError.self) { try spec.meaning("Q") }
    }
}
