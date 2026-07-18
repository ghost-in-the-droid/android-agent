import Foundation
import Network

/// Tiny best-effort HTTP status endpoint for multi-fleet per-device tiles.
/// `GET :8088/status` → {phase, tok_s, model, narration_last_line, ts}.
/// No serials/UDIDs. Failure-tolerant — never affects the demo if it can't bind.
final class StatusServer: @unchecked Sendable {
    static let shared = StatusServer()
    private let queue = DispatchQueue(label: "ghost.status")
    private var listener: NWListener?
    private var snapshot = #"{"phase":"idle"}"#

    func start(port: UInt16 = 8088) {
        queue.async {
            guard self.listener == nil, let p = NWEndpoint.Port(rawValue: port) else { return }
            guard let l = try? NWListener(using: .tcp, on: p) else { return }
            l.newConnectionHandler = { [weak self] c in self?.serve(c) }
            l.start(queue: self.queue)
            self.listener = l
        }
    }

    func update(phase: String, tokS: Double, model: String, line: String) {
        let ts = ISO8601DateFormatter().string(from: Date())
        let obj: [String: Any] = ["phase": phase, "tok_s": tokS, "model": model,
                                  "narration_last_line": line, "ts": ts]
        let body = (try? JSONSerialization.data(withJSONObject: obj))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        queue.async { self.snapshot = body }
    }

    private func serve(_ conn: NWConnection) {
        conn.start(queue: queue)
        conn.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] _, _, _, _ in
            let body = self?.snapshot ?? "{}"
            let resp = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n" +
                       "Access-Control-Allow-Origin: *\r\nConnection: close\r\n" +
                       "Content-Length: \(body.utf8.count)\r\n\r\n\(body)"
            conn.send(content: resp.data(using: .utf8), completion: .contentProcessed { _ in conn.cancel() })
        }
    }
}
