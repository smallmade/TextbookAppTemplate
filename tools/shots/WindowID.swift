/// [E-09] The CGWindowID of an app's front window, by owner pid or owner name.
///
/// Exists so a screenshot can be addressed to **a window** rather than to a
/// rectangle of the screen (`engineering-standard.md` §5m). This machine runs
/// several Claude sessions at once; a region capture would photograph whatever
/// they happen to have open, and would go on doing so unnoticed.
///
///     swift tools/shots/WindowID.swift --pid 87749     ← prefer this
///     swift tools/shots/WindowID.swift MechanicsOne
///
/// ## Why `--pid` is the one to use
///
/// `kCGWindowOwnerName` is **not** the name System Events knows the process
/// by. StructureMechOne ships `CFBundleDisplayName = "Truss Frame"`, so the
/// accessibility layer calls it `StructureMechOne` while CGWindowList calls it
/// `Truss Frame`. Asking by the accessibility name finds nothing -- and this
/// tool's only way of saying "nothing" is to exit 1 silently, which the caller
/// reads as "the app did not launch". Two identities, one of them wrong, and
/// the error message points at the wrong thing.
///
/// A pid is the same identity on both sides. It also proves the window that
/// gets photographed belongs to the process being driven, which the name never
/// did: two apps may share a display name, and this machine has had five
/// Simulator windows belonging to four sessions.
///
/// The name form is kept because it is what the older call sites pass.
///
/// No screen geometry is used to point at anything -- the area comparison below
/// only picks among that one app's own windows, because an app can own a
/// menu-bar or tooltip window listed ahead of the real one.
///
/// Written in Swift rather than Python because the Python route needs pyobjc,
/// and a dependency added for a screenshot helper would also have to be carried
/// through the licence audit. Swift and CoreGraphics are already here.
///
/// Prints the id and exits 0, or prints nothing and exits 1 when the app has no
/// on-screen window yet. The caller polls; a fixed sleep would be tuned to
/// whichever launch happened to be timed.
import CoreGraphics
import Foundation

let arguments = CommandLine.arguments
var wantedPID: Int?
var wantedOwner: String?

switch arguments.count {
case 2:
    wantedOwner = arguments[1]
case 3 where arguments[1] == "--pid":
    wantedPID = Int(arguments[2])
    if wantedPID == nil {
        FileHandle.standardError.write("--pid 要一个数字\n".data(using: .utf8)!)
        exit(2)
    }
default:
    FileHandle.standardError.write(
        "用法: swift WindowID.swift --pid <pid> | <应用名>\n".data(using: .utf8)!)
    exit(2)
}

let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard let windows = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
        as? [[String: Any]] else {
    exit(1)
}

var bestID: Int?
var bestArea = -1.0
for window in windows {
    let mine: Bool
    if let pid = wantedPID {
        mine = (window[kCGWindowOwnerPID as String] as? Int) == pid
    } else {
        mine = (window[kCGWindowOwnerName as String] as? String) == wantedOwner
    }
    guard mine,
          let bounds = window[kCGWindowBounds as String] as? [String: Any],
          let width = bounds["Width"] as? Double,
          let height = bounds["Height"] as? Double,
          let number = window[kCGWindowNumber as String] as? Int
    else { continue }
    let area = width * height
    // A real document window, not a 1x1 helper.
    if area > bestArea && area > 10_000 {
        bestID = number
        bestArea = area
    }
}

guard let found = bestID else { exit(1) }
print(found)
