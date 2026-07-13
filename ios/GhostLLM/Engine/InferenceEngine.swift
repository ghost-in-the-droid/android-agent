import Foundation

/// Runtime-agnostic inference surface. llama.cpp is the MVP backend (GGUF parity
/// with the Android on-device path); an MLX backend can conform to this later
/// without touching call sites — mirrors Android's `Runtime { MEDIAPIPE, LLAMA_CPP }`.
protocol InferenceEngine: Actor {
    /// Generate up to `maxTokens`, streaming each decoded piece via `onToken`.
    /// Returns timing/shape info for the run.
    func generate(
        prompt: String,
        maxTokens: Int,
        onToken: @Sendable @escaping (String) -> Void
    ) async throws -> GenerationInfo
}

struct GenerationInfo {
    var promptTokens: Int
    var generatedTokens: Int
    var loadMillis: Int
    var genMillis: Int
    var backend: String
    var firstToken: String

    var tokensPerSecond: Double {
        genMillis > 0 ? Double(generatedTokens) / (Double(genMillis) / 1000.0) : 0
    }

    var summary: String {
        String(
            format: "prompt=%dtok gen=%dtok load=%dms gen=%dms (%.1f tok/s) backend=%@",
            promptTokens, generatedTokens, loadMillis, genMillis, tokensPerSecond, backend
        )
    }
}

enum InferenceError: Error, CustomStringConvertible {
    case modelNotFound(String)
    case loadFailed(String)
    case contextFailed
    case tokenizeFailed

    var description: String {
        switch self {
        case .modelNotFound(let p): return "model not found: \(p)"
        case .loadFailed(let p): return "llama_model_load_from_file failed: \(p)"
        case .contextFailed: return "llama_init_from_model failed"
        case .tokenizeFailed: return "llama_tokenize failed"
        }
    }
}
