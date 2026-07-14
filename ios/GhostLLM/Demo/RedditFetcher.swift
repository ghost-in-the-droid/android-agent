import Foundation

struct RedditThread {
    let subreddit: String
    let title: String
    let comments: [String]
    let live: Bool   // true if fetched live, false if bundled fallback
}

/// Fetches the top r/LocalLLaMA thread for demo mode. Tries live Reddit JSON
/// (works from the phone's residential IP); falls back to a bundled real-thread
/// snapshot so the hero recording is bulletproof (no network variability).
enum RedditFetcher {
    static func topThread(subreddit: String = "LocalLLaMA") async -> RedditThread {
        if let live = try? await fetchLive(subreddit: subreddit), !live.comments.isEmpty {
            return live
        }
        return bundled()
    }

    private static func fetchLive(subreddit: String) async throws -> RedditThread {
        let ua = "GhostLLM-iOS-demo/0.1 (on-device summarizer)"
        func get(_ url: URL) async throws -> Any {
            var req = URLRequest(url: url, timeoutInterval: 6)
            req.setValue(ua, forHTTPHeaderField: "User-Agent")
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            return try JSONSerialization.jsonObject(with: data)
        }

        let listing = try await get(URL(string: "https://www.reddit.com/r/\(subreddit)/hot.json?limit=6&raw_json=1")!)
        let children = ((( listing as? [String: Any])?["data"] as? [String: Any])?["children"] as? [[String: Any]]) ?? []
        var post: [String: Any]?
        for c in children {
            let d = c["data"] as? [String: Any] ?? [:]
            if (d["stickied"] as? Bool) != true { post = d; break }
        }
        guard let p = post, let permalink = p["permalink"] as? String, let title = p["title"] as? String
        else { throw URLError(.cannotParseResponse) }

        let thread = try await get(URL(string: "https://www.reddit.com\(permalink).json?limit=20&raw_json=1")!)
        let arr = thread as? [Any] ?? []
        let commentsData = (arr.count > 1 ? arr[1] : nil) as? [String: Any]
        let cChildren = ((commentsData?["data"] as? [String: Any])?["children"] as? [[String: Any]]) ?? []
        var bodies: [String] = []
        for c in cChildren {
            let d = c["data"] as? [String: Any] ?? [:]
            if let body = d["body"] as? String, body.count > 20, (d["stickied"] as? Bool) != true {
                bodies.append(body)
            }
            if bodies.count >= 8 { break }
        }
        guard !bodies.isEmpty else { throw URLError(.cannotParseResponse) }
        return RedditThread(subreddit: "r/\(subreddit)", title: title, comments: bodies, live: true)
    }

    private static func bundled() -> RedditThread {
        guard let url = Bundle.main.url(forResource: "reddit_thread", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return RedditThread(subreddit: "r/LocalLLaMA", title: "On-device LLMs", comments: ["Running models locally keeps data private."], live: false)
        }
        return RedditThread(
            subreddit: obj["subreddit"] as? String ?? "r/LocalLLaMA",
            title: obj["title"] as? String ?? "",
            comments: obj["comments"] as? [String] ?? [],
            live: false
        )
    }
}
