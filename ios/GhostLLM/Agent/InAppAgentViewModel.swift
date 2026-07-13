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
    // Chat-style surface (Android-matched UI). `chat` is the bubble transcript;
    // `activityLine` is the amber "what it's doing right now" indicator.
    @Published var chat: [ChatMsg] = []
    @Published var activityLine = ""
    @Published var ready = false      // engine loaded, waiting for a prompt
    @Published var running = false

    private func say(_ role: ChatRole, _ text: String) { chat.append(ChatMsg(role: role, text: text)) }
    private(set) var modelName = "Qwen2.5 1.5B"

    /// Friendly chip label for a tool call (what the phone is doing, in plain words).
    private func toolLabel(_ c: ToolCall) -> String {
        switch c.tool {
        case "open":  return "🌐 open \(prettyHost(c.url ?? ""))"
        case "read":  return "📄 read the page"
        case "click": return "👆 tap “\(c.text ?? "")”"
        case "done":  return "✅ summarize"
        default:       return "🔧 \(c.tool)"
        }
    }
    private func prettyHost(_ url: String) -> String {
        guard let h = URLComponents(string: url)?.host else { return url }
        return h.replacingOccurrences(of: "www.", with: "")
    }

    let webView: WKWebView
    private var engine: LlamaEngine?
    private let downloader = ModelDownloadManager()
    private var loadCont: CheckedContinuation<Void, Never>?
    private let maxSteps = 8
    private var lastCallKey = ""
    // Counts every (tool+args) call this run — catches loops the consecutive check
    // misses (e.g. open→read→open→read alternating on a contentless page).
    private var callCounts: [String: Int] = [:]

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
        // Dark background so the panel doesn't flash white against the dark theme.
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 0x06/255, green: 0x0A/255, blue: 0x07/255, alpha: 1)
        webView.scrollView.backgroundColor = webView.backgroundColor
        // Desktop UA so old.reddit serves the classic layout (a.title post links)
        // instead of a mobile/search redirect.
        webView.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    }

    /// Load the model once, then idle — the chat UI waits for a typed prompt.
    func prepare() async {
        guard engine == nil else { ready = true; return }
        StatusServer.shared.start()
        do {
            let spec = ModelStore.isAvailable(ModelRegistry.qwen15) ? ModelRegistry.qwen15
                     : ModelStore.isAvailable(ModelRegistry.phase0) ? ModelRegistry.phase0
                     : ModelRegistry.qwen15
            status = "🧠 loading \(spec.displayName)…"
            let url: URL
            if ModelStore.isAvailable(spec) {
                url = try ModelStore.resolvedURL(for: spec)
            } else {
                url = try await downloader.ensure(spec) { p in
                    Task { @MainActor in self.status = "⬇️ downloading model \(Int(p * 100))%…" }
                }
            }
            engine = try LlamaEngine(modelURL: url, nCtx: 1536, nBatch: 768)
            modelName = spec.displayName
            let backend = await engine!.backend
            status = "ready · \(spec.displayName) · \(backend)"
            ready = true
        } catch {
            status = "⚠️ \(error)"
        }
    }

    /// Run the agent for a user-typed prompt, emitting chat bubbles + tool chips.
    func submit(goal: String) async {
        let goal = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !goal.isEmpty, !running else { return }
        if engine == nil { await prepare() }
        print("AGENT_GOAL \(goal)")
        say(.user, goal)
        running = true; answer = ""; lastCallKey = ""; callCounts.removeAll()
        defer { running = false; thinking = false; activityLine = "" }
        do {
            let spec = ModelRegistry.qwen15
            status = "🤖 working…"
            var context = ""
            for step in 0..<maxSteps {
                thinking = true
                activityLine = "🤔 thinking…"
                StatusServer.shared.update(phase: "thinking(step \(step))", tokS: 0, model: spec.displayName, line: status)
                guard let call = await decide(goal: goal, context: context) else {
                    say(.error, "couldn't decide a next step — stopping"); break
                }
                thinking = false
                let key = "\(call.tool)|\(argStr(call))"
                callCounts[key, default: 0] += 1
                // anti-loop: same call back-to-back, OR the identical call seen 2+
                // times total (alternating loops re-fetch the same page for nothing)
                // → nudge it toward a different tool/arg or done.
                if key == lastCallKey || callCounts[key, default: 0] >= 2 {
                    context += "\n(note: \(call.tool) already tried with no new result — use a DIFFERENT tool or argument, or emit done with your summary)"
                    push("agent", "↻ repeated \(call.tool); nudging")
                    lastCallKey = ""
                    continue
                }
                lastCallKey = key
                print("AGENT_TOOL step=\(step) \(call.tool)(\(argStr(call)))")
                say(.tool, toolLabel(call))
                activityLine = toolLabel(call)
                let obs = await execute(call)
                print("AGENT_OBS \(obs.prefix(1200))")
                push("tool", "\(call.tool) → \(obs.prefix(160))")
                StatusServer.shared.update(phase: call.tool, tokS: 0, model: spec.displayName, line: "\(call.tool): \(obs.prefix(80))")
                if call.tool == "done" {
                    answer = call.summary ?? obs; status = "✅ done"; activityLine = ""
                    say(.assistant, answer); print("AGENT_ANSWER \(answer)"); break
                }
                // keep context bounded (long prompts are slow + memory-heavy)
                context = String((context + "\n- \(call.tool)(\(argStr(call))) → \(obs.prefix(450))").suffix(1300))
            }
            if answer.isEmpty {
                // Ran out of steps without a `done`. Rather than give up, force one
                // final summary from whatever the agent actually observed — a grounded
                // answer beats "(stopped)", and the observations are the only source.
                if !context.isEmpty, let engine {
                    status = "📝 summarizing…"; thinking = true
                    var summary = ""
                    let prompt = """
                    You are Ghost, an on-device agent. Goal: \(goal)
                    Notes from what you observed while browsing:
                    \(context.suffix(1200))
                    Write the final answer to the goal in 2 sentences. Use ONLY facts, topics, and names that literally appear in the notes above; never invent model names, versions, or numbers.
                    Answer:
                    """
                    _ = try? await engine.generate(prompt: prompt, maxTokens: 160) { summary += $0 }
                    thinking = false
                    answer = summary.trimmingCharacters(in: .whitespacesAndNewlines)
                }
                if answer.isEmpty {
                    answer = "I couldn't finish that one — the page didn't give me enough to summarize."
                    status = "⏹ stopped"; say(.error, answer)
                } else {
                    status = "✅ done"; say(.assistant, answer)
                }
                print("AGENT_ANSWER \(answer)")
            }
            activityLine = ""
            StatusServer.shared.update(phase: "done", tokS: 0, model: spec.displayName, line: status)
        } catch {
            status = "⚠️ \(error)"; say(.error, "\(error)")
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
        {"tool":"done","summary":"..."} — do NOT read the same page again. In the
        summary, use ONLY facts, topics, and names that literally appear in the page
        text above; never invent model names, versions, or numbers.
        Reply with ONE JSON tool call:
        """
        let valid = ["open", "read", "click", "done"]

        // GRAMMAR-NARROWING (per ghost-multi-fleet-dev): free THOUGHT reasons + picks
        // the tool; we parse that choice, then constrain the action grammar to JUST
        // that tool + its args. The model never picks the branch (that was the loop
        // failure) — grammar only guarantees valid args.
        var thought = ""
        _ = try? await engine.generate(prompt: base + "\nReason in one short sentence, then give the tool call:", maxTokens: 80) { thought += $0 }
        print("AGENT_THOUGHT<\(thought.prefix(140))>")
        // URLs the model is ALLOWED to open = those literally present in the goal or
        // what it has already seen. Without this the constrained fill lets a small
        // model default the url to example.com (its training-prior "example URL").
        let allowedURLs = urlsIn(goal + " " + context)
        if let picked = ToolCall.parse(from: thought), valid.contains(picked.tool),
           let g = narrowGrammar(for: picked.tool, allowedURLs: allowedURLs) {
            var action = ""
            _ = try? await engine.generate(prompt: base + "\nThought: \(thought.prefix(220))\nOutput the \(picked.tool) tool call:", maxTokens: 96, grammar: g) { action += $0 }
            print("AGENT_ACTION<\(action.prefix(120))>")
            if let c = ToolCall.parse(from: action), c.tool == picked.tool { return c }
            return picked   // grammar hiccup → use the thought's own parse
        }

        // fallback: plain instruct+parse
        for attempt in 0..<2 {
            var out = ""
            _ = try? await engine.generate(prompt: base + (attempt == 0 ? "" : "\nOutput ONLY one JSON tool call.\nJSON:"), maxTokens: 80) { out += $0 }
            if let call = ToolCall.parse(from: out), valid.contains(call.tool) { return call }
        }
        return nil
    }

    /// Grammar constrained to exactly ONE tool (+ its args). The tool is fixed, so a
    /// 2B can't mis-commit the branch; only the arg values are model-chosen.
    private func narrowGrammar(for tool: String, allowedURLs: [String] = []) -> String? {
        // If we know which URLs are legitimate (present in goal/context), pin the url
        // rule to an alternation of those exact literals so the model can't fabricate
        // one (e.g. example.com). Fall back to a free url charclass if we know none.
        let urlRule: String
        if tool == "open", !allowedURLs.isEmpty {
            urlRule = "url ::= " + allowedURLs.map { "\"\($0)\"" }.joined(separator: " | ")
        } else {
            urlRule = #"url ::= [a-zA-Z0-9:/._?=&%~#@+-]+"#
        }
        let common = [#"q   ::= ["]"#, urlRule,
                      #"txt ::= [a-zA-Z0-9 .,!?;:'()/_-]+"#, ""]
        let root: String
        switch tool {
        case "open":  root = #"root ::= "{" q "tool" q ":" q "open" q "," q "url" q ":" q url q "}""#
        case "read":  root = #"root ::= "{" q "tool" q ":" q "read" q "}""#
        case "click": root = #"root ::= "{" q "tool" q ":" q "click" q "," q "text" q ":" q txt q "}""#
        case "done":  root = #"root ::= "{" q "tool" q ":" q "done" q "," q "summary" q ":" q txt q "}""#
        default: return nil
        }
        return ([root] + common).joined(separator: "\n")
    }

    /// Extract distinct http(s) URLs appearing in `text` (trailing punctuation
    /// stripped). Used to whitelist which pages the agent may open.
    private func urlsIn(_ text: String) -> [String] {
        guard let re = try? NSRegularExpression(pattern: #"https?://[^\s"'|}\\]+"#) else { return [] }
        var seen: [String] = []
        for m in re.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let r = Range(m.range, in: text) else { continue }
            var u = String(text[r])
            while let last = u.last, ".,;:)]".contains(last) { u.removeLast() }
            if !u.isEmpty, !seen.contains(u) { seen.append(u) }
        }
        return seen
    }

    // MARK: - Execute a tool against the WebView

    private func execute(_ c: ToolCall) async -> String {
        switch c.tool {
        case "open":
            guard let s = c.url, let u = normalizedURL(s) else { return "invalid url" }
            await load(u)
            return "opened \(currentURL). Page text: \(await readText(1600))"
        case "read":
            return "Page text: \(await readText(1600))"
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
