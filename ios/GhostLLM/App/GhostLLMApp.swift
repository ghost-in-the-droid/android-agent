import SwiftUI

@main
struct GhostLLMApp: App {
    var body: some Scene {
        WindowGroup {
            // Agent is the DEFAULT experience (uses its built-in r/LocalLLaMA goal),
            // so a bare launch — no env vars — runs the real on-device agent cleanly.
            // Opt out with GHOST_CHAT=1 (plain chat) or GHOST_DEMO=1 (scripted demo).
            if ProcessInfo.processInfo.environment["GHOST_BGTEST"] == "1" {
                BGDriveTestView()  // validate background-drive architecture
            } else if ProcessInfo.processInfo.environment["GHOST_CHAT"] == "1" {
                ContentView()
            } else if ProcessInfo.processInfo.environment["GHOST_DEMO"] == "1" {
                DemoView()         // scripted hero demo (fetch + summarize)
            } else {
                AgentChatView()    // real on-device agent, Android-style chat UI
            }
        }
    }
}
