import SwiftUI

/// Full-screen demo narrative — designed to read clearly as a per-device tile.
struct DemoView: View {
    @StateObject private var vm = DemoViewModel()

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.06, green: 0.06, blue: 0.10), .black],
                           startPoint: .top, endPoint: .bottom).ignoresSafeArea()
            VStack(alignment: .leading, spacing: 18) {
                header
                narrationLine
                if !vm.postTitle.isEmpty { postCard }
                if !vm.summary.isEmpty { summaryCard }
                Spacer()
                if !vm.stats.isEmpty { footer }
            }
            .padding(20)
        }
        .task { await vm.run() }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Text("👻").font(.system(size: 34))
            VStack(alignment: .leading, spacing: 2) {
                Text("Ghost").font(.title2.bold()).foregroundStyle(.white)
                Text("on-device agent").font(.caption).foregroundStyle(.white.opacity(0.55))
            }
            Spacer()
            badge("A17 Pro · Metal · offline")
        }
    }

    private var narrationLine: some View {
        HStack(spacing: 8) {
            if !vm.done { ProgressView().tint(.white).scaleEffect(0.8) }
            Text(vm.narration)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.white.opacity(0.9))
                .animation(.easeInOut, value: vm.narration)
        }
    }

    private var postCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Text(vm.subreddit).font(.caption.bold()).foregroundStyle(Color(red: 1, green: 0.4, blue: 0.3))
                Text("· top post · \(vm.sourceLabel)").font(.caption2).foregroundStyle(.white.opacity(0.4))
            }
            Text(vm.postTitle).font(.headline).foregroundStyle(.white).fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
    }

    private var summaryCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("On-device summary", systemImage: "sparkles")
                .font(.caption.bold()).foregroundStyle(.white.opacity(0.6))
            Text(vm.summary)
                .font(.body)
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(colors: [Color(red: 0.10, green: 0.14, blue: 0.24), Color(red: 0.08, green: 0.09, blue: 0.14)],
                           startPoint: .topLeading, endPoint: .bottomTrailing),
            in: RoundedRectangle(cornerRadius: 16)
        )
        .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(.white.opacity(0.08)))
    }

    private var footer: some View {
        HStack(spacing: 6) {
            Image(systemName: "cpu").font(.caption2)
            Text(vm.stats).font(.caption2.monospaced())
        }
        .foregroundStyle(.white.opacity(0.5))
    }

    private func badge(_ text: String) -> some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.white.opacity(0.85))
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(.white.opacity(0.08), in: Capsule())
            .overlay(Capsule().strokeBorder(.white.opacity(0.12)))
    }
}
