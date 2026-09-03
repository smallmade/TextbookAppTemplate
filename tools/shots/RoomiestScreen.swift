/// [M-A20] Where to put a window that wants to be tall.
///
/// Prints `<x>\t<y>\t<width>\t<height>` — the top-left corner and size of the
/// **usable** area of whichever screen has the most vertical room, in the
/// coordinates System Events uses (origin top-left of the primary screen, y
/// growing downward).
///
/// Why this exists: `matrix_mac.sh` used to place every tier at `{0, 0}`,
/// which is the *primary* screen's origin. On a machine whose primary screen
/// carries the menu bar and an un-hidden Dock, 90 points of it are not
/// available, so a tier asking for a 1010-point window got 990 and was written
/// down as "本机屏幕放不下" — 36 cells of evidence discarded for a size the
/// machine could produce all along, just not on that screen. A second display
/// with no menu bar and no Dock had the full 1080.
///
/// The gate this feeds cannot tell a genuine hardware limit from a window
/// placed on the wrong screen: both arrive as a clamped height. So the
/// distinction has to be made here, before the measurement is taken.
///
///     swift tools/shots/RoomiestScreen.swift
///
/// One screen, or all screens equal: prints the primary one's visible area, so
/// the caller's behaviour is unchanged on a single-display machine.
import AppKit

guard let primary = NSScreen.screens.first else { exit(1) }
var best = primary
for screen in NSScreen.screens where screen.visibleFrame.height > best.visibleFrame.height {
    best = screen
}
let visible = best.visibleFrame
// AppKit measures from the bottom-left of the primary screen and grows upward;
// System Events measures from its top-left and grows downward.
let top = Int(primary.frame.maxY - visible.maxY)
print("\(Int(visible.minX))\t\(top)\t\(Int(visible.width))\t\(Int(visible.height))")
