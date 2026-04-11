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

// Global for SIGTERM handler — C fn ptrs can't capture context
var _gRequest: SFSpeechAudioBufferRecognitionRequest?
var _gEngine: AVAudioEngine?
var _gLatestTranscript = ""

func finish(_ transcript: String) -> Never {
    _gEngine?.stop()
    fputs("\r\u{1B}[2K", stderr)  // clear partial-result line
    if !transcript.isEmpty {
        print(transcript)
    }
    exit(0)
}

func authorize() {
    // SFSpeechRecognizer auth must run on main thread; since we call this
    // before RunLoop.main.run() we use a semaphore to wait inline.
    let sem = DispatchSemaphore(value: 0)
    SFSpeechRecognizer.requestAuthorization { _ in sem.signal() }
    sem.wait()

    guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
        fputs("error: speech recognition not authorized — System Settings › Privacy & Security › Speech Recognition\n", stderr)
        exit(1)
    }
}

authorize()

// Prefer current locale; fall back to en-US / en-GB.
// On-device models are locale-specific and often absent (e.g. en-IN).
let localesToTry = [Locale.current, Locale(identifier: "en-US"), Locale(identifier: "en-GB")]
guard let recognizer = localesToTry
    .compactMap({ SFSpeechRecognizer(locale: $0) })
    .first(where: { $0.isAvailable })
else {
    fputs("error: no available speech recognizer\n", stderr)
    exit(1)
}
fputs("locale: \(recognizer.locale.identifier)\n", stderr)

let engine = AVAudioEngine()
_gEngine = engine

let request = SFSpeechAudioBufferRecognitionRequest()
_gRequest = request
request.shouldReportPartialResults = true
// Server-based recognition — works for all locales, no on-device model needed
if #available(macOS 13, *) {
    request.addsPunctuation = true
}

let inputNode = engine.inputNode
let format = inputNode.outputFormat(forBus: 0)
inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buf, _ in
    request.append(buf)
}

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
        // 216 = no speech, 203 = interrupted/cancelled — both are expected
        if code != 216 && code != 203 {
            fputs("\nerror: \(error.localizedDescription)\n", stderr)
        }
        finish(_gLatestTranscript)
    }
}

do {
    try engine.start()
} catch {
    fputs("error: could not start audio engine: \(error)\n", stderr)
    exit(1)
}

// SIGTERM — Python calls proc.terminate() for early cancellation
signal(SIGTERM) { _ in
    _gRequest?.endAudio()
    // finish() will be called from the recognition callback above
}

// 60 s hard timeout
DispatchQueue.global().asyncAfter(deadline: .now() + 60) {
    _gRequest?.endAudio()
}

// Keep main RunLoop alive — recognition callbacks are delivered here
RunLoop.main.run()
