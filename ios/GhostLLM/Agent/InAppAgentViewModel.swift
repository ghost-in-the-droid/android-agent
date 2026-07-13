import Foundation
import WebKit

/// A real on-device agent: Gemma emits tool calls that drive an embedded WebView,
/// autonomously browsing to accomplish a goal. Every decision is the on-device LLM;
/// the app just executes the tool it chose. Fully on-device, no OS-level driving.
@MainActor
final class InAppAgentViewModel: NSObject, ObservableObject, WKNavigationDelegate {
    @Published var status = "waking up…"
    @Published var transcript: [String] = []
    @Published var answer = ""
    @Published var thinking = false
    @Published var currentURL = ""

    let webView: WKWebView
    private var engine: LlamaEngine?
    private let downloader = ModelDownloadManager()
    private var loadCont: CheckedContinuation<Void, Never>?
    private let maxSteps = 8
    private var lastCallKey = ""

    /// GBNF that hard-restricts output to EXACTLY one of the 4 tool shapes with the
    /// right keys — a 2B model literally cannot emit invalid JSON or a bad tool name
    /// (per ghost-multi-fleet-dev: grammar wins, not close, for on-device FC).
    // NOTE: this llama.cpp build's GBNF parser mishandles \" inside string literals
    // (crashes with 'empty grammar stack'). So we NEVER use \" — the literal quote
    // comes from a char-class rule q ::= ["], and all other literals are quote-free.
    // Hard-restricts output to exactly one valid tool call — a 2B model literally
    // cannot emit invalid JSON or a bad tool name. Quote via q ::= ["] (avoids \").
    private let webToolGrammar = [
        #"root  ::= open | read | click | done"#,
        #"open  ::= "{" q "tool" q ":" q "open" q "," q "url" q ":" q url q "}""#,
        #"read  ::= "{" q "tool" q ":" q "read" q "}""#,
        #"click ::= "{" q "tool" q ":" q "click" q "," q "text" q ":" q txt q "}""#,
        #"done  ::= "{" q "tool" q ":" q "done" q "," q "summary" q ":" q txt q "}""#,
        #"q     ::= ["]"#,
        #"url   ::= [a-zA-Z0-9:/._?=&%~#@+-]+"#,
        #"txt   ::= [a-zA-Z0-9 .,!?;:'()/_-]+"#, "",
    ].joined(separator: "\n")

    override init() {
        let cfg = WKWebViewConfiguration()
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        webView = WKWebView(frame: .zero, configuration: cfg)
        super.init()
        webView.navigationDelegate = self
        // Desktop UA so old.reddit serves the classic layout (a.title post links)
        // instead of a mobile/search redirect.
        webView.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    }

    func run(goal: String) async {
        StatusServer.shared.start()
        do {
            // Qwen2.5-1.5B: small enough to run beside a WKWebView (Gemma+WebKit OOMs)
            // and stronger at tool-calling. Prefer it; fall back to the bundled model
            // (e.g. on the simulator, which lacks Qwen); else download Qwen (~1.1 GB).
            let spec = ModelStore.isAvailable(ModelRegistry.qwen15) ? ModelRegistry.qwen15
                     : ModelStore.isAvailable(ModelRegistry.phase0) ? ModelRegistry.phase0
                     : ModelRegistry.qwen15
            status = "🧠 loading \(spec.displayName)…"
            let url: URL
            if ModelStore.isAvailable(spec) {
                url = try ModelStore.resolvedURL(for: spec)
            } else {
                url = try await downloader.ensure(spec) { p in
                    Task { @MainActor in self.status = "⬇️ downloading agent model \(Int(p * 100))%…" }
                }
            }
            // nBatch must be >= the (long) agent prompt — generate() fills one batch.
            // Smaller nCtx trims the KV cache to leave room for WebKit's rendered page.
            engine = try LlamaEngine(modelURL: url, nCtx: 1536, nBatch: 768)
            let backend = await engine!.backend
            push("agent", "goal: \(goal)")
            status = "🤖 agent running · \(spec.displayName) · \(backend)"

            var context = ""
            for step in 0..<maxSteps {
                thinking = true
                StatusServer.shared.update(phase: "thinking(step \(step))", tokS: 0, model: spec.displayName, line: status)
                guard let call = await decide(goal: goal, context: context) else {
                    push("agent", "⚠️ couldn't parse a tool call; stopping"); break
                }
                thinking = false
                let key = "\(call.tool)|\(argStr(call))"
                if key == lastCallKey {
                    // anti-loop: same call twice → nudge it to do something different
                    context += "\n(note: \(call.tool) repeated with no new result — try a DIFFERENT tool or argument)"
                    push("agent", "↻ repeated \(call.tool); nudging")
                    lastCallKey = ""
                    continue
                }
                lastCallKey = key
                print("AGENT_TOOL step=\(step) \(call.tool)(\(argStr(call)))")
                let obs = await execute(call)
                print("AGENT_OBS \(obs.prefix(140))")
                push("tool", "\(call.tool) → \(obs.prefix(160))")
                StatusServer.shared.update(phase: call.tool, tokS: 0, model: spec.displayName, line: "\(call.tool): \(obs.prefix(80))")
                if call.tool == "done" { answer = call.summary ?? obs; status = "✅ done"; print("AGENT_ANSWER \(answer)"); break }
                // keep context bounded (long prompts are slow + memory-heavy)
                context = String((context + "\n- \(call.tool)(\(argStr(call))) → \(obs.prefix(450))").suffix(1300))
            }
            if answer.isEmpty { answer = "(no final answer — agent stopped)" ; status = "⏹ stopped" }
            StatusServer.shared.update(phase: "done", tokS: 0, model: spec.displayName, line: status)
        } catch {
            status = "⚠️ \(error)"
        }
    }

    // MARK: - LLM decides the next tool

    private func decide(goal: String, context: String) async -> ToolCall? {
        guard let engine else { return nil }
        let base = """
        You are a web-browsing agent on a phone. Reply with EXACTLY ONE JSON tool call, nothing else.
        Tools (pick one):
        {"tool":"open","url":"https://..."}      open a web page
        {"tool":"read"}                            read the current page text
        {"tool":"click","text":"link text"}      click a link containing that text
        {"tool":"done","summary":"..."}          finish with your answer

        Examples:
        {"tool":"open","url":"https://old.reddit.com/r/LocalLLaMA/"}
        {"tool":"done","summary":"The top post is about ..."}

        GOAL: \(goal)
        Progress so far:\(context.isEmpty ? " nothing yet — open a page first." : context)

        IMPORTANT: As soon as the page text above contains what the goal needs, use
        {"tool":"done","summary":"..."} — do NOT read the same page again.
        Reply with ONE JSON tool call:
        """
        // Single-phase instruct+parse — empirically the best for Qwen-1.5B here.
        // Its free generation is self-consistent (reasons AND acts together: leads
        // with `open`, then `done`); the robust parser extracts the JSON. A two-phase
        // thought→grammar-action split loops (the constrained action head ignores the
        // thought and defaults to `read`). Grammar stays available engine-wide.
        let valid = ["open", "read", "click", "done"]
        for attempt in 0..<3 {
            var out = ""
            let p = attempt == 0 ? base : base + "\nOutput ONLY one JSON object like {\"tool\":\"read\"} — no prose.\nJSON:"
            _ = try? await engine.generate(prompt: p, maxTokens: 80) { out += $0 }
            print("AGENT_RAW[\(attempt)]<\(out.prefix(140))>")
            if let call = ToolCall.parse(from: out), valid.contains(call.tool) { return call }
        }
        return nil
    }

    // MARK: - Execute a tool against the WebView

    private func execute(_ c: ToolCall) async -> String {
        switch c.tool {
        case "open":
            guard let s = c.url, let u = normalizedURL(s) else { return "invalid url" }
            await load(u)
            return "opened \(currentURL). Page text: \(await readText(700))"
        case "read":
            return "Page text: \(await readText(900))"
        case "click":
            let ok = await clickLink(containing: c.text ?? "")
            if ok { return "clicked '\(c.text ?? "")'. Now at \(currentURL). Page text: \(await readText(700))" }
            return "no link matching '\(c.text ?? "")' found. Page text: \(await readText(500))"
        case "done":
            return c.summary ?? "done"
        default:
            return "unknown tool \(c.tool)"
        }
    }

    private func load(_ url: URL) async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            loadCont = cont
            webView.load(URLRequest(url: url))
        }
    }

    private func readText(_ limit: Int) async -> String {
        // Prefer meaningful content (titles/headings/paragraphs) over nav chrome.
        let js = """
        (function(){
          var titles = Array.from(document.querySelectorAll('a.title, [data-testid=post-title], shreddit-post'))
             .map(function(e){return (e.innerText||'').trim();}).filter(function(x){return x.length>10;});
          if (titles.length) return 'Reddit posts: ' + titles.slice(0,15).join(' | ');
          var els = Array.from(document.querySelectorAll('h1, h2, h3, p'))
             .map(function(e){return (e.innerText||'').trim();}).filter(function(x){return x.length>25;});
          if (els.length) return els.slice(0,20).join(' | ');
          return document.body ? document.body.innerText : '';
        })()
        """
        let raw = (try? await webView.evaluateJavaScript(js)) as? String ?? ""
        let clean = raw.replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "  ", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return String(clean.prefix(limit))
    }

    private func clickLink(containing text: String) async -> Bool {
        let t = text.replacingOccurrences(of: "'", with: "\\'").lowercased()
        let js = """
        (function(){
          var as = Array.from(document.querySelectorAll('a'));
          var el = as.find(a => (a.innerText||'').toLowerCase().includes('\(t)'));
          if (el && el.href) { window.location.href = el.href; return true; }
          return false;
        })()
        """
        let clicked = (try? await webView.evaluateJavaScript(js)) as? Bool ?? false
        if clicked { await waitForLoad() }
        return clicked
    }

    private func waitForLoad() async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in loadCont = cont }
    }

    // MARK: - helpers

    private func normalizedURL(_ s: String) -> URL? {
        var str = s.trimmingCharacters(in: .whitespaces)
        if !str.lowercased().hasPrefix("http") { str = "https://" + str }
        return URL(string: str)
    }
    private func argStr(_ c: ToolCall) -> String { c.url ?? c.text ?? c.summary ?? "" }
    private func push(_ who: String, _ text: String) { transcript.append("\(who): \(text)") }

    // WKNavigationDelegate
    nonisolated func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        Task { @MainActor in
            currentURL = webView.url?.absoluteString ?? ""
            loadCont?.resume(); loadCont = nil
        }
    }
    nonisolated func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        Task { @MainActor in loadCont?.resume(); loadCont = nil }
    }
    nonisolated func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        Task { @MainActor in loadCont?.resume(); loadCont = nil }
    }
}
