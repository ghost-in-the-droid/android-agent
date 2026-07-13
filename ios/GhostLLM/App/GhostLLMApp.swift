import SwiftUI

@main
struct GhostLLMApp: App {
    var body: some Scene {
        WindowGroup {
            if ProcessInfo.processInfo.environment["GHOST_DEMO"] == "1" {
                DemoView()   // self-running hero demo, zero UI-driving
            } else {
                ContentView()
            }
        }
    }
}
