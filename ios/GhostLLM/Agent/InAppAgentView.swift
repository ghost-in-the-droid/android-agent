import SwiftUI
import WebKit

struct WebViewContainer: UIViewRepresentable {
    let webView: WKWebView
    func makeUIView(context: Context) -> WKWebView { webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

/// Shows the on-device agent browsing live: the WebView it drives + the LLM's
/// tool-call transcript (proof every step is an LLM decision) + the final answer.
struct InAppAgentView: View {
    @StateObject private var vm = InAppAgentViewModel()
    private let goal = ProcessInfo.processInfo.environment["GHOST_GOAL"]
        ?? "Open https://old.reddit.com/r/LocalLLaMA/ and summarize what the community is discussing right now, in 2 sentences."

    var body: some View {
        VStack(spacing: 0) {
            header
            WebViewContainer(webView: vm.webView)
                .overlay(alignment: .topTrailing) {
                    if vm.thinking { thinkingChip.padding(8) }
                }
            transcriptStrip
            if !vm.answer.isEmpty { answerCard }
        }
        .task { await vm.run(goal: goal) }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("👻").font(.title2)
            VStack(alignment: .leading, spacing: 1) {
                Text("Ghost Agent").font(.headline)
                Text(vm.status).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            Text("on-device").font(.caption2.weight(.semibold))
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(.green.opacity(0.18), in: Capsule())
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(.ultraThinMaterial)
    }

    private var thinkingChip: some View {
        HStack(spacing: 6) {
            ProgressView().scaleEffect(0.7)
            Text("Gemma deciding…").font(.caption2)
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(.ultraThinMaterial, in: Capsule())
    }

    private var transcriptStrip: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(vm.transcript.enumerated()), id: \.offset) { i, line in
                        Text(line).font(.caption2.monospaced())
                            .foregroundStyle(line.hasPrefix("tool") ? .primary : .secondary)
                            .frame(maxWidth: .infinity, alignment: .leading).id(i)
                    }
                }.padding(8)
            }
            .frame(height: 96)
            .background(Color(.secondarySystemBackground))
            .onChange(of: vm.transcript.count) { _, c in withAnimation { proxy.scrollTo(c - 1, anchor: .bottom) } }
        }
    }

    private var answerCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("On-device answer", systemImage: "sparkles").font(.caption.bold()).foregroundStyle(.secondary)
            Text(vm.answer).font(.callout)
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.accentColor.opacity(0.12))
    }
}
