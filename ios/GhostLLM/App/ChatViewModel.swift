import Foundation
import SwiftUI

/// Tiny step counter for the scripted agent self-test (safe across the loop's
/// @Sendable decider closure).
actor Counter {
    private var n = 0
    func next() -> Int { defer { n += 1 }; return n }
}

struct ChatMessage: Identifiable, Equatable {
    enum Role { case user, assistant, system }
    let id = UUID()
    let role: Role
    var text: String
}

/// Drives on-device chat: model load/download/switch + full streaming turns.
/// One engine instance per loaded model; KV cleared each turn (full history
/// re-fed — simple + correct for MVP-length chats).
@MainActor
final class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var status: String = "loading model…"
    @Published var ready = false
    @Published var generating = false
    @Published var currentModel: ModelSpec = ModelRegistry.defaultModel
    @Published var downloadProgress: Double? = nil   // non-nil while downloading

    let models = ModelRegistry.all
    private var engine: LlamaEngine?
    private let downloader = ModelDownloadManager()
    private let systemPrompt = "You are Ghost, a concise helpful assistant running entirely on this iPhone."
    private let maxTokens = 256

    func loadDefaultModel() async { await load(currentModel) }

    func switchModel(to spec: ModelSpec) async {
        guard spec.id != currentModel.id || !ready else { return }
        await load(spec)
    }

    private func load(_ spec: ModelSpec) async {
        ready = false
        engine = nil
        currentModel = spec
        do {
            let url: URL
            if ModelStore.isAvailable(spec) {
                url = try ModelStore.resolvedURL(for: spec)
            } else {
                status = "downloading \(spec.displayName) (\(spec.sizeLabel))…"
                downloadProgress = 0
                url = try await downloader.ensure(spec) { [weak self] p in
                    Task { @MainActor in self?.downloadProgress = p }
                }
                downloadProgress = nil
            }
            status = "loading \(spec.displayName)…"
            let engine = try LlamaEngine(modelURL: url)
            self.engine = engine
            let backend = await engine.backend
            status = "ready · \(spec.displayName) · \(backend)"
            ready = true
        } catch {
            downloadProgress = nil
            status = "error: \(error)"
        }
    }

    /// Headless proof of the download-on-first-run path: download a model over
    /// the network into Documents, then load it. Uses the small model URL so the
    /// mechanism is validated fast (the production Gemma path is identical).
    func runDownloadSelfTest() async {
        let spec = ModelSpec(
            id: "dl-test", displayName: "download self-test",
            filename: "dltest-\(ModelRegistry.phase0.filename)",
            url: ModelRegistry.phase0.url, sizeBytes: ModelRegistry.phase0.sizeBytes, bundled: false
        )
        try? FileManager.default.removeItem(at: ModelStore.documentsURL(for: spec))
        var lastDecile = -1
        do {
            let url = try await downloader.ensure(spec) { p in
                let d = Int(p * 10)
                if d != lastDecile { lastDecile = d; print("DL_TEST_PROGRESS \(d * 10)%") }
            }
            let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int64) ?? -1
            let inDocs = url.path.contains("/Documents/models/")
            let engine = try LlamaEngine(modelURL: url)
            let backend = await engine.backend
            print("DL_TEST_RESULT ok file=\(url.lastPathComponent) size=\(size ?? -1) in_documents=\(inDocs) loaded_backend=\(backend)")
        } catch {
            print("DL_TEST_ERROR \(error)")
        }
    }

    /// Phone-free proof of the agent loop: a scripted decider drives MockWDAClient
    /// (getUI → tap → done); asserts the loop issues the right WDA calls in order
    /// and terminates. The real loop swaps the mock for HTTPWDAClient + the LLM.
    func runAgentSelfTest() async {
        let mock = MockWDAClient()
        let loop = AgentLoop(engine: nil, wda: mock)
        let script: [ToolCall] = [
            ToolCall(tool: "getUI"),
            ToolCall(tool: "tap", x: 100, y: 200),
            ToolCall(tool: "done", summary: "tapped Settings"),
        ]
        let counter = Counter()
        let result = await loop.run(goal: "Open Settings", maxSteps: 6) { _ in
            let i = await counter.next()
            return i < script.count ? script[i] : nil
        }
        let calls = await mock.calls
        let transcript = await loop.transcript
        let ok = calls == ["createSession", "source", "tap(100,200)"] && result == "tapped Settings"
        print("AGENT_TEST_RESULT ok=\(ok) result=<\(result)> calls=\(calls) transcript=\(transcript)")
    }

    func send(_ text: String) async {
        let prompt = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty, !generating, let engine else { return }
        generating = true
        defer { generating = false }

        messages.append(ChatMessage(role: .user, text: prompt))
        let assistantIndex = messages.count
        messages.append(ChatMessage(role: .assistant, text: ""))

        var turns: [ChatTurn] = [ChatTurn(role: "system", content: systemPrompt)]
        for m in messages where m.role != .assistant || !m.text.isEmpty {
            let role = m.role == .user ? "user" : (m.role == .system ? "system" : "assistant")
            turns.append(ChatTurn(role: role, content: m.text))
        }

        await engine.resetContext()
        let formatted = await engine.formatChat(turns)
        do {
            let info = try await engine.generate(prompt: formatted, maxTokens: maxTokens) { [weak self] piece in
                Task { @MainActor in
                    guard let self, self.messages.indices.contains(assistantIndex) else { return }
                    self.messages[assistantIndex].text += piece
                }
            }
            status = "ready · \(info.summary)"
            print("M1_RESULT reply=<\(messages[assistantIndex].text)> \(info.summary)")
        } catch {
            messages[assistantIndex].text = "[error: \(error)]"
            print("M1_ERROR \(error)")
        }
    }
}
