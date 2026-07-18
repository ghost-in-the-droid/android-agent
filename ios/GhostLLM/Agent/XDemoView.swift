import SwiftUI

/// Test/demo harness for the real-app agent (GHOST_XDEMO=1): open X → read →
/// summarize → re-open Ghost. Runs on CPU + keep-alive (survives while X is
/// foreground). Writes the trajectory to Documents/xagent.log (pull via devicectl)
/// and shows it on screen once Ghost re-opens.
struct XDemoView: View {
    @State private var lines: [ChatMsg] = []
    private static let logURL = FileManager.default
        .urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("xagent.log")

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("👻 Ghost · real-app agent").font(.headline).foregroundStyle(GhostTheme.accent)
            ForEach(lines) { m in
                Text(m.text)
                    .font(.system(size: 14, design: m.role == .tool ? .monospaced : .default))
                    .foregroundStyle(m.role == .assistant ? GhostTheme.text1 : GhostTheme.text3)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding()
        .background(GhostTheme.bgBase.ignoresSafeArea())
        .task { await run() }
    }

    private func fileLog(_ s: String) {
        let line = s + "\n"
        if let h = try? FileHandle(forWritingTo: Self.logURL) { h.seekToEndOfFile(); h.write(Data(line.utf8)); try? h.close() }
        else { try? line.write(to: Self.logURL, atomically: true, encoding: .utf8) }
    }

    private func run() async {
        try? "".write(to: Self.logURL, atomically: true, encoding: .utf8)
        let goal = ProcessInfo.processInfo.environment["GHOST_GOAL"] ?? "open X and summarize the posts in my feed"
        fileLog("XAGENT_GOAL \(goal)")
        // Keep-alive so Ghost keeps running the read/re-open code while X is
        // foreground (otherwise it suspends and never wakes itself). The LLM still
        // runs later on Metal, in the foreground, after we re-open Ghost.
        KeepAlive.shared.start()
        guard ModelStore.isAvailable(ModelRegistry.qwen15),
              let url = try? ModelStore.resolvedURL(for: ModelRegistry.qwen15),
              let engine = try? LlamaEngine(modelURL: url, nCtx: 2048, nBatch: 512) else {  // Metal
            fileLog("XAGENT_ENGINE_FAIL"); return
        }
        fileLog("XAGENT_ENGINE_READY(metal)")
        let wda = HTTPWDAClient(base: URL(string: "http://127.0.0.1:8100")!)
        let agent = RealAppAgent(engine: engine, wda: wda)
        let summary = await agent.run(goal: goal) { role, text in
            fileLog("XAGENT_\(role == .tool ? "TOOL" : role == .assistant ? "ANSWER" : "MSG") \(text)")
            Task { @MainActor in lines.append(ChatMsg(role: role, text: text)) }
        }
        fileLog("XAGENT_DONE \(summary)")
        KeepAlive.shared.stop()
    }
}
