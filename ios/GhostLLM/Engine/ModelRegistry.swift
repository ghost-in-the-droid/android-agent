import Foundation

/// A downloadable / bundled on-device model. Mirrors the Android
/// `OnDeviceModelRegistry` entries so the two platforms track the same models.
struct ModelSpec: Identifiable, Equatable {
    let id: String
    let displayName: String
    let filename: String
    let url: URL?          // nil for bundled-only
    let sizeBytes: Int64
    let bundled: Bool      // shipped inside the app bundle

    var sizeLabel: String {
        ByteCountFormatter.string(fromByteCount: sizeBytes, countStyle: .file)
    }
}

enum ModelRegistry {
    /// Tiny model bundled for offline-out-of-the-box + the Phase 0 pipeline proof.
    static let phase0 = ModelSpec(
        id: "smollm2-360m",
        displayName: "SmolLM2 360M (bundled)",
        filename: "SmolLM2-360M-Instruct-Q4_K_M.gguf",
        url: URL(string: "https://huggingface.co/bartowski/SmolLM2-360M-Instruct-GGUF/resolve/main/SmolLM2-360M-Instruct-Q4_K_M.gguf"),
        sizeBytes: 270_590_880,
        bundled: true
    )

    /// Production default — same GGUF the Android registry ships (cross-platform
    /// parity). Downloaded on first run into the Documents dir.
    static let gemma4E2B = ModelSpec(
        id: "gemma-4-e2b",
        displayName: "Gemma 4 E2B (Q4_K_M)",
        filename: "gemma-4-E2B-it-Q4_K_M.gguf",
        url: URL(string: "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf"),
        sizeBytes: 3_106_735_776,
        bundled: false
    )

    static let all: [ModelSpec] = [phase0, gemma4E2B]
    static let defaultModel = phase0   // load instantly offline; user can pull Gemma
}
