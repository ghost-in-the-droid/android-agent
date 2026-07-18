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
    var app: String? = nil

    /// Extract the first JSON object from arbitrary model text and decode it.
    static func parse(from raw: String) -> ToolCall? {
        // Extract every {...} object (small models often emit a tentative call then
        // reconsider to a better one, e.g. read → done).
        var objs: [String] = []
        var depth = 0
        var start: String.Index?
        var i = raw.startIndex
        while i < raw.endIndex {
            let c = raw[i]
            if c == "{" { if depth == 0 { start = i }; depth += 1 }
            else if c == "}" { depth -= 1; if depth == 0, let s = start { objs.append(String(raw[s...i])); start = nil } }
            i = raw.index(after: i)
        }
        let calls = objs.compactMap(interpret)
        // prefer a terminal `done`, else the first valid call
        return calls.first(where: { $0.tool == "done" }) ?? calls.first
    }

    /// Decode one object; fall back to regex for slightly-malformed JSON.
    private static func interpret(_ json: String) -> ToolCall? {
        if let c = try? JSONDecoder().decode(ToolCall.self, from: Data(json.utf8)) { return c }
        guard let tool = rx(#""tool"\s*:\s*"([a-zA-Z]+)""#, json) else { return nil }
        var c = ToolCall(tool: tool)
        c.url = rx(#""url"\s*:\s*"([^"]*)""#, json)
        c.text = rx(#""text"\s*:\s*"([^"]*)""#, json)
        c.summary = rx(#""?summary"?\s*:\s*"?([^"}]+)"#, json)
        return c
    }

    private static func rx(_ pattern: String, _ s: String) -> String? {
        guard let re = try? NSRegularExpression(pattern: pattern),
              let m = re.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)),
              let r = Range(m.range(at: 1), in: s) else { return nil }
        return String(s[r]).trimmingCharacters(in: .whitespaces)
    }
}

/// GBNF grammar constraining the model to emit exactly one tool-call JSON object
/// (llama.cpp `llama_sampler_init_grammar`, root = "root"). Guarantees the output
/// is parseable by `ToolCall.parse` regardless of model size.
let toolCallGrammar = #"""
root  ::= "{" sp "\"tool\"" sp ":" sp tool args sp "}"
tool  ::= "\"tap\"" | "\"swipe\"" | "\"type\"" | "\"pressButton\"" | "\"launchApp\"" | "\"openURL\"" | "\"getUI\"" | "\"done\""
args  ::= ( sp "," sp pair )*
pair  ::= key sp ":" sp val
key   ::= "\"" [a-zA-Z0-9]+ "\""
val   ::= str | int
str   ::= "\"" [^"\\]* "\""
int   ::= "-"? [0-9]+
sp    ::= [ \t\n]*
"""#

enum AgentToolResult {
    case observation(String)   // fed back to the model
    case finished(String)      // `done` summary — ends the loop
}
