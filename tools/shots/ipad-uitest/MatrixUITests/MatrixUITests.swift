import XCTest

/// [M-A21] Walk every screen of the iPad build and photograph each one.
///
/// ## Why this exists
///
/// `matrix_ipad.sh` used to switch screens through macOS System Events, driving
/// the Simulator's accessibility bridge the same way the Mac half drives the
/// real app. That was never able to work, for two reasons measured on 2026-09-03:
///
///   * the sidebar path from `ci.toml` does not resolve inside the Simulator
///     process at all -- it describes the *macOS* app's split view;
///   * `select_screen` decided which screen it had reached by reading
///     `title of window 1`, and a Simulator window's title is the **device
///     name**, so the comparison could never match.
///
/// The root cause is that an iOS app's accessibility elements are not published
/// to macOS System Events: probing a live Simulator window returns only the
/// simulator's own chrome. Worse, sending synthetic keys or clicks that way
/// delivers them to whichever application is frontmost -- on this machine, four
/// arrow keys aimed at the simulator landed in the owner's text editor.
///
/// XCUITest talks to the app inside the simulator directly, so it neither needs
/// nor can steal window focus, and every tap here is a real touch: no launch
/// argument presets a screen, nothing reads an environment variable to decide
/// what to show. That is what architecture invariant 4 asks for, and it is why
/// the screenshots are taken by driving the interface rather than by asking the
/// application to draw itself into a file.
///
/// ## Why it drives an app it did not build
///
/// There is no application target in the generated project. The matrix has
/// already installed the very binary it wants photographed; building a second
/// copy here would photograph a *different* build, which is the one thing a
/// screenshot must never do.
final class MatrixUITests: XCTestCase {

    /// `id:Title|id:Title|…`, handed over by the capture script so the list of
    /// screens has exactly one home (`RootView.swift`) rather than a copy here
    /// that drifts.
    private var screens: [(id: String, title: String)] {
        let raw = ProcessInfo.processInfo.environment["MATRIX_SCREENS"] ?? ""
        return raw.split(separator: "|").compactMap { pair in
            let parts = pair.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { return nil }
            return (String(parts[0]), String(parts[1]))
        }
    }

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testPhotographEveryScreen() throws {
        let wanted = screens
        XCTAssertFalse(wanted.isEmpty,
                       "MATRIX_SCREENS was empty -- the runner passes it as "
                       + "TEST_RUNNER_MATRIX_SCREENS; a walk over no screens "
                       + "would pass while photographing nothing")

        // Rotation lives here for the same reason the taps do: `simctl` has no
        // way to turn a device, which is why the four landscape tiers were
        // recorded as "--headless 转不了屏" and never captured at all. XCUIDevice
        // does, and it turns the device the way a hand would.
        let wantLandscape = (ProcessInfo.processInfo.environment["MATRIX_ORIENTATION"]
                             ?? "portrait") == "landscape"
        XCUIDevice.shared.orientation = wantLandscape ? .landscapeLeft : .portrait
        Thread.sleep(forTimeInterval: 2.0)

        // Handed over rather than written in: this file lives in the shared
        // template, and a bundle id baked in here is one application's identity
        // welded into every application's tooling.
        let bundleId = ProcessInfo.processInfo.environment["MATRIX_BUNDLE_ID"] ?? ""
        XCTAssertFalse(bundleId.isEmpty, "MATRIX_BUNDLE_ID was not passed")
        let app = XCUIApplication(bundleIdentifier: bundleId)
        app.activate()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 60),
                      "the installed app never came to the foreground")

        // Wait for the interface, not just for the process. `runningForeground`
        // is true the moment the app is frontmost, which is before it has drawn
        // anything -- and the first `select` then looked for a sidebar row in an
        // empty window. It cost exactly one cell, on the one pass where the app
        // had just been relaunched after an appearance switch, which is the
        // slowest launch of the run.
        XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 45),
                      "the app came to the foreground but never drew a navigation bar")
        Thread.sleep(forTimeInterval: 1.5)

        // A tier asked for in landscape that photographs a portrait screen is a
        // whole tier of evidence for a layout nobody asked about, and it looks
        // exactly like a correct run in the manifest.
        let frame = app.windows.firstMatch.frame
        XCTAssertEqual(frame.width > frame.height, wantLandscape,
                       "asked for \(wantLandscape ? "landscape" : "portrait") "
                       + "but the window is \(Int(frame.width))x\(Int(frame.height))")

        for (id, title) in wanted {
            try select(id: id, title: title, in: app)

            // The screen is named by the navigation bar's own identifier, which
            // is the app's title for it. Asserting on that rather than on "a tap
            // happened" is what stops a silent walk: a mis-tap that lands on the
            // wrong row, or a sidebar that failed to open, photographs the
            // previous screen under the next screen's name -- 18 files, all
            // plausible, all wrong.
            let bar = app.navigationBars.firstMatch
            XCTAssertTrue(bar.waitForExistence(timeout: 10), "\(id): no navigation bar")
            XCTAssertEqual(bar.identifier, title,
                           "\(id): asked for «\(title)» but the screen says "
                           + "«\(bar.identifier)»")

            // `app.screenshot()`, not `XCUIScreen.main.screenshot()`. The
            // screen's own capture comes back in the device's *physical* frame,
            // so a rotated tier produced a portrait-shaped PNG of a landscape
            // layout -- content lying on its side, and pixel dimensions that
            // could never match the tier the gate is checking against.
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = id
            shot.lifetime = .keepAlways
            add(shot)
        }
    }

    /// The button that opens the sidebar, whatever it is calling itself today.
    ///
    /// Its label is **not** stable: portrait shows `Toggle sidebar`, landscape
    /// with the sidebar hidden shows `Show Sidebar`, and hidden/shown swap it
    /// again. Matching one spelling worked in portrait and then failed on the
    /// second screen of every landscape tier -- the sidebar simply never opened,
    /// and the run died looking for a row that was not on screen.
    ///
    /// So: try the spellings, then fall back to the navigation bar's leading
    /// button, which is what this control is regardless of its name.
    private func sidebarToggle(in app: XCUIApplication) -> XCUIElement {
        for label in ["Toggle sidebar", "Show Sidebar", "Hide Sidebar",
                      "Toggle Sidebar", "Show sidebar"] {
            let candidate = app.buttons[label].firstMatch
            if candidate.exists { return candidate }
        }
        return app.navigationBars.buttons.element(boundBy: 0)
    }

    /// Open the sidebar if it is closed, then tap the row for this screen.
    ///
    /// Rows are addressed by `screen-row-<id>`, the accessibility identifier
    /// the sidebar attaches in `RootView.swift`. They used to be addressed by
    /// their visible title, and that is what broke every landscape tier: the
    /// title is prose, and the one control the walk depends on -- the sidebar
    /// toggle -- renames itself between `Toggle sidebar` and `Show Sidebar`
    /// depending on orientation and state. An identifier is chosen once and
    /// does not move when someone rewords a heading.
    private func select(id: String, title: String, in app: XCUIApplication) throws {
        let identifier = "screen-row-\(id)"
        var row = app.descendants(matching: .any)[identifier].firstMatch
        var attempt = 0
        while !row.exists && attempt < 3 {
            attempt += 1
            let toggle = sidebarToggle(in: app)
            if toggle.exists {
                toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
                    .tap()
                Thread.sleep(forTimeInterval: 1.5)
            }
            row = app.descendants(matching: .any)[identifier].firstMatch
            _ = row.waitForExistence(timeout: 4)
        }
        if !row.exists {
            let dump = XCTAttachment(string: app.debugDescription)
            dump.name = "hierarchy-when-\(id)-was-missing"
            dump.lifetime = .keepAlways
            add(dump)
            let picture = XCTAttachment(screenshot: app.screenshot())
            picture.name = "screen-when-\(id)-was-missing"
            picture.lifetime = .keepAlways
            add(picture)
            XCTFail("no sidebar row «\(identifier)» (\(title)) — hierarchy attached")
            return
        }
        row.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        Thread.sleep(forTimeInterval: 1.0)
    }
}
