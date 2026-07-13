import Foundation

/// MVP real-app agent: the on-device LLM drives a REAL app (not a web view).
/// Flow (all on-device): open the app → read its screen → summarize → re-open
/// Ghost to show the answer. Runs on CPU + keep-alive so it survives while the
/// target app is foreground (see [[ghost-ios-background-drive]]). ~2 LLM tool
/// calls (open_app, read) then a summary.
@MainActor
final class RealAppAgent {
    private let engine: LlamaEngine
    private let wda: WDAClient
    private let ghostBundle = "com.ghostinthedroid.ghostllm"

    /// Friendly app name → bundle id. The 1.5B names the app; we resolve the id.
    private let apps: [String: String] = [
        "x": "com.atebits.Tweetie2", "twitter": "com.atebits.Tweetie2",
        "reddit": "com.reddit.Reddit", "safari": "com.apple.mobilesafari",
    ]

    init(engine: LlamaEngine, wda: WDAClient) { self.engine = engine; self.wda = wda }

    struct Progress { let line: (String) -> Void }

    /// Returns the final summary. `emit` streams human-readable progress for the UI.
    /// The tool steps (open, read) are executed directly; the on-device LLM's job is
    /// the summary — and we keep it as the engine's FIRST generate, which is reliable
    /// (repeated generate() calls on one context degrade to a single token on CPU).
    func run(goal: String, emit: @escaping @Sendable (ChatRole, String) -> Void) async -> String {
        func log(_ s: String) { print("XAGENT_\(s)") }
        do { _ = try await wda.createSession() } catch { log("WDA_FAIL \(error)") }

        // ── Step 1: open the app named in the goal ──────────────────────────
        let name = appName(in: goal)
        let bundle = apps[name] ?? "com.atebits.Tweetie2"
        emit(.tool, "🚀 open \(name.uppercased())")
        log("OPEN \(name) -> \(bundle)")
        try? await wda.launchApp(bundleId: bundle)
        try? await Task.sleep(nanoseconds: 3_000_000_000)  // let the feed load

        // ── Step 2: read the screen (WDA only — no LLM, works backgrounded) ──
        emit(.tool, "📄 read the feed")
        let src = (try? await wda.source()) ?? ""
        let pageText = Self.extractText(from: src)
        log("READ srcLen=\(src.count) textLen=\(pageText.count)")

        // ── Step 3: come back to Ghost, THEN summarize on Metal (foreground) ─
        // The LLM only runs in the foreground: Metal inference is killed in the
        // background, and CPU inference in this llama.cpp build is unreliable. So we
        // re-open Ghost first, then summarize with the GPU where it actually works.
        try? await wda.launchApp(bundleId: ghostBundle)
        try? await Task.sleep(nanoseconds: 1_200_000_000)  // let Ghost take foreground
        emit(.tool, "✅ summarize (on-device)")
        let summary = await summarize(goal: goal, app: name.uppercased(), text: pageText)
        log("SUMMARY \(summary)")
        emit(.assistant, summary)
        return summary
    }

    /// Which known app the goal refers to (defaults to X).
    private func appName(in goal: String) -> String {
        let g = goal.lowercased()
        return apps.keys.first(where: { g.contains($0) }) ?? "x"
    }

    private func summarize(goal: String, app: String, text: String) async -> String {
        guard !text.isEmpty else { return "I opened \(app) but couldn't read anything from the screen." }
        let prompt = """
        Here are posts from the \(app) feed:
        \(text.prefix(1200))

        In two sentences, summarize what people in this feed are posting about. Use \
        only what appears above; never invent names or numbers.
        """
        var out = ""
        _ = try? await engine.generate(prompt: prompt, maxTokens: 120) { out += $0 }
        // The 1.5B tends to ramble; keep the first 2 sentences as the answer.
        return Self.firstSentences(out.trimmingCharacters(in: .whitespacesAndNewlines), 2)
    }

    /// First `n` sentences of `s` (splits on . ! ? followed by space/newline/end).
    private static func firstSentences(_ s: String, _ n: Int) -> String {
        var count = 0, end = s.startIndex
        var i = s.startIndex
        while i < s.endIndex {
            let c = s[i]
            let next = s.index(after: i)
            if ".!?".contains(c), (next == s.endIndex || s[next] == " " || s[next] == "\n") {
                count += 1; end = next
                if count >= n { return String(s[s.startIndex..<next]).trimmingCharacters(in: .whitespacesAndNewlines) }
            }
            i = next
        }
        return s
    }

    // MARK: - Parse a WDA accessibility XML dump into readable feed text

    /// Pull human-readable strings (label/value/name of text-ish elements) out of
    /// WDA's XML source. X's tree is huge + noisy — keep meaningful lines only.
    static func extractText(from xml: String) -> String {
        var seen = Set<String>()
        var out: [String] = []
        for attr in ["label", "value", "name"] {
            guard let re = try? NSRegularExpression(pattern: "\(attr)=\"([^\"]{4,300})\"") else { continue }
            for m in re.matches(in: xml, range: NSRange(xml.startIndex..., in: xml)) {
                guard let r = Range(m.range(at: 1), in: xml) else { continue }
                let s = String(xml[r]).trimmingCharacters(in: .whitespacesAndNewlines)
                // drop UI-chrome junk and pure numbers/short tokens
                if s.count < 8 || Double(s) != nil { continue }
                if ["Home", "Search", "Notifications", "Messages", "Profile", "Tweet", "Post"].contains(s) { continue }
                if seen.insert(s).inserted { out.append(s) }
                if out.count >= 40 { break }
            }
        }
        return out.joined(separator: "\n")
    }
}
