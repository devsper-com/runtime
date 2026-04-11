"""Voice input for the coding REPL.

On macOS, uses the native Speech Recognition framework via a compiled Swift helper
(devsper_dictation). The helper is compiled automatically on first use with swiftc.
No API keys or extra Python packages required on macOS.

On other platforms (or if swiftc is unavailable), falls back to sounddevice +
OpenAI Whisper API / local whisper package.

Usage::

    voice = VoiceInput(console=rich_console)
    if voice.available:
        text = voice.prompt_with_voice("[bold cyan]myproject[/] [dim]>[/] ")
"""

from __future__ import annotations

import io
import logging
import re
import select
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SWIFT_SRC  = Path(__file__).parent / "devsper_dictation.swift"
_BIN_DIR    = Path.home() / ".local" / "share" / "devsper" / "bin"
_BIN_PATH   = _BIN_DIR / "devsper-dictation"

# ---------------------------------------------------------------------------
# macOS native dictation via Swift helper
# ---------------------------------------------------------------------------

class DictationHelper:
    """Manages compilation and use of the Swift dictation binary."""

    def __init__(self, console=None) -> None:
        self._console = console
        self._available: bool | None = None   # None = not yet checked
        self._current_proc: subprocess.Popen | None = None

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = self._check()
        return self._available

    def _check(self) -> bool:
        if sys.platform != "darwin":
            return False
        if not _SWIFT_SRC.exists():
            return False
        # Binary already compiled?
        if _BIN_PATH.exists():
            return True
        # Can we compile?
        return bool(shutil.which("swiftc"))

    def ensure_compiled(self) -> bool:
        """Compile the Swift helper if not already done. Returns True on success."""
        if _BIN_PATH.exists():
            return True
        if not shutil.which("swiftc"):
            return False

        self._print(
            "  [dim]Compiling dictation helper (first time only)...[/]",
            markup=True,
        )
        _BIN_DIR.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "swiftc",
                "-framework", "Foundation",
                "-framework", "Speech",
                "-framework", "AVFoundation",
                "-O",
                str(_SWIFT_SRC),
                "-o", str(_BIN_PATH),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.warning("[voice] swiftc failed:\n%s", result.stderr)
            self._available = False
            return False
        return True

    def record(self, tui_mode: bool = False) -> str:
        """Launch the helper, wait for silence detection, return transcript.

        The Swift binary stops itself via SFSpeechRecognizer's isFinal callback
        (fires ~1-2 s after the user stops talking).

        When ``tui_mode=True`` (running inside Textual) the raw-stdin cancel
        watcher is skipped because Textual already owns stdin.  SIGTERM is still
        sent on timeout.  The user cancels by pressing Escape in the TUI.
        """
        if not self.ensure_compiled():
            return ""

        try:
            proc = subprocess.Popen(
                [str(_BIN_PATH)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                # stderr NOT piped — Swift writes partial results (\r overwrite)
                # directly to the terminal.  Piping stderr + calling communicate()
                # creates a read-race that starves stdout → empty transcripts.
                stderr=None,
            )
        except OSError as exc:
            log.warning("[voice] could not launch dictation helper: %s", exc)
            return ""

        self._current_proc = proc  # expose for external termination

        self._print(
            "  [bold yellow]🎤[/] [dim]Speak now — pause to finish"
            + ("" if tui_mode else ", Enter to cancel")
            + "[/]",
            markup=True,
        )

        cancel_thread = None
        if not tui_mode:
            # ── Watch for Enter / Ctrl+C to cancel early (raw mode) ──────────
            def _watch_cancel():
                import tty
                import termios
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    while proc.poll() is None:
                        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                        if ready:
                            ch = sys.stdin.read(1)
                            if ch in ("\r", "\n", "\x03", "\x04"):
                                proc.terminate()
                                break
                except Exception:
                    pass
                finally:
                    try:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old)
                    except Exception:
                        pass

            cancel_thread = threading.Thread(target=_watch_cancel, daemon=True)
            cancel_thread.start()

        # ── Wait for binary to finish (silence detection or cancel) ──────────
        try:
            stdout, _ = proc.communicate(timeout=65)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()
        finally:
            self._current_proc = None  # clear ref once process is gone

        if cancel_thread:
            cancel_thread.join(timeout=0.2)

        if not tui_mode:
            # Clear the partial-result line Swift left on stderr
            sys.stderr.write("\r\033[2K")
            sys.stderr.flush()

        transcript = stdout.decode("utf-8", errors="replace").strip()
        if transcript:
            self._print(f"  [bold cyan]Heard:[/] {transcript}", markup=True)
        else:
            self._print("  [dim]Nothing heard — try again.[/]", markup=True)

        return transcript

    def _print(self, text: str, *, markup: bool = False) -> None:
        if self._console:
            self._console.print(text, markup=markup)
        else:
            print(re.sub(r"\[/?[^\]]*\]", "", text))


# ---------------------------------------------------------------------------
# Fallback: sounddevice + Whisper
# ---------------------------------------------------------------------------

def _has_audio_deps() -> bool:
    try:
        import sounddevice  # noqa: F401
        import numpy        # noqa: F401
        return True
    except ImportError:
        return False


def _can_transcribe() -> bool:
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        pass
    return False


def _to_wav_bytes(audio, sample_rate: int) -> bytes:
    import numpy as np
    audio_int16 = (audio * 32767).clip(-32768, 32767).astype("int16")
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    buf.seek(0)
    return buf.read()


def _whisper_transcribe(audio, sample_rate: int) -> str:
    wav_bytes = _to_wav_bytes(audio, sample_rate)
    try:
        import openai
        client = openai.OpenAI()
        f = io.BytesIO(wav_bytes)
        f.name = "audio.wav"
        return str(client.audio.transcriptions.create(model="whisper-1", file=f, response_format="text")).strip()
    except Exception as exc:
        log.debug("[voice] OpenAI whisper failed: %s", exc)
    try:
        import tempfile
        import whisper as _whisper
        model = _whisper.load_model("base")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name
        try:
            return _whisper.transcribe(model, tmp)["text"].strip()
        finally:
            Path(tmp).unlink(missing_ok=True)
    except Exception as exc:
        log.debug("[voice] local whisper failed: %s", exc)
    return ""


# ---------------------------------------------------------------------------
# VoiceInput — public API
# ---------------------------------------------------------------------------

class VoiceInput:
    """Hold-space voice input for the terminal REPL.

    On macOS uses the native Speech framework (via compiled Swift helper).
    Falls back to sounddevice + Whisper on other platforms.
    """

    SAMPLE_RATE = 16_000

    def __init__(self, console=None) -> None:
        self._console = console
        self._dictation = DictationHelper(console=console)
        self._whisper_ok = _has_audio_deps() and _can_transcribe()

    @property
    def available(self) -> bool:
        if sys.platform == "win32":
            return False
        return self._dictation.available or self._whisper_ok

    # ------------------------------------------------------------------

    def prompt_with_voice(self, prompt_text: str) -> str:
        """Show prompt; if user's first key is Space, record and transcribe."""
        if not self.available:
            return self._normal_input(prompt_text)
        try:
            return self._voice_aware_input(prompt_text)
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as exc:
            log.debug("[voice] error, falling back to normal input: %s", exc)
            return self._normal_input(prompt_text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _print(self, text: str, *, markup: bool = False) -> None:
        if self._console:
            self._console.print(text, markup=markup)
        else:
            print(re.sub(r"\[/?[^\]]*\]", "", text))

    def _normal_input(self, prompt_text: str) -> str:
        if self._console:
            try:
                return self._console.input(prompt_text)
            except Exception:
                pass
        return input(re.sub(r"\[/?[^\]]*\]", "", prompt_text))

    def _voice_aware_input(self, prompt_text: str) -> str:
        """Raw-mode prompt — intercept first Space for voice, else normal input."""
        import tty
        import termios

        clean_prompt = re.sub(r"\[/?[^\]]*\]", "", prompt_text)
        sys.stdout.write(clean_prompt)
        sys.stdout.flush()

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            first = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

        if first == "\x03":
            raise KeyboardInterrupt
        if first in ("\x04", ""):
            raise EOFError
        if first in ("\r", "\n"):
            return ""
        if first == " ":
            return self._record()

        # Normal typing: echo the char and read the rest of the line
        sys.stdout.write(first)
        sys.stdout.flush()
        try:
            rest = input()
        except EOFError:
            rest = ""
        return first + rest

    def _record(self, tui_mode: bool = False) -> str:
        """Route to macOS dictation or Whisper fallback."""
        if self._dictation.available:
            return self._dictation.record(tui_mode=tui_mode)
        return self._whisper_record()

    def _whisper_record(self) -> str:
        import sounddevice as sd
        import numpy as np

        self._print(
            "  [bold yellow]🎤[/] [dim]Recording — release Space or press Enter...[/]",
            markup=True,
        )

        chunks: list = []
        stop_event = threading.Event()

        def _cb(indata, frames, time_info, status):
            if not stop_event.is_set():
                chunks.append(indata.copy())

        stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=_cb,
        )

        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        last_space_at = time.monotonic()

        with stream:
            try:
                tty.setraw(fd)
                while True:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                    now = time.monotonic()
                    if ready:
                        ch = sys.stdin.read(1)
                        if ch in ("\r", "\n", "\x03", "\x04"):
                            break
                        if ch == " ":
                            last_space_at = now
                        else:
                            break
                    else:
                        if now - last_space_at > 0.3:
                            break
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            stop_event.set()

        if not chunks:
            self._print("  [dim]No audio captured.[/]", markup=True)
            return ""

        audio = np.concatenate(chunks, axis=0).flatten()
        if float(np.abs(audio).max()) < 0.005:
            self._print("  [dim]Too quiet.[/]", markup=True)
            return ""

        self._print("  [dim]Transcribing...[/]", markup=True)
        text = _whisper_transcribe(audio, self.SAMPLE_RATE)
        if text:
            self._print(f"  [bold cyan]Heard:[/] {text}", markup=True)
        else:
            self._print("  [dim]Could not transcribe.[/]", markup=True)
        return text
