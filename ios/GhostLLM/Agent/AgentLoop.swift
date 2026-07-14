import Foundation

/// The on-device agent loop: the LLM emits a tool call, we execute it against WDA,
/// feed the observation back, and repeat until `done` or `maxSteps`. The `decider`
/// is pluggable so the loop is testable with a scripted decider (no model/phone).
actor AgentLoop {
    private let engine: LlamaEngine?
    private let wda: WDAClient
    private let useGrammar: Bool
    private(set) var transcript: [String] = []

    init(engine: LlamaEngine?, wda: WDAClient, useGrammar: Bool = false) {
        self.engine = engine
        self.wda = wda
        self.useGrammar = useGrammar
    }

    /// `decider` maps the running context to the next ToolCall. Defaults to the LLM.
    func run(goal: String, maxSteps: Int = 8,
             decider: (@Sendable (String) async -> ToolCall?)? = nil) async -> String {
        transcript.removeAll()
        _ = try? await wda.createSession()
        var context = "GOAL: \(goal)\n"

        for step in 0..<maxSteps {
            let call = decider != nil ? await decider!(context) : await llmDecide(context)
            guard let call else { transcript.append("step \(step): no valid tool call"); break }
            transcript.append("step \(step): \(call.tool)")
            switch await execute(call) {
            case .finished(let s):
                transcript.append("DONE: \(s)")
                return s
            case .observation(let obs):
                context += "\n> \(call.tool): \(obs)"
            }
        }
        return "max steps reached"
    }

    private func execute(_ c: ToolCall) async -> AgentToolResult {
        do {
            switch AgentTool(rawValue: c.tool) {
            case .tap:         try await wda.tap(x: c.x ?? 0, y: c.y ?? 0); return .observation("tapped \(c.x ?? 0),\(c.y ?? 0)")
            case .swipe:       try await wda.swipe(x1: c.x1 ?? 0, y1: c.y1 ?? 0, x2: c.x2 ?? 0, y2: c.y2 ?? 0); return .observation("swiped")
            case .type:        try await wda.typeText(c.text ?? ""); return .observation("typed")
            case .pressButton: try await wda.pressButton(c.name ?? "home"); return .observation("pressed \(c.name ?? "home")")
            case .launchApp:   try await wda.launchApp(bundleId: c.bundleId ?? ""); return .observation("launched \(c.bundleId ?? "")")
            case .openURL:     try await wda.openURL(c.url ?? ""); return .observation("opened \(c.url ?? "")")
            case .getUI:       let s = try await wda.source(); return .observation("ui: \(s.prefix(400))")
            case .done:        return .finished(c.summary ?? "")
            case .none:        return .observation("unknown tool: \(c.tool)")
            }
        } catch {
            return .observation("error: \(error)")
        }
    }

    /// Ask the on-device LLM for the next tool call (JSON). Grammar-constrained
    /// decoding is the M2 hardening step; for now we instruct + leniently parse.
    private func llmDecide(_ context: String) async -> ToolCall? {
        guard let engine else { return nil }
        let tools = AgentTool.allCases.map { "- " + $0.schemaLine }.joined(separator: "\n")
        let prompt = """
        You control an iPhone. Respond with EXACTLY ONE JSON tool call and nothing else.
        Available tools:
        \(tools)

        \(context)

        Next tool call:
        """
        var out = ""
        // Instruct-and-parse. Grammar-constrained decoding (toolCallGrammar) is
        // available but OFF by default: the GBNF needs validation against llama.cpp
        // on-device (a malformed grammar throws an uncatchable C++ exception), and
        // Gemma-4 E2B follows the JSON schema well without it. Enable once verified.
        _ = try? await engine.generate(prompt: prompt, maxTokens: 96, grammar: useGrammar ? toolCallGrammar : nil) { out += $0 }
        return ToolCall.parse(from: out)
    }
}
