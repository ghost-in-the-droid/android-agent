import SwiftUI

@main
struct GhostLLMApp: App {
    var body: some Scene {
        WindowGroup {
            if ProcessInfo.processInfo.environment["GHOST_AGENT"] == "1" {
                InAppAgentView()   // real on-device agent: Gemma drives an in-app browser
            } else if ProcessInfo.processInfo.environment["GHOST_DEMO"] == "1" {
                DemoView()         // scripted hero demo (fetch + summarize)
            } else {
                ContentView()
            }
        }
    }
}
