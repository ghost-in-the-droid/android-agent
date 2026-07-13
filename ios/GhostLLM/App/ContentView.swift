import SwiftUI

/// M1 chat UI: a single-window chat backed by the on-device llama.cpp engine.
/// Streams the assistant reply token-by-token.
struct ContentView: View {
    @StateObject private var vm = ChatViewModel()
    @State private var draft = ""

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            messagesList
            Divider()
            composer
        }
        .task {
            await vm.loadDefaultModel()
            // Headless verification: `SIMCTL_CHILD_GHOST_AUTORUN=1` auto-sends a prompt.
            if ProcessInfo.processInfo.environment["GHOST_AUTORUN"] == "1", vm.ready {
                await vm.send("Say hello in one short sentence.")
            }
            if ProcessInfo.processInfo.environment["GHOST_DL_TEST"] == "1" {
                await vm.runDownloadSelfTest()
            }
            if ProcessInfo.processInfo.environment["GHOST_AGENT_TEST"] == "1" {
                await vm.runAgentSelfTest()
            }
        }
    }

    private var header: some View {
        VStack(spacing: 4) {
            HStack {
                Text("👻 Ghost LLM").font(.headline)
                Menu {
                    ForEach(vm.models) { spec in
                        Button {
                            Task { await vm.switchModel(to: spec) }
                        } label: {
                            Label(
                                "\(spec.displayName)\(ModelStore.isAvailable(spec) ? "" : " · ↓ \(spec.sizeLabel)")",
                                systemImage: spec.id == vm.currentModel.id ? "checkmark" : "cpu"
                            )
                        }
                    }
                } label: {
                    Image(systemName: "chevron.down.circle").font(.subheadline)
                }
                .disabled(vm.generating || vm.downloadProgress != nil)
            }
            if let p = vm.downloadProgress {
                ProgressView(value: p) { Text("downloading… \(Int(p * 100))%").font(.caption2) }
                    .padding(.horizontal, 24)
            }
            Text(vm.status)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
    }

    private var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(vm.messages) { msg in
                        bubble(for: msg).id(msg.id)
                    }
                }
                .padding(12)
            }
            .onChange(of: vm.messages.last?.text) { _, _ in
                if let last = vm.messages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
            }
        }
    }

    private func bubble(for msg: ChatMessage) -> some View {
        let isUser = msg.role == .user
        return HStack {
            if isUser { Spacer(minLength: 40) }
            Text(msg.text.isEmpty ? "…" : msg.text)
                .padding(10)
                .background(isUser ? Color.accentColor.opacity(0.9) : Color.gray.opacity(0.2))
                .foregroundStyle(isUser ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
            if !isUser { Spacer(minLength: 40) }
        }
    }

    private var composer: some View {
        HStack(spacing: 8) {
            TextField("Message (runs on-device)…", text: $draft, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .disabled(!vm.ready || vm.generating)
                .onSubmit(sendDraft)
            Button(action: sendDraft) {
                Image(systemName: "arrow.up.circle.fill").font(.title2)
            }
            .disabled(!vm.ready || vm.generating || draft.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(10)
    }

    private func sendDraft() {
        let text = draft
        draft = ""
        Task { await vm.send(text) }
    }
}
