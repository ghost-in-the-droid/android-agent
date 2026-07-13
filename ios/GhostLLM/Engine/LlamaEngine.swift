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

    var backend: String { backendName }

    // llama backend is process-global — init exactly once, never free it (freeing
    // it while another/future engine exists breaks model switching + perf).
    private static let backendInit: Void = { llama_backend_init() }()

    init(modelURL: URL, nCtx: UInt32 = 2048, nBatch: Int32 = 512) throws {
        let t0 = Date()
        _ = LlamaEngine.backendInit

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
        // Free this engine's model/context; leave the process-global backend alone.
        llama_free(ctx)
        llama_model_free(model)
    }

    /// Format a chat history using the model's built-in chat template (falls back
    /// to ChatML). `add_ass` appends the assistant-turn opening tokens.
    func formatChat(_ messages: [ChatTurn]) -> String {
        let tmpl = llama_model_chat_template(model, nil)  // model's default, or nil
        // strdup role/content so the C pointers stay valid across the call.
        var cStrings: [UnsafeMutablePointer<CChar>?] = []
        var chat: [llama_chat_message] = messages.map { turn in
            let r = strdup(turn.role)
            let c = strdup(turn.content)
            cStrings.append(r); cStrings.append(c)
            return llama_chat_message(role: r, content: c)
        }
        defer { cStrings.forEach { free($0) } }

        var buf = [CChar](repeating: 0, count: 8192)
        var n = llama_chat_apply_template(tmpl, &chat, messages.count, true, &buf, Int32(buf.count))
        if n > Int32(buf.count) {
            buf = [CChar](repeating: 0, count: Int(n) + 1)
            n = llama_chat_apply_template(tmpl, &chat, messages.count, true, &buf, Int32(buf.count))
        }
        guard n > 0 else {
            // Fallback: raw concatenation if the model ships no supported template.
            return messages.map { "\($0.role): \($0.content)" }.joined(separator: "\n") + "\nassistant:"
        }
        let bytes = buf.prefix(Int(n)).map { UInt8(bitPattern: $0) }
        return String(decoding: bytes, as: UTF8.self)
    }

    /// Clear the KV cache so the next prompt starts fresh (we re-feed the full
    /// templated history each turn — simple + correct for MVP-length chats).
    func resetContext() {
        llama_memory_clear(llama_get_memory(ctx), true)
    }

    func generate(
        prompt: String,
        maxTokens: Int,
        grammar: String? = nil,
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
        // Start every generation from a clean KV cache: we always feed positions
        // from 0, so stale KV entries (e.g. a prior warmup) collide — fatal under
        // Gemma's sliding-window attention. Makes generate() self-contained.
        llama_memory_clear(llama_get_memory(ctx), true)
        var batch = llama_batch_init(nBatch, 0, 1)
        defer { llama_batch_free(batch) }
        // Prefill in nBatch-sized chunks so a prompt longer than nBatch can't
        // overflow the batch buffers (that overran → SIGSEGV). Logits only on the
        // very last token.
        let step = Int(nBatch)
        var pos = 0
        while pos < promptTokens.count {
            let end = min(pos + step, promptTokens.count)
            let chunk = Array(promptTokens[pos..<end])
            fill(&batch, with: chunk, startPos: Int32(pos))
            let isLast = end == promptTokens.count
            if isLast { batch.logits[Int(batch.n_tokens) - 1] = 1 }
            guard llama_decode(ctx, batch) == 0 else { throw InferenceError.contextFailed }
            pos = end
        }

        // --- Decode loop ---
        // Chain order matters: penalties → grammar → greedy. The grammar mask must
        // be applied LAST before the selector, or the selector picks an unmasked
        // token and llama_sampler_accept crashes ('empty grammar stack').
        let usingGrammar = grammar != nil
        let chain = llama_sampler_chain_init(llama_sampler_chain_default_params())
        llama_sampler_chain_add(chain, llama_sampler_init_penalties(256, 1.2, 0.0, 0.0))
        if let grammar, let g = llama_sampler_init_grammar(vocab, grammar, "root") {
            llama_sampler_chain_add(chain, g)
        }
        llama_sampler_chain_add(chain, llama_sampler_init_greedy())
        defer { llama_sampler_free(chain) }

        let genStart = Date()
        var nCur = batch.n_tokens
        var generated = 0
        var firstToken = ""
        // In grammar mode, stop after one balanced JSON object: accepting a token
        // past a completed grammar throws an (uncatchable) C++ exception.
        var braceDepth = 0
        var sawOpenBrace = false

        for _ in 0..<maxTokens {
            // llama_sampler_sample already calls accept internally — a second accept
            // double-advances the grammar and crashes ('empty grammar stack').
            let next = llama_sampler_sample(chain, ctx, -1)
            if llama_vocab_is_eog(vocab, next) { break }

            let piece = detokenize(next)
            if generated == 0 { firstToken = piece }
            generated += 1
            onToken(piece)

            if usingGrammar {
                for ch in piece {
                    if ch == "{" { braceDepth += 1; sawOpenBrace = true }
                    else if ch == "}" { braceDepth -= 1 }
                }
                if sawOpenBrace && braceDepth <= 0 { break }   // one complete object
            }

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
