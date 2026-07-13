import Foundation

/// Locates GGUF models. Phase 0 ships one model in the app bundle; the real app
/// will download-on-first-run into the Documents dir (see ModelRegistry, M1+).
enum ModelStore {
    /// The tiny model bundled for the Phase 0 pipeline proof.
    static let phase0ModelName = "SmolLM2-360M-Instruct-Q4_K_M"

    static func bundledPhase0ModelURL() throws -> URL {
        guard let url = Bundle.main.url(forResource: phase0ModelName, withExtension: "gguf") else {
            throw InferenceError.modelNotFound("\(phase0ModelName).gguf (not in app bundle)")
        }
        return url
    }
}
