// devsper_dictation — macOS native dictation helper for the devsper REPL.
//
// Protocol:
//   • Starts capturing mic audio immediately on launch.
//   • Streams audio through SFSpeechRecognizer (on-device when available).
//   • Partial results are written to stderr so Python can show live text.
//   • Stops automatically when speech silence is detected (isFinal = true).
//   • Also stops on SIGTERM (Python sends this for early cancellation).
//   • Final transcript printed to stdout, then exits 0.
//
// Compile:
//   swiftc -framework Foundation -framework Speech -framework AVFoundation \
//          -O devsper_dictation.swift -o devsper-dictation

import AVFoundation
import Foundation
import Speech

// Global used by the SIGTERM handler (C fn pointers can't capture context)
var _gRequest: SFSpeechAudioBufferRecognitionRequest?

// MARK: - Helpers

func fail(_ msg: String) -> Never {
    fputs("error: \(msg)\n", stderr)
    exit(1)
}

// MARK: - Authorization (synchronous)

func authorize() {
    let sem = DispatchSemaphore(value: 0)
    SFSpeechRecognizer.requestAuthorization { _ in sem.signal() }
    sem.wait()

    guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
        fail(
            "speech recognition not authorized — go to System Settings › Privacy & Security › Speech Recognition"
        )
    }
}

// MARK: - Main

func run() {
    authorize()

    guard let recognizer = SFSpeechRecognizer(locale: Locale.current) ?? SFSpeechRecognizer()
    else { fail("no speech recognizer available for this locale") }
    guard recognizer.isAvailable else { fail("speech recognizer is unavailable right now") }

    let engine = AVAudioEngine()
    let request = SFSpeechAudioBufferRecognitionRequest()
    request.shouldReportPartialResults = true
    if #available(macOS 13, *) {
        // Prefer on-device — no network needed, faster, private
        request.requiresOnDeviceRecognition = recognizer.supportsOnDeviceRecognition
        request.addsPunctuation = true
    }

    let inputNode = engine.inputNode
    let format = inputNode.outputFormat(forBus: 0)
    inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buf, _ in
        request.append(buf)
    }

    var latestTranscript = ""
    let doneSem = DispatchSemaphore(value: 0)

    recognizer.recognitionTask(with: request) { result, error in
        if let result {
            latestTranscript = result.bestTranscription.formattedString
            // Overwrite the same line on stderr — Python mirrors this live
            fputs("\r\u{1B}[2K\(latestTranscript)", stderr)
            if result.isFinal {
                doneSem.signal()
            }
        }
        if let error {
            let code = (error as NSError).code
            // 216 = "no speech detected" — soft, not a crash
            if code != 216 {
                fputs("\nerror: \(error.localizedDescription)\n", stderr)
            }
            doneSem.signal()
        }
    }

    do { try engine.start() } catch { fail("could not start audio engine: \(error)") }

    // SIGTERM handler — Python sends this when user cancels early.
    // C function pointers can't capture context, so store request in a global.
    _gRequest = request
    signal(SIGTERM) { _ in _gRequest?.endAudio() }

    // Hard timeout: 60 s max, in case silence detection never fires
    DispatchQueue.global().asyncAfter(deadline: .now() + 60) {
        request.endAudio()
    }

    doneSem.wait()

    engine.stop()
    inputNode.removeTap(onBus: 0)

    // Clear the partial-result stderr line, print final to stdout
    fputs("\r\u{1B}[2K", stderr)
    if !latestTranscript.isEmpty {
        print(latestTranscript)
    }
}

run()
