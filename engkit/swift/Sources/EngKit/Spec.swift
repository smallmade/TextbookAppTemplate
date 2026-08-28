import CryptoKit
import Foundation

/// 正典载入与校验，Swift 侧。
///
/// **架构不变量 3**：Swift 与 Python 读同一份 specification.json，
/// 对同一文件求出的 digest 必须相同。两边用同一套规范化规则——键排序、
/// 无空格分隔符、UTF-8——否则「哈希相同」这条闸门就是摆设。
public enum SpecError: Error, CustomStringConvertible {
    case notFound(String)
    case malformed(String)
    case missingSymbol(String)

    public var description: String {
        switch self {
        case .notFound(let p):     return "找不到正典：\(p)"
        case .malformed(let m):    return "正典不是合法 JSON：\(m)"
        case .missingSymbol(let s):
            return "符号 \(s) 没有 meanings 条目 —— Gate 01 要求每个出现在 "
                 + "entries/outputs 的符号都有一句白话"
        }
    }
}

public struct Spec: Sendable {
    public let data: [String: Any]

    public init(data: [String: Any]) { self.data = data }

    public static func load(_ url: URL) throws -> Spec {
        guard let raw = try? Data(contentsOf: url) else {
            throw SpecError.notFound(url.path)
        }
        guard let obj = try? JSONSerialization.jsonObject(with: raw),
              let dict = obj as? [String: Any] else {
            throw SpecError.malformed(url.lastPathComponent)
        }
        return Spec(data: dict)
    }

    public var modules: [[String: Any]] {
        data["modules"] as? [[String: Any]] ?? []
    }

    public func module(_ id: String) -> [String: Any]? {
        modules.first { $0["id"] as? String == id }
    }

    public func meaning(_ symbol: String) throws -> String {
        guard let meanings = data["meanings"] as? [String: String],
              let text = meanings[symbol] else {
            throw SpecError.missingSymbol(symbol)
        }
        return text
    }

    /// 规范化 JSON 的 SHA-256。必须与 Python 侧 Spec.digest() 一致。
    ///
    /// 规范化规则要和 Python 逐字对齐：键排序、分隔符无空格、UTF-8。
    /// `.withoutEscapingSlashes` 是必要的——Foundation 默认会把 / 转义成
    /// \/，Python 不会，两边算出来就不一样了。
    public func digest() throws -> String {
        let canonical = try JSONSerialization.data(
            withJSONObject: data,
            options: [.sortedKeys, .withoutEscapingSlashes])
        return SHA256.hash(data: canonical)
            .map { String(format: "%02x", $0) }.joined()
    }
}
