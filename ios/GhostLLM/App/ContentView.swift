import SwiftUI

/// Phase 0 UI: a single button that loads the bundled GGUF and generates one token,
/// proving the on-device llama.cpp pipeline end-to-end on the simulator.
struct ContentView: View {
    @State private var status: String = "idle"
    @State private var output: String = ""
    @State private var running = false

    var body: some View {
        VStack(spacing: 16) {
            Text("👻 Ghost LLM")
                .font(.largeTitle.bold())
            Text("on-device · llama.cpp")
                .font(.footnote)
                .foregroundStyle(.secondary)

            Button {
                Task { await runPhase0() }
            } label: {
                Text(running ? "generating…" : "Phase 0: generate one token")
                    .padding(.horizontal, 8)
            }
            .buttonStyle(.borderedProminent)
            .disabled(running)

            GroupBox("status") {
                Text(status).frame(maxWidth: .infinity, alignment: .leading)
            }
            GroupBox("output") {
                Text(output.isEmpty ? "—" : output)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Spacer()
        }
        .padding()
        .task { await runPhase0() }   // auto-run on launch for headless capture
    }

    @MainActor
    private func runPhase0() async {
        guard !running else { return }
        running = true
        defer { running = false }
        status = "loading model…"
        output = ""
        do {
            let url = try ModelStore.bundledPhase0ModelURL()
            let engine = try LlamaEngine(modelURL: url)
            status = "model loaded — generating…"
            let info = try await engine.generate(prompt: "Hello", maxTokens: 24) { piece in
                Task { @MainActor in output += piece }
            }
            status = "OK · \(info.summary)"
            print("PHASE0_RESULT first_token=<\(info.firstToken)> full=<\(output)> \(info.summary)")
        } catch {
            status = "ERROR: \(error)"
            output = ""
            print("PHASE0_ERROR \(error)")
        }
    }
}
