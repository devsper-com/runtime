// devsper_dictation — macOS native dictation helper for the devsper REPL.
//
// Protocol:
//   • Starts capturing mic audio immediately on launch.
//   • Streams audio through SFSpeechRecognizer (on-device, no network needed).
//   • Partial results are written to stderr so Python can show live feedback.
//   • When Python closes the stdin pipe (spacebar released), audio ends.
//   • Final transcript is printed to stdout, then the process exits.
//
// Compile:
//   swiftc -framework Foundation -framework Speech -framework AVFoundation \
//          -O devsper_dictation.swift -o devsper-dictation

import Foundation
import Speech
import AVFoundation

// MARK: - Helpers

func fail(_ msg: String) -> Never {
    fputs("error: \(msg)\n", stderr)
    exit(1)
}

// MARK: - Authorization

func requestAuthorization() {
    let sem = DispatchSemaphore(value: 0)
    SFSpeechRecognizer.requestAuthorization { _ in sem.signal() }
    sem.wait()

    let status = SFSpeechRecognizer.authorizationStatus()
    guard status == .authorized else {
        fail("speech recognition not authorized — grant access in System Settings › Privacy & Security › Speech Recognition")
    }
}

// MARK: - Main

func run() {
    requestAuthorization()

    // Prefer on-device recognition when available (macOS 13+, no network required)
    guard let recognizer = SFSpeechRecognizer(locale: Locale.current) ?? SFSpeechRecognizer() else {
        fail("no speech recognizer available for this locale")
    }
    guard recognizer.isAvailable else {
        fail("speech recognizer is unavailable right now")
    }

    let engine   = AVAudioEngine()
    let request  = SFSpeechAudioBufferRecognitionRequest()

    request.shouldReportPartialResults = true
    // On-device model when supported (private API check — safe to ignore failure)
    if #available(macOS 13, *) {
        request.requiresOnDeviceRecognition = recognizer.supportsOnDeviceRecognition
        request.addsPunctuation = true
    }

    // Tap the input bus
    let inputNode = engine.inputNode
    let format    = inputNode.outputFormat(forBus: 0)
    inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buf, _ in
        request.append(buf)
    }

    // ── Recognition task ────────────────────────────────────────────────────
    var latestTranscript = ""
    let finalSem = DispatchSemaphore(value: 0)

    recognizer.recognitionTask(with: request) { result, error in
        if let result {
            latestTranscript = result.bestTranscription.formattedString
            // Stream partial results to stderr so Python can show live text
            fputs("\r\u{1B}[2K" + latestTranscript, stderr)
            if result.isFinal {
                finalSem.signal()
            }
        }
        if let error {
            // Don't treat "no speech detected" (216) as a hard error
            let nsError = error as NSError
            if nsError.code != 216 {
                fputs("\nerror: \(error.localizedDescription)\n", stderr)
            }
            finalSem.signal()
        }
    }

    // ── Start engine ────────────────────────────────────────────────────────
    do {
        try engine.start()
    } catch {
        fail("could not start audio engine: \(error)")
    }

    // ── Wait for stdin close (Python releases spacebar) ─────────────────────
    // Python closes the write end of the pipe → stdin reaches EOF here.
    DispatchQueue.global(qos: .userInteractive).async {
        FileHandle.standardInput.readDataToEndOfFile()
        // Signal end of audio to the recognizer
        request.endAudio()
        engine.stop()
        inputNode.removeTap(onBus: 0)
        // Give the recognizer up to 4 s to produce a final result
        let waited = finalSem.wait(timeout: .now() + 4.0)
        if waited == .timedOut { finalSem.signal() }
    }

    finalSem.wait()

    // Clear the partial-result line on stderr, print final to stdout
    fputs("\r\u{1B}[2K", stderr)
    if !latestTranscript.isEmpty {
        print(latestTranscript)
    }
}

run()
