import Foundation

/// Self-running demo: load Gemma → fetch r/LocalLLaMA thread → summarize on-device,
/// streaming. Zero external UI-driving — everything is app-owned so the whole run
/// can be captured in one continuous take (and rendered as a per-device tile).
@MainActor
final class DemoViewModel: ObservableObject {
    @Published var narration = "👻 Waking up Ghost…"
    @Published var subreddit = "r/LocalLLaMA"
    @Published var postTitle = ""
    @Published var summary = ""
    @Published var stats = ""
    @Published var backend = ""
    @Published var sourceLabel = ""
    @Published var done = false

    private var engine: LlamaEngine?
    private let downloader = ModelDownloadManager()

    private var modelName = ""

    /// Set the narration line and push a status snapshot for fleet tiles (:8088).
    private func narrate(_ line: String, phase: String, tokS: Double = 0) {
        narration = line
        StatusServer.shared.update(phase: phase, tokS: tokS, model: modelName, line: line)
    }

    func run() async {
        StatusServer.shared.start()   // best-effort status endpoint for fleet tiles
        do {
            // 1) Load the best available on-device model (Gemma if present;
            //    else the bundled model; download Gemma only if nothing is local).
            let spec = ModelStore.isAvailable(ModelRegistry.gemma4E2B) ? ModelRegistry.gemma4E2B
                     : ModelStore.isAvailable(ModelRegistry.phase0) ? ModelRegistry.phase0
                     : ModelRegistry.gemma4E2B
            modelName = spec.displayName
            narrate("🧠 Loading \(spec.displayName) on-device…", phase: "loading")
            let url: URL
            if ModelStore.isAvailable(spec) {
                url = try ModelStore.resolvedURL(for: spec)
            } else {
                url = try await downloader.ensure(spec) { p in
                    Task { @MainActor in self.narration = "⬇️ Downloading Gemma (\(Int(p * 100))%)…" }
                }
            }
            let engine = try LlamaEngine(modelURL: url)
            self.engine = engine
            backend = await engine.backend

            // 2) Fetch the thread (the app itself — no UI driving)
            narrate("🌐 Opening r/LocalLLaMA…", phase: "fetching")
            let thread = await RedditFetcher.topThread()
            subreddit = thread.subreddit
            postTitle = thread.title
            sourceLabel = thread.live ? "live" : "cached"
            narrate("📖 Reading the top post (\(thread.comments.count) comments)…", phase: "reading")

            // 3) Summarize on-device, streaming (short prompt; digest passed programmatically)
            narrate("✍️ Summarizing 100% on-device — offline-capable…", phase: "summarizing")
            let digest = thread.comments.prefix(8).joined(separator: "\n- ")
            let prompt = """
            Summarize the top comments on this r/LocalLLaMA post in 3 sentences — \
            the main points and the overall sentiment. Post title: "\(thread.title)".
            Comments:
            - \(digest)
            """
            let info = try await engine.generate(prompt: prompt, maxTokens: 170) { piece in
                Task { @MainActor in self.summary += piece }
            }
            stats = String(format: "%d→%d tok · %.1f tok/s · %@",
                           info.promptTokens, info.generatedTokens, info.tokensPerSecond, info.backend)
            narrate("✅ Summarized on-device — no cloud, no network needed",
                    phase: "done", tokS: info.tokensPerSecond)
            done = true
        } catch {
            narrate("⚠️ \(error)", phase: "error")
        }
    }
}
