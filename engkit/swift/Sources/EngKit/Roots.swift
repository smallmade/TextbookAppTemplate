import Foundation

/// 求根。与 Python 侧 engkit.roots 同名同结构——阶段 05 的对等测试比对的
/// 就是这个。
public enum RootError: Error, CustomStringConvertible {
    case noBracket(a: Double, fa: Double, b: Double, fb: Double)

    public var description: String {
        switch self {
        case .noBracket(let a, let fa, let b, let fb):
            return "f(\(a)) = \(fa) 与 f(\(b)) = \(fb) 同号，区间内不保证有根。"
                 + "多解结构应当在正典的 branching 字段里声明，并在界面上显性选择。"
        }
    }
}

/// 二分法。慢，但只要有括号就绝不失败——用作 brentq 的对照基准。
public func bisect(_ f: (Double) -> Double, _ a0: Double, _ b0: Double,
                   xtol: Double = 1e-14, rtol: Double = 1e-15,
                   maxiter: Int = 200) throws -> Double {
    var a = a0, b = b0
    var fa = f(a); let fb = f(b)
    if fa == 0 { return a }
    if fb == 0 { return b }
    guard fa * fb < 0 else { throw RootError.noBracket(a: a, fa: fa, b: b, fb: fb) }

    for _ in 0..<maxiter {
        let m = 0.5 * (a + b)
        let fm = f(m)
        if fm == 0 || (b - a) < max(xtol, rtol * abs(m)) { return m }
        if fa * fm < 0 { b = m } else { a = m; fa = fm }
    }
    return 0.5 * (a + b)
}

/// Brent 法：反二次插值 + 二分兜底。收敛快且保持括号。
public func brentq(_ f: (Double) -> Double, _ a0: Double, _ b0: Double,
                   xtol: Double = 1e-14, rtol: Double = 1e-15,
                   maxiter: Int = 100) throws -> Double {
    var a = a0, b = b0
    var fa = f(a), fb = f(b)
    if fa == 0 { return a }
    if fb == 0 { return b }
    guard fa * fb < 0 else { throw RootError.noBracket(a: a, fa: fa, b: b, fb: fb) }

    var c = a, fc = fa, d = b - a, e = d
    for _ in 0..<maxiter {
        if fb * fc > 0 { c = a; fc = fa; d = b - a; e = d }
        if abs(fc) < abs(fb) { a = b; b = c; c = a; fa = fb; fb = fc; fc = fa }
        let tol = 2 * rtol * abs(b) + 0.5 * xtol
        let m = 0.5 * (c - b)
        if abs(m) <= tol || fb == 0 { return b }

        if abs(e) < tol || abs(fa) <= abs(fb) {
            d = m; e = m                       // 退回二分
        } else {
            let s = fb / fa
            var p: Double, q: Double
            if a == c {
                p = 2 * m * s; q = 1 - s
            } else {
                let qq = fa / fc, r = fb / fc
                p = s * (2 * m * qq * (qq - r) - (b - a) * (r - 1))
                q = (qq - 1) * (r - 1) * (s - 1)
            }
            if p > 0 { q = -q }
            p = abs(p)
            if 2 * p < min(3 * m * q - abs(tol * q), abs(e * q)) {
                e = d; d = p / q
            } else { d = m; e = m }
        }
        a = b; fa = fb
        b += abs(d) > tol ? d : (m > 0 ? tol : -tol)
        fb = f(b)
    }
    return b
}
