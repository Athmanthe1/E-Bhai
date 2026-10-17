"""Live smoke test for E-Bhai: chat -> tts -> stt. Needs SARVAM_API_KEY and network."""

import sarvam_core as core


def main() -> None:
    """Print a chat reply, the speech rendered from it, and its transcription."""
    reply = core.chat([{"role": "user", "content": "Introduce yourself in one short Hinglish sentence."}])
    print("CHAT:", reply)
    audio = core.tts(reply or "Namaste, main E-Bhai hoon.")
    with open("out.wav", "wb") as handle:
        handle.write(audio)
    print("WAV: out.wav", len(audio), "bytes")
    with open("out.wav", "rb") as handle:
        print("STT:", core.stt(handle))


if __name__ == "__main__":
    main()