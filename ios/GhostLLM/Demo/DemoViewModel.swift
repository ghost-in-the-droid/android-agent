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

    func run() async {
        do {
            // 1) Load the best available on-device model (Gemma if present;
            //    else the bundled model; download Gemma only if nothing is local).
            let spec = ModelStore.isAvailable(ModelRegistry.gemma4E2B) ? ModelRegistry.gemma4E2B
                     : ModelStore.isAvailable(ModelRegistry.phase0) ? ModelRegistry.phase0
                     : ModelRegistry.gemma4E2B
            narration = "🧠 Loading \(spec.displayName) on-device…"
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
            narration = "🌐 Opening r/LocalLLaMA…"
            let thread = await RedditFetcher.topThread()
            subreddit = thread.subreddit
            postTitle = thread.title
            sourceLabel = thread.live ? "live" : "cached"
            narration = "📖 Reading the top post (\(thread.comments.count) comments)…"

            // 3) Summarize on-device, streaming (short prompt; digest passed programmatically)
            narration = "✍️ Summarizing 100% on-device — offline-capable…"
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
            narration = "✅ Summarized on-device — no cloud, no network needed"
            done = true
        } catch {
            narration = "⚠️ \(error)"
        }
    }
}
