import Foundation

/// Downloads a model GGUF into Documents/models with progress, using a
/// URLSessionDownloadTask (efficient for multi-GB files). Skips if already
/// present. This is the "download-on-first-run" path for the production model.
final class ModelDownloadManager: NSObject, URLSessionDownloadDelegate {
    private var session: URLSession!
    private var spec: ModelSpec?
    private var progressHandler: ((Double) -> Void)?
    private var continuation: CheckedContinuation<URL, Error>?

    override init() {
        super.init()
        let config = URLSessionConfiguration.default
        config.waitsForConnectivity = true
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }

    /// Ensure `spec` is on disk, downloading if needed. Returns its local URL.
    func ensure(_ spec: ModelSpec, onProgress: @escaping (Double) -> Void) async throws -> URL {
        if let existing = try? ModelStore.resolvedURL(for: spec) { return existing }
        guard let url = spec.url else { throw InferenceError.modelNotFound(spec.filename) }
        self.spec = spec
        self.progressHandler = onProgress
        return try await withCheckedThrowingContinuation { cont in
            self.continuation = cont
            session.downloadTask(with: url).resume()
        }
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didWriteData bytesWritten: Int64, totalBytesWritten: Int64,
                    totalBytesExpectedToWrite: Int64) {
        guard totalBytesExpectedToWrite > 0 else { return }
        let p = Double(totalBytesWritten) / Double(totalBytesExpectedToWrite)
        progressHandler?(p)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didFinishDownloadingTo location: URL) {
        guard let spec else { return }
        let dest = ModelStore.documentsURL(for: spec)
        do {
            try? FileManager.default.removeItem(at: dest)
            try FileManager.default.moveItem(at: location, to: dest)
            continuation?.resume(returning: dest)
        } catch {
            continuation?.resume(throwing: error)
        }
        continuation = nil
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error {
            continuation?.resume(throwing: error)
            continuation = nil
        }
    }
}
