import SwiftUI

/// Validates the "drive a real app from the background" architecture end-to-end,
/// gated on GHOST_BGTEST=1. Logs each stage (prefix BGTEST_) so a --console run can
/// confirm: keep-alive holds, WDA is reachable on-device (127.0.0.1:8100), launching
/// X backgrounds us, and CPU inference still runs while backgrounded. If the app were
/// suspended, the post-background log lines never appear.
struct BGDriveTestView: View {
    @State private var lines: [String] = ["starting…"]
    var body: some View {
        ScrollView { VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, l in
                Text(l).font(.system(size: 12, design: .monospaced)).foregroundStyle(.green)
            }
        }.padding() }
        .background(Color.black.ignoresSafeArea())
        .task { await run() }
    }

    private static let logURL = FileManager.default
        .urls(for: .documentDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("bgtest.log")

    private func log(_ s: String) {
        print("BGTEST_\(s)")
        Task { @MainActor in lines.append(s) }
        // Append to a file in Documents — survives suspension, pulled via devicectl
        // afterward. This is the ground-truth channel (no networking, no permission).
        let line = "BGTEST_\(s)\n"
        if let data = line.data(using: .utf8) {
            if let h = try? FileHandle(forWritingTo: Self.logURL) {
                h.seekToEndOfFile(); h.write(data); try? h.close()
            } else {
                try? line.write(to: Self.logURL, atomically: true, encoding: .utf8)
            }
        }
    }

    private func resetLog() { try? "".write(to: Self.logURL, atomically: true, encoding: .utf8) }

    private func run() async {
        resetLog()
        let t0 = Date()
        func elapsed() -> String { String(format: "%.0fs", Date().timeIntervalSince(t0)) }

        // 1) keep-alive
        KeepAlive.shared.start()
        log("KEEPALIVE_STARTED @\(elapsed())")

        // 2) load a CPU engine (Metal is killed in background)
        do {
            let spec = ModelRegistry.qwen15
            guard ModelStore.isAvailable(spec) else { log("MODEL_MISSING"); return }
            let url = try ModelStore.resolvedURL(for: spec)
            let engine = try LlamaEngine(modelURL: url, nCtx: 512, nBatch: 256, cpuOnly: true)
            log("ENGINE_CPU_READY @\(elapsed())")

            // 3) reach WDA on-device and launch X (backgrounds us)
            let wda = HTTPWDAClient(base: URL(string: "http://127.0.0.1:8100")!)
            do {
                _ = try await wda.createSession()
                log("WDA_SESSION_OK @\(elapsed())")
                try await wda.launchApp(bundleId: "com.atebits.Tweetie2")
                log("X_LAUNCHED_now_backgrounded @\(elapsed())")
            } catch {
                log("WDA_FAIL \(error) @\(elapsed())")
            }

            // 4) wait past the ~30s suspension threshold, then prove CPU inference runs
            try? await Task.sleep(nanoseconds: 40_000_000_000)
            log("AWOKE_AFTER_SLEEP @\(elapsed())")   // if suspended, this never prints
            // Run THREE sequential generates to test whether repeated calls on one
            // engine degrade (the real-app summarize — the 3rd call — emitted 1 token).
            for i in 1...3 {
                var out = ""
                _ = try? await engine.generate(prompt: "Write two short sentences about the number \(i).", maxTokens: 40) { out += $0 }
                log("GEN\(i)_LEN\(out.count) '\(out.trimmingCharacters(in: .whitespacesAndNewlines).prefix(80))'")
            }

            // 5) read X's screen via WDA to see if the feed is inspectable
            do {
                let src = try await wda.source()
                log("X_SOURCE_LEN \(src.count) @\(elapsed())")
            } catch { log("X_SOURCE_FAIL \(error)") }

            log("DONE @\(elapsed())")
        } catch {
            log("ENGINE_FAIL \(error)")
        }
    }
}
