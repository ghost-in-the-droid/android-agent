import AVFoundation

/// Keeps the app running in the background while it drives another app (X) in the
/// foreground. An active audio session + the `audio` background mode stops iOS
/// suspending us; we emit continuous silence (volume 0, mixed with others) so we
/// never interrupt the user's audio. Without this the on-device agent loop freezes
/// ~30s after X takes the foreground.
final class KeepAlive {
    static let shared = KeepAlive()
    private let engine = AVAudioEngine()
    private var running = false

    func start() {
        guard !running else { return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
            try session.setActive(true)
            let fmt = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 2)!
            let src = AVAudioSourceNode { _, _, frameCount, ablPtr in
                let abl = UnsafeMutableAudioBufferListPointer(ablPtr)
                for buf in abl { memset(buf.mData, 0, Int(buf.mDataByteSize)) }
                return noErr
            }
            engine.attach(src)
            engine.connect(src, to: engine.mainMixerNode, format: fmt)
            engine.mainMixerNode.outputVolume = 0
            try engine.start()
            running = true
            print("KEEPALIVE_ON")
        } catch {
            print("KEEPALIVE_ERR \(error)")
        }
    }

    func stop() {
        guard running else { return }
        engine.stop()
        try? AVAudioSession.sharedInstance().setActive(false, options: [.notifyOthersOnDeactivation])
        running = false
        print("KEEPALIVE_OFF")
    }
}
