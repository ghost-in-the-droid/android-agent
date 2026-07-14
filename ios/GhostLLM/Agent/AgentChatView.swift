import SwiftUI
import WebKit

struct WebViewContainer: UIViewRepresentable {
    let webView: WKWebView
    func makeUIView(context: Context) -> WKWebView { webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

/// Ghost's on-device agent, presented as a chat — matched to the Android app:
/// a dark green theme, a bubble transcript, and a bottom prompt field. The user
/// types a task; the on-device LLM drives the phone and reports back in-line.
struct AgentChatView: View {
    @StateObject private var vm = InAppAgentViewModel()
    @State private var draft = ""
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(GhostTheme.border)
            transcript
            if vm.running || !vm.chat.isEmpty { screenPanel }
            if !vm.activityLine.isEmpty { activityBar }
            Divider().overlay(GhostTheme.border)
            inputBar
        }
        .background(GhostTheme.bgBase.ignoresSafeArea())
        .task {
            await vm.prepare()
            let env = ProcessInfo.processInfo.environment
            // Record hook: GHOST_AUTOTYPE animates the prompt into the field (so a
            // screen recording shows a user typing), then submits. Opens the WDA
            // session first so the recorder's MJPEG stream is live before typing.
            if let g = env["GHOST_GOAL"], !g.isEmpty, env["GHOST_AUTOTYPE"] == "1" {
                await vm.startCaptureSession()
                try? await Task.sleep(nanoseconds: 1_800_000_000)  // let the recorder attach
                inputFocused = true
                for ch in g {                                       // "type" it out
                    draft.append(ch)
                    try? await Task.sleep(nanoseconds: 45_000_000)
                }
                try? await Task.sleep(nanoseconds: 600_000_000)
                send()
            } else if let g = env["GHOST_GOAL"], !g.isEmpty {
                await vm.submit(goal: g)
            }
        }
    }

    // MARK: header
    private var header: some View {
        HStack(spacing: 10) {
            Text("👻").font(.system(size: 26))
                .shadow(color: GhostTheme.accent.opacity(0.5), radius: 6)
            VStack(alignment: .leading, spacing: 1) {
                Text("Ghost in the Droid")
                    .font(.system(size: 18, weight: .bold)).foregroundStyle(GhostTheme.text1)
                HStack(spacing: 6) {
                    Circle().fill(statusDot).frame(width: 6, height: 6)
                    Text(vm.running ? "working" : (vm.ready ? "on-device · \(vm.modelName)" : "loading…"))
                        .font(.system(size: 11, weight: .semibold)).foregroundStyle(GhostTheme.text2)
                }
            }
            Spacer()
            Text("on-device").font(.system(size: 10, weight: .semibold))
                .foregroundStyle(GhostTheme.accent)
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(GhostTheme.accent.opacity(0.12), in: Capsule())
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(GhostTheme.bgBase)
    }
    private var statusDot: Color {
        vm.running ? GhostTheme.dotWorking : (vm.chat.isEmpty ? GhostTheme.dotIdle : GhostTheme.dotDone)
    }

    // MARK: transcript
    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 8) {
                    if vm.chat.isEmpty { emptyState.padding(.top, 40) }
                    ForEach(vm.chat) { bubble(for: $0).id($0.id) }
                }
                .padding(12)
            }
            .onChange(of: vm.chat.count) { _, _ in
                if let last = vm.chat.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Text("Chat with the agent — it runs entirely on this phone.")
            Text("Try: “open r/LocalLLaMA and summarize the top posts”")
                .foregroundStyle(GhostTheme.text3)
        }
        .font(.system(size: 12)).lineSpacing(4)
        .foregroundStyle(GhostTheme.text4)
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder private func bubble(for m: ChatMsg) -> some View {
        switch m.role {
        case .user:
            HStack { Spacer(minLength: 40)
                Text(m.text).font(.system(size: 13)).foregroundStyle(.white)
                    .padding(.vertical, 8).padding(.horizontal, 12)
                    .background(GhostTheme.userBubble,
                                in: .rect(topLeadingRadius: 12, bottomLeadingRadius: 12, bottomTrailingRadius: 2, topTrailingRadius: 12))
            }
        case .assistant:
            HStack { Text(m.text).font(.system(size: 13)).foregroundStyle(GhostTheme.text1)
                    .textSelection(.enabled)
                    .padding(.vertical, 8).padding(.horizontal, 12)
                    .background(GhostTheme.bgDeep,
                                in: .rect(topLeadingRadius: 12, bottomLeadingRadius: 2, bottomTrailingRadius: 12, topTrailingRadius: 12))
                Spacer(minLength: 40) }
        case .tool:
            HStack { Text(m.text).font(.system(size: 11, weight: .medium)).foregroundStyle(GhostTheme.toolChip)
                    .padding(.vertical, 3).padding(.horizontal, 9)
                    .background(GhostTheme.toolChip.opacity(0.09), in: Capsule())
                    .overlay(Capsule().stroke(GhostTheme.toolChip.opacity(0.22), lineWidth: 1))
                Spacer(minLength: 40) }
        case .error:
            HStack { Text(m.text).font(.system(size: 11)).foregroundStyle(GhostTheme.stop)
                    .padding(.vertical, 6).padding(.horizontal, 10)
                    .background(GhostTheme.stop.opacity(0.08))
                    .overlay(Rectangle().frame(width: 2).foregroundStyle(GhostTheme.stop), alignment: .leading)
                    .clipShape(.rect(cornerRadius: 6))
                Spacer(minLength: 40) }
        }
    }

    // MARK: the phone screen the agent drives (its in-app browser)
    private var screenPanel: some View {
        WebViewContainer(webView: vm.webView)
            .frame(height: 220)
            .overlay(alignment: .topLeading) {
                Text("agent's screen").font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(GhostTheme.text3)
                    .padding(.horizontal, 7).padding(.vertical, 3)
                    .background(GhostTheme.bgCard.opacity(0.9), in: Capsule())
                    .padding(6)
            }
            .background(GhostTheme.bgDeep)
            .overlay(Rectangle().frame(height: 1).foregroundStyle(GhostTheme.border), alignment: .top)
    }

    private var activityBar: some View {
        HStack(spacing: 8) {
            Circle().fill(GhostTheme.activity).frame(width: 5, height: 5)
                .opacity(0.9)
            Text(vm.activityLine).font(.system(size: 10, design: .monospaced))
                .foregroundStyle(GhostTheme.activity)
            Spacer()
        }
        .padding(.horizontal, 14).padding(.vertical, 6)
        .background(GhostTheme.bgBase)
    }

    // MARK: input
    private var inputBar: some View {
        HStack(spacing: 8) {
            TextField("", text: $draft, prompt: Text(vm.running ? "Agent is working… type your next message"
                                                                 : "Tell the agent what to do…")
                        .foregroundColor(GhostTheme.text3))
                .font(.system(size: 13)).foregroundStyle(GhostTheme.text1)
                .focused($inputFocused)
                .submitLabel(.send)
                .onSubmit(send)
                .padding(.vertical, 9).padding(.horizontal, 12)
                .background(GhostTheme.bgDeep, in: .rect(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(GhostTheme.border, lineWidth: 1))
            Button(action: send) {
                Text(vm.running ? "•••" : "Send")
                    .font(.system(size: 12, weight: .semibold)).foregroundStyle(.white)
                    .padding(.vertical, 9).padding(.horizontal, 16)
                    .background(vm.running ? GhostTheme.text4 : GhostTheme.userBubble, in: .rect(cornerRadius: 8))
            }
            .disabled(vm.running || draft.trimmingCharacters(in: .whitespaces).isEmpty || !vm.ready)
            .opacity((vm.running || draft.trimmingCharacters(in: .whitespaces).isEmpty || !vm.ready) ? 0.4 : 1)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(GhostTheme.bgBase)
    }

    private func send() {
        let goal = draft
        guard !goal.trimmingCharacters(in: .whitespaces).isEmpty, !vm.running, vm.ready else { return }
        draft = ""; inputFocused = false
        Task { await vm.submit(goal: goal) }
    }
}
