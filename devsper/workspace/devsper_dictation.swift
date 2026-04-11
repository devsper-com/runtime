// devsper_dictation — macOS native dictation helper for the devsper REPL.
//
// Protocol:
//   • Starts capturing mic audio immediately on launch.
//   • Streams audio through SFSpeechRecognizer (server-based, works all locales).
//   • Partial results written to stderr (\r overwrite) for live feedback.
//   • Stops automatically on speech silence (SFSpeechRecognizer isFinal).
//   • SIGTERM for early cancellation (Python calls proc.terminate()).
//   • Final transcript printed to stdout, then exits 0.
//
// Compile:
//   swiftc -framework Foundation -framework Speech -framework AVFoundation \
//          -O devsper_dictation.swift -o devsper-dictation

import AVFoundation
import Foundation
import Speech

// Globals for signal handler — C fn ptrs can't capture context
var _gRequest: SFSpeechAudioBufferRecognitionRequest?
var _gEngine: AVAudioEngine?
var _gLatestTranscript = ""
var _gFinished = false

func finish(_ transcript: String) -> Never {
    guard !_gFinished else { exit(0) }
    _gFinished = true
    _gEngine?.stop()
    fputs("\r\u{1B}[2K", stderr)  // clear partial-result line
    if !transcript.isEmpty {
        print(transcript)
        fflush(stdout)
    }
    exit(0)
}

// ── Microphone permission ────────────────────────────────────────────────────
let micSem = DispatchSemaphore(value: 0)
AVCaptureDevice.requestAccess(for: .audio) { _ in micSem.signal() }
micSem.wait()

guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
    fputs("error: microphone not authorized — grant access in System Settings › Privacy › Microphone\n", stderr)
    exit(1)
}

// ── Speech recognition permission ───────────────────────────────────────────
let srSem = DispatchSemaphore(value: 0)
SFSpeechRecognizer.requestAuthorization { _ in srSem.signal() }
srSem.wait()

guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
    fputs("error: speech recognition not authorized — grant access in System Settings › Privacy › Speech Recognition\n", stderr)
    exit(1)
}

// ── Locale fallback: current → en-US → en-GB ────────────────────────────────
let localesToTry = [Locale.current, Locale(identifier: "en-US"), Locale(identifier: "en-GB")]
guard let recognizer = localesToTry
    .compactMap({ SFSpeechRecognizer(locale: $0) })
    .first(where: { $0.isAvailable })
else {
    fputs("error: no available speech recognizer\n", stderr)
    exit(1)
}
fputs("locale: \(recognizer.locale.identifier)\n", stderr)

// ── Audio engine + recognition request ──────────────────────────────────────
let engine = AVAudioEngine()
_gEngine = engine

let request = SFSpeechAudioBufferRecognitionRequest()
_gRequest = request
request.shouldReportPartialResults = true
if #available(macOS 13, *) {
    request.addsPunctuation = true
}

let inputNode = engine.inputNode
let hwFormat = inputNode.outputFormat(forBus: 0)

// Down-mix to mono 16 kHz — the format SFSpeechRecognizer prefers
let recFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                              sampleRate: 16_000,
                              channels: 1,
                              interleaved: false)!

inputNode.installTap(onBus: 0, bufferSize: 4096, format: hwFormat) { buf, _ in
    // Convert hardware format to 16 kHz mono before appending
    guard let converter = AVAudioConverter(from: hwFormat, to: recFormat),
          let converted = AVAudioPCMBuffer(
              pcmFormat: recFormat,
              frameCapacity: AVAudioFrameCount(
                  Double(buf.frameLength) * recFormat.sampleRate / hwFormat.sampleRate + 1
              )
          )
    else { return }
    var error: NSError?
    var inputBlock = buf  // capture
    var inputProvided = false
    converter.convert(to: converted, error: &error) { _, outStatus in
        if !inputProvided {
            inputProvided = true
            outStatus.pointee = .haveData
            return inputBlock
        }
        outStatus.pointee = .noDataNow
        return nil
    }
    if error == nil && converted.frameLength > 0 {
        request.append(converted)
    }
}

// ── Recognition task ─────────────────────────────────────────────────────────
recognizer.recognitionTask(with: request) { result, error in
    if let result {
        _gLatestTranscript = result.bestTranscription.formattedString
        fputs("\r\u{1B}[2K\(_gLatestTranscript)", stderr)
        if result.isFinal {
            finish(_gLatestTranscript)
        }
    }
    if let error {
        let code = (error as NSError).code
        // 216 = no speech detected, 203 = interrupted/cancelled — both are normal
        if code != 216 && code != 203 {
            fputs("\nerror (\(code)): \(error.localizedDescription)\n", stderr)
        }
        finish(_gLatestTranscript)
    }
}

do {
    try engine.start()
    fputs("recording\n", stderr)
} catch {
    fputs("error: could not start audio engine: \(error)\n", stderr)
    exit(1)
}

// SIGTERM — Python calls proc.terminate() for early cancellation
signal(SIGTERM) { _ in
    _gRequest?.endAudio()
}

// 60 s hard timeout
DispatchQueue.global().asyncAfter(deadline: .now() + 60) {
    _gRequest?.endAudio()
}

RunLoop.main.run()
