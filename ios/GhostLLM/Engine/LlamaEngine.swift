import Foundation
import LlamaSwift

/// llama.cpp-backed on-device inference. Loads a GGUF and runs greedy decode.
/// All C pointers are confined to this actor, so they never cross a concurrency
/// boundary. Metal on device; CPU on the simulator (simulator has no Metal).
actor LlamaEngine: InferenceEngine {
    private let model: OpaquePointer
    private let ctx: OpaquePointer
    private let vocab: OpaquePointer
    private let backendName: String
    private let nBatch: Int32
    private let loadMillis: Int

    init(modelURL: URL, nCtx: UInt32 = 2048, nBatch: Int32 = 512) throws {
        let t0 = Date()
        llama_backend_init()

        var mparams = llama_model_default_params()
        #if targetEnvironment(simulator)
        mparams.n_gpu_layers = 0
        self.backendName = "cpu (simulator)"
        #else
        mparams.n_gpu_layers = 99
        self.backendName = "metal"
        #endif

        guard let m = llama_model_load_from_file(modelURL.path, mparams) else {
            throw InferenceError.loadFailed(modelURL.lastPathComponent)
        }

        var cparams = llama_context_default_params()
        cparams.n_ctx = nCtx
        cparams.n_batch = UInt32(nBatch)
        guard let c = llama_init_from_model(m, cparams) else {
            llama_model_free(m)
            throw InferenceError.contextFailed
        }

        self.model = m
        self.ctx = c
        self.vocab = llama_model_get_vocab(m)
        self.nBatch = nBatch
        self.loadMillis = Int(Date().timeIntervalSince(t0) * 1000)
    }

    deinit {
        llama_free(ctx)
        llama_model_free(model)
        llama_backend_free()
    }

    func generate(
        prompt: String,
        maxTokens: Int,
        onToken: @Sendable @escaping (String) -> Void
    ) async throws -> GenerationInfo {
        // --- Tokenize prompt ---
        let utf8Count = Int32(prompt.utf8.count)
        let cap = utf8Count + 1
        var tokens = [llama_token](repeating: 0, count: Int(cap))
        let n = llama_tokenize(vocab, prompt, utf8Count, &tokens, cap, /*add_special*/ true, /*parse_special*/ true)
        guard n > 0 else { throw InferenceError.tokenizeFailed }
        let promptTokens = Array(tokens.prefix(Int(n)))

        // --- Evaluate prompt ---
        var batch = llama_batch_init(nBatch, 0, 1)
        defer { llama_batch_free(batch) }
        fill(&batch, with: promptTokens, startPos: 0)
        batch.logits[Int(batch.n_tokens) - 1] = 1
        guard llama_decode(ctx, batch) == 0 else { throw InferenceError.contextFailed }

        // --- Greedy decode loop ---
        let vocabSize = Int(llama_vocab_n_tokens(vocab))
        let eos = llama_vocab_eos(vocab)
        let genStart = Date()
        var nCur = batch.n_tokens
        var generated = 0
        var firstToken = ""

        for _ in 0..<maxTokens {
            guard let logits = llama_get_logits_ith(ctx, batch.n_tokens - 1) else { break }
            var best = logits[0]
            var next: llama_token = 0
            for i in 1..<vocabSize where logits[i] > best {
                best = logits[i]
                next = llama_token(i)
            }
            if next == eos { break }

            let piece = detokenize(next)
            if generated == 0 { firstToken = piece }
            generated += 1
            onToken(piece)

            // feed the sampled token back in
            batch.n_tokens = 1
            batch.token[0] = next
            batch.pos[0] = nCur
            batch.n_seq_id[0] = 1
            if let seqIds = batch.seq_id, let seq0 = seqIds[0] { seq0[0] = 0 }
            batch.logits[0] = 1
            nCur += 1
            guard llama_decode(ctx, batch) == 0 else { break }
        }

        let genMillis = Int(Date().timeIntervalSince(genStart) * 1000)
        return GenerationInfo(
            promptTokens: promptTokens.count,
            generatedTokens: generated,
            loadMillis: loadMillis,
            genMillis: genMillis,
            backend: backendName,
            firstToken: firstToken
        )
    }

    // MARK: - helpers

    private func fill(_ batch: inout llama_batch, with toks: [llama_token], startPos: Int32) {
        batch.n_tokens = Int32(toks.count)
        for i in 0..<toks.count {
            batch.token[i] = toks[i]
            batch.pos[i] = startPos + Int32(i)
            batch.n_seq_id[i] = 1
            if let seqIds = batch.seq_id, let seqI = seqIds[i] { seqI[0] = 0 }
            batch.logits[i] = 0
        }
    }

    private func detokenize(_ token: llama_token) -> String {
        var buf = [CChar](repeating: 0, count: 64)
        let len = llama_token_to_piece(vocab, token, &buf, Int32(buf.count), 0, false)
        guard len > 0 else { return "" }
        let bytes = buf.prefix(Int(len)).map { UInt8(bitPattern: $0) }
        return String(decoding: bytes, as: UTF8.self)
    }
}
