import Foundation

/// Resolves where a model's GGUF lives: bundled models come from the app bundle;
/// downloaded models live in Documents/models (survives app updates, user-visible).
enum ModelStore {
    static let phase0ModelName = ModelRegistry.phase0.filename.replacingOccurrences(of: ".gguf", with: "")

    static var modelsDir: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dir = docs.appendingPathComponent("models", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static func documentsURL(for spec: ModelSpec) -> URL {
        modelsDir.appendingPathComponent(spec.filename)
    }

    static func isAvailable(_ spec: ModelSpec) -> Bool {
        (try? resolvedURL(for: spec)) != nil
    }

    /// The on-disk URL to load from, or throws if the model isn't present yet.
    static func resolvedURL(for spec: ModelSpec) throws -> URL {
        if spec.bundled,
           let u = Bundle.main.url(forResource: spec.filename.replacingOccurrences(of: ".gguf", with: ""), withExtension: "gguf") {
            return u
        }
        let docs = documentsURL(for: spec)
        if FileManager.default.fileExists(atPath: docs.path) { return docs }
        throw InferenceError.modelNotFound(spec.filename)
    }

    // Back-compat for Phase 0 callers.
    static func bundledPhase0ModelURL() throws -> URL {
        try resolvedURL(for: ModelRegistry.phase0)
    }
}
