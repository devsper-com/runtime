"""Voice input for the coding REPL.

Hold the spacebar to record, release to transcribe. Requires the `voice`
optional extra (sounddevice + numpy). Transcription uses the OpenAI Whisper
API if an API key is present, falling back to a local whisper model if the
`openai-whisper` package is installed.

Usage::

    voice = VoiceInput(console=rich_console)
    if voice.available:
        text = voice.prompt_with_voice("[bold cyan]myproject[/] [dim]>[/] ")
    else:
        text = console.input("[bold cyan]myproject[/] [dim]>[/] ")
"""

from __future__ import annotations

import io
import logging
import re
import select
import sys
import threading
import time
import wave
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

def _has_audio_deps() -> bool:
    try:
        import sounddevice  # noqa: F401
        import numpy  # noqa: F401
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


# ---------------------------------------------------------------------------
# Audio → WAV bytes (no soundfile dependency)
# ---------------------------------------------------------------------------

def _to_wav_bytes(audio, sample_rate: int) -> bytes:
    """Convert float32 numpy array to 16-bit WAV bytes using stdlib wave."""
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


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def _transcribe(audio, sample_rate: int) -> str:
    """Transcribe a numpy float32 audio array. Tries OpenAI then local whisper."""
    import numpy as np

    wav_bytes = _to_wav_bytes(audio, sample_rate)

    # ── OpenAI Whisper API ──────────────────────────────────────────────────
    try:
        import openai

        client = openai.OpenAI()
        wav_file = io.BytesIO(wav_bytes)
        wav_file.name = "audio.wav"
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=wav_file,
            response_format="text",
        )
        return str(result).strip()
    except Exception as exc:
        log.debug("[voice] OpenAI Whisper failed: %s", exc)

    # ── Local openai-whisper package ────────────────────────────────────────
    try:
        import tempfile
        from pathlib import Path
        import whisper

        model = whisper.load_model("base")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name
        try:
            result = model.transcribe(tmp)
            return result["text"].strip()
        finally:
            Path(tmp).unlink(missing_ok=True)
    except Exception as exc:
        log.debug("[voice] local whisper failed: %s", exc)

    return ""


# ---------------------------------------------------------------------------
# VoiceInput
# ---------------------------------------------------------------------------

class VoiceInput:
    """Hold-space voice input for the terminal REPL.

    When the user holds the spacebar at the prompt, audio is recorded via
    sounddevice. Releasing space (detected by 300 ms of key-repeat silence)
    stops recording and triggers Whisper transcription. Any other key also
    stops recording.

    Falls back transparently to normal text input when deps are missing or on
    Windows (where raw-mode terminal handling differs).
    """

    SAMPLE_RATE = 16_000  # Hz — Whisper's native rate

    def __init__(self, console=None) -> None:
        self._console = console
        self._audio_ok = _has_audio_deps()
        self._xscribe_ok = _can_transcribe()

    @property
    def available(self) -> bool:
        """True if both recording and transcription deps are present."""
        return self._audio_ok and self._xscribe_ok and sys.platform != "win32"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def prompt_with_voice(self, prompt_text: str) -> str:
        """Display *prompt_text* and return user input.

        If the user's first keystroke is Space, enters voice recording mode.
        Otherwise falls back to normal line input.
        """
        if not self.available:
            return self._normal_input(prompt_text)
        try:
            return self._voice_aware_input(prompt_text)
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as exc:
            log.debug("[voice] voice input error, falling back: %s", exc)
            return self._normal_input(prompt_text)

    # ------------------------------------------------------------------
    # Internal helpers
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
        clean = re.sub(r"\[/?[^\]]*\]", "", prompt_text)
        return input(clean)

    def _voice_aware_input(self, prompt_text: str) -> str:
        """Raw-mode prompt: intercept first Space for voice, else normal input."""
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

        if first == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        if first in ("\x04", ""):  # Ctrl+D / EOF
            raise EOFError
        if first == "\r" or first == "\n":
            return ""

        if first == " ":
            # Spacebar held — enter voice mode
            return self._record_and_transcribe()

        # Normal typing: echo the char and read the rest of the line
        sys.stdout.write(first)
        sys.stdout.flush()
        try:
            rest = input()
        except EOFError:
            rest = ""
        return first + rest

    def _record_and_transcribe(self) -> str:
        """Record audio until space is released, then transcribe."""
        import sounddevice as sd
        import numpy as np

        self._print(
            "\n  [bold yellow]🎤[/] [dim]Recording — release Space or press Enter to send...[/]",
            markup=True,
        )

        chunks: list = []
        stop_event = threading.Event()

        def _audio_cb(indata, frames, time_info, status):
            if not stop_event.is_set():
                chunks.append(indata.copy())

        stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=_audio_cb,
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
                            last_space_at = now  # still holding
                        else:
                            break  # any other key stops
                    else:
                        # No space char for > 300 ms → user released spacebar
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
            self._print("  [dim]Too quiet — nothing heard.[/]", markup=True)
            return ""

        self._print("  [dim]Transcribing...[/]", markup=True)
        text = _transcribe(audio, self.SAMPLE_RATE)

        if text:
            self._print(f"  [bold cyan]Heard:[/] {text}", markup=True)
        else:
            self._print("  [dim]Could not transcribe — try again.[/]", markup=True)

        return text
