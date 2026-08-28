import Foundation

/// 单位换算。与 Python 侧 engkit.units 同名同结构、同数值。
///
/// dimension 层纪律：**内部一律 SI，不流出去。** 换算只在边界做一次。
public enum UnitError: Error, CustomStringConvertible {
    case unknownQuantity(String)
    case unknownUnit(quantity: String, unit: String)

    public var description: String {
        switch self {
        case .unknownQuantity(let q):  return "未知量纲 \(q)"
        case .unknownUnit(let q, let u): return "\(q) 没有单位 \(u)"
        }
    }
}

/// SI 值 = 用户值 * 乘数 + 偏移。数值必须与 Python 侧逐位一致。
public let unitFactors: [String: [String: (mul: Double, off: Double)]] = [
    "length":      ["m": (1, 0), "mm": (1e-3, 0), "cm": (1e-2, 0),
                    "km": (1e3, 0), "in": (0.0254, 0), "ft": (0.3048, 0)],
    "mass":        ["kg": (1, 0), "g": (1e-3, 0), "lb": (0.45359237, 0)],
    "force":       ["N": (1, 0), "kN": (1e3, 0), "lbf": (4.4482216152605, 0)],
    "pressure":    ["Pa": (1, 0), "kPa": (1e3, 0), "MPa": (1e6, 0),
                    "GPa": (1e9, 0), "bar": (1e5, 0),
                    "psi": (6894.757293168, 0), "atm": (101325, 0)],
    "temperature": ["K": (1, 0), "degC": (1, 273.15),
                    "degF": (5.0 / 9.0, 255.3722222222222)],
    "energy":      ["J": (1, 0), "kJ": (1e3, 0), "MJ": (1e6, 0),
                    "cal": (4.184, 0), "BTU": (1055.05585262, 0)],
    "angle":       ["rad": (1, 0), "deg": (0.017453292519943295, 0)],
]

private func lookup(_ quantity: String, _ unit: String) throws
        -> (mul: Double, off: Double) {
    guard let table = unitFactors[quantity] else {
        throw UnitError.unknownQuantity(quantity)
    }
    guard let f = table[unit] else {
        throw UnitError.unknownUnit(quantity: quantity, unit: unit)
    }
    return f
}

public func toSI(_ value: Double, _ quantity: String, _ unit: String) throws -> Double {
    let f = try lookup(quantity, unit)
    return value * f.mul + f.off
}

public func fromSI(_ value: Double, _ quantity: String, _ unit: String) throws -> Double {
    let f = try lookup(quantity, unit)
    return (value - f.off) / f.mul
}
