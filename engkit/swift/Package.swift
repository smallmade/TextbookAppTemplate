// swift-tools-version:5.10
//
// EngKit —— 七款 App 共用的零依赖工具层，Swift 侧。
//
// 版本纪律：每个 App pin 一个具体 tag，不用 main。否则改动 EngKit 会同时
// 打破七个 App，而你不会知道是哪一次改动干的。
import PackageDescription

let package = Package(
    name: "EngKit",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [.library(name: "EngKit", targets: ["EngKit"])],
    targets: [
        .target(name: "EngKit"),
        .testTarget(name: "EngKitTests", dependencies: ["EngKit"]),
    ]
)
