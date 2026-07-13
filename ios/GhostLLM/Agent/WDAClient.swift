import Foundation

/// Drives a device via WebDriverAgent's REST API. `HTTPWDAClient` talks to a real
/// WDA (the phone, over Tailscale or localhost); `MockWDAClient` scripts screen
/// state so the whole agent loop is testable with no device.
protocol WDAClient {
    func createSession() async throws -> String
    func windowSize() async throws -> (w: Int, h: Int)
    func tap(x: Int, y: Int) async throws
    func swipe(x1: Int, y1: Int, x2: Int, y2: Int) async throws
    func typeText(_ text: String) async throws
    func pressButton(_ name: String) async throws
    func launchApp(bundleId: String) async throws
    func openURL(_ url: String) async throws
    func source() async throws -> String
    func screenshotBase64() async throws -> String
}

enum WDAError: Error, CustomStringConvertible {
    case badStatus(Int, String)
    case noSession
    case decode(String)
    var description: String {
        switch self {
        case .badStatus(let c, let b): return "WDA HTTP \(c): \(b.prefix(200))"
        case .noSession: return "no WDA session"
        case .decode(let s): return "WDA decode: \(s)"
        }
    }
}

/// Real WDA over HTTP. `base` is e.g. http://<tailscale-ip>:8100 (never commit
/// the real IP — see docs/ios/AGENT_LOOP_BRIDGE.md).
actor HTTPWDAClient: WDAClient {
    private let base: URL
    private var sessionId: String?

    init(base: URL) { self.base = base }

    @discardableResult
    func createSession() async throws -> String {
        let body: [String: Any] = ["capabilities": ["alwaysMatch": [:], "firstMatch": [[:]]]]
        let v = try await postJSON("/session", body)
        // sessionId can be top-level or under value
        if let sid = v["sessionId"] as? String { sessionId = sid; return sid }
        if let val = v["value"] as? [String: Any], let sid = val["sessionId"] as? String { sessionId = sid; return sid }
        throw WDAError.decode("no sessionId in /session response")
    }

    func windowSize() async throws -> (w: Int, h: Int) {
        let v = try await getJSON("/session/\(try sid())/window/size")
        guard let val = v["value"] as? [String: Any],
              let w = val["width"] as? Int, let h = val["height"] as? Int else {
            throw WDAError.decode("window/size")
        }
        return (w, h)
    }

    func tap(x: Int, y: Int) async throws {
        // W3C actions: move → down → pause → up
        let action: [String: Any] = ["actions": [[
            "type": "pointer", "id": "finger1", "parameters": ["pointerType": "touch"],
            "actions": [
                ["type": "pointerMove", "duration": 0, "x": x, "y": y],
                ["type": "pointerDown", "button": 0],
                ["type": "pause", "duration": 60],
                ["type": "pointerUp", "button": 0],
            ],
        ]]]
        _ = try await postJSON("/session/\(try sid())/actions", action)
    }

    func swipe(x1: Int, y1: Int, x2: Int, y2: Int) async throws {
        let action: [String: Any] = ["actions": [[
            "type": "pointer", "id": "finger1", "parameters": ["pointerType": "touch"],
            "actions": [
                ["type": "pointerMove", "duration": 0, "x": x1, "y": y1],
                ["type": "pointerDown", "button": 0],
                ["type": "pointerMove", "duration": 300, "x": x2, "y": y2],
                ["type": "pointerUp", "button": 0],
            ],
        ]]]
        _ = try await postJSON("/session/\(try sid())/actions", action)
    }

    func typeText(_ text: String) async throws {
        // Focus the active element, then set value (WDA types char-by-char).
        let active = try await postJSON("/session/\(try sid())/element/active", [:])
        let elemId = ((active["value"] as? [String: Any])?["ELEMENT"] as? String)
            ?? ((active["value"] as? [String: Any])?["element-6066-11e4-a52e-4f735466cecf"] as? String)
        if let elemId {
            _ = try await postJSON("/session/\(try sid())/element/\(elemId)/value", ["value": Array(text.map(String.init))])
        } else {
            _ = try await postJSON("/session/\(try sid())/wda/keys", ["value": Array(text.map(String.init))])
        }
    }

    func pressButton(_ name: String) async throws {
        _ = try await postJSON("/session/\(try sid())/wda/pressButton", ["name": name])
    }

    func launchApp(bundleId: String) async throws {
        _ = try await postJSON("/session/\(try sid())/wda/apps/launch", ["bundleId": bundleId])
    }

    func openURL(_ url: String) async throws {
        _ = try await postJSON("/session/\(try sid())/url", ["url": url])
    }

    func source() async throws -> String {
        let v = try await getJSON("/session/\(try sid())/source")
        return (v["value"] as? String) ?? ""
    }

    func screenshotBase64() async throws -> String {
        let v = try await getJSON("/session/\(try sid())/screenshot")
        return (v["value"] as? String) ?? ""
    }

    // MARK: - HTTP helpers

    private func sid() throws -> String {
        guard let sessionId else { throw WDAError.noSession }
        return sessionId
    }

    private func getJSON(_ path: String) async throws -> [String: Any] {
        var req = URLRequest(url: base.appendingPathComponent(path))
        req.timeoutInterval = 30
        return try await send(req)
    }

    private func postJSON(_ path: String, _ body: [String: Any]) async throws -> [String: Any] {
        var req = URLRequest(url: base.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.timeoutInterval = 30
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await send(req)
    }

    private func send(_ req: URLRequest) async throws -> [String: Any] {
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            throw WDAError.badStatus(code, String(decoding: data, as: UTF8.self))
        }
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }
}
