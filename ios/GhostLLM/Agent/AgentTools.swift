import Foundation

/// The tool vocabulary the on-device LLM can call to drive the phone. Maps 1:1
/// to the WDA REST surface Ghost uses (see docs/ios/AGENT_LOOP_BRIDGE.md).
enum AgentTool: String, CaseIterable {
    case tap, swipe, type, pressButton, launchApp, openURL, getUI, done

    var schemaLine: String {
        switch self {
        case .tap:         return #"{"tool":"tap","x":<int>,"y":<int>}"#
        case .swipe:       return #"{"tool":"swipe","x1":<int>,"y1":<int>,"x2":<int>,"y2":<int>}"#
        case .type:        return #"{"tool":"type","text":"<string>"}"#
        case .pressButton: return #"{"tool":"pressButton","name":"home|volumeUp|volumeDown"}"#
        case .launchApp:   return #"{"tool":"launchApp","bundleId":"<string>"}"#
        case .openURL:     return #"{"tool":"openURL","url":"<string>"}"#
        case .getUI:       return #"{"tool":"getUI"}"#
        case .done:        return #"{"tool":"done","summary":"<string>"}"#
        }
    }
}

/// A parsed tool call. Decoded from the model's JSON output (lenient parser).
struct ToolCall: Codable, Equatable {
    let tool: String
    var x: Int? = nil, y: Int? = nil
    var x1: Int? = nil, y1: Int? = nil, x2: Int? = nil, y2: Int? = nil
    var text: String? = nil
    var name: String? = nil
    var bundleId: String? = nil
    var url: String? = nil
    var summary: String? = nil

    /// Extract the first JSON object from arbitrary model text and decode it.
    static func parse(from raw: String) -> ToolCall? {
        guard let start = raw.firstIndex(of: "{") else { return nil }
        // find matching closing brace (handles nested braces)
        var depth = 0
        var end: String.Index?
        var i = start
        while i < raw.endIndex {
            let c = raw[i]
            if c == "{" { depth += 1 }
            else if c == "}" { depth -= 1; if depth == 0 { end = i; break } }
            i = raw.index(after: i)
        }
        guard let e = end else { return nil }
        let json = String(raw[start...e])
        return try? JSONDecoder().decode(ToolCall.self, from: Data(json.utf8))
    }
}

enum AgentToolResult {
    case observation(String)   // fed back to the model
    case finished(String)      // `done` summary — ends the loop
}
