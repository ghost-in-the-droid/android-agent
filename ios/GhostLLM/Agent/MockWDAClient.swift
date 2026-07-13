import Foundation

/// Scripted WDA for phone-free testing of the agent loop. Records every call and
/// returns canned screen state, so the loop's plumbing can be validated on the
/// simulator with no device.
actor MockWDAClient: WDAClient {
    private(set) var calls: [String] = []
    private let cannedSource: String
    private let cannedShot: String

    init(source: String = "<XCUIElementTypeButton name=\"Settings\" x=\"100\" y=\"200\"/>",
         screenshot: String = "iVBORw0KGgo=") {
        self.cannedSource = source
        self.cannedShot = screenshot
    }

    func createSession() async throws -> String { calls.append("createSession"); return "mock-session" }
    func windowSize() async throws -> (w: Int, h: Int) { calls.append("windowSize"); return (393, 852) }
    func tap(x: Int, y: Int) async throws { calls.append("tap(\(x),\(y))") }
    func swipe(x1: Int, y1: Int, x2: Int, y2: Int) async throws { calls.append("swipe(\(x1),\(y1)->\(x2),\(y2))") }
    func typeText(_ text: String) async throws { calls.append("type(\(text))") }
    func pressButton(_ name: String) async throws { calls.append("pressButton(\(name))") }
    func launchApp(bundleId: String) async throws { calls.append("launchApp(\(bundleId))") }
    func openURL(_ url: String) async throws { calls.append("openURL(\(url))") }
    func source() async throws -> String { calls.append("source"); return cannedSource }
    func screenshotBase64() async throws -> String { calls.append("screenshot"); return cannedShot }
}
