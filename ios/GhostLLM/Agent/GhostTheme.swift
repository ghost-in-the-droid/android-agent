import SwiftUI

/// One line in the chat transcript. `tool` renders as a subtle chip, the rest as
/// bubbles (user right-aligned indigo, assistant left-aligned deep, error red).
enum ChatRole { case user, assistant, tool, error }
struct ChatMsg: Identifiable { let id = UUID(); let role: ChatRole; let text: String }

/// Ghost brand palette — matched 1:1 to the Android app / dashboard theme
/// (frontend/src/assets/main.css + portal MainActivity). Dark, green-tinted.
enum GhostTheme {
    static let bgBase   = Color(hex: 0x0A0F0C)   // app background (darkest)
    static let bgCard   = Color(hex: 0x141E17)   // card / panel
    static let bgDeep   = Color(hex: 0x060A07)   // inset: text field, assistant bubble
    static let border   = Color(hex: 0x1E2E22)   // borders, dividers
    static let text1    = Color(hex: 0xE8EDE9)   // primary text
    static let text2    = Color(hex: 0xBEC8C0)   // secondary (labels)
    static let text3    = Color(hex: 0x8A9A8D)   // hints, placeholders
    static let text4    = Color(hex: 0x5A6E5E)   // disabled, empty-state
    static let accent   = Color(hex: 0x00E5A0)   // brand green — mascot, status
    static let accentLt = Color(hex: 0x6EFCD0)   // light mint
    // functional (chat)
    static let userBubble = Color(hex: 0x6366F1) // indigo — user + Send
    static let toolChip   = Color(hex: 0x38BDF8) // sky — tool-call chips
    static let activity   = Color(hex: 0xF59E0B) // amber — thinking indicator
    static let stop       = Color(hex: 0xEF4444) // red — Stop button
    static let dotWorking = Color(hex: 0xF59E0B)
    static let dotDone    = Color(hex: 0x22C55E)
    static let dotIdle    = Color(hex: 0x475569)
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red:   Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue:  Double(hex & 0xFF) / 255,
                  opacity: 1)
    }
}
