"""Offline tests for sarvam_core: no network, no API key."""

import base64
import io
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sarvam_core as core  # noqa: E402


def _wav(frames: int) -> bytes:
    """Return a tiny mono 16-bit 16 kHz WAV holding `frames` silent frames."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setparams((1, 2, 16000, frames, "NONE", "not compressed"))
        writer.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


def test_extract_json() -> None:
    """Clean, fenced, reasoning-prefixed, garbage and empty input."""
    assert core.extract_json('{"a": 1}') == {"a": 1}
    assert core.extract_json('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert core.extract_json('Sure! {"plan": "revise"} done') == {"plan": "revise"}
    assert core.extract_json('{"a": "}"}') == {"a": "}"}
    assert core.extract_json("no json here") is None
    assert core.extract_json("{not json}") is None
    assert core.extract_json("") is None


def test_split_sentences() -> None:
    """Short text stays whole, long text hard-splits, blanks give no chunks."""
    assert core.split_sentences("Hi there. How are you?") == ["Hi there. How are you?"]
    assert core.split_sentences("") == []
    assert core.split_sentences("  \n ") == []
    long_text = "x" * 950
    chunks = core.split_sentences(long_text, max_len=400)
    assert chunks == ["x" * 400, "x" * 400, "x" * 150]
    assert all(chunk and len(chunk) <= 400 for chunk in chunks)
    assert "".join(chunks) == long_text


def test_split_sentences_uses_danda() -> None:
    """The Devanagari danda is a sentence boundary."""
    assert core.split_sentences("नमस्ते। कैसे हो?", max_len=8) == ["नमस्ते।", "कैसे हो?"]


def test_clean_reply() -> None:
    """Reasoning blocks disappear; plain text is only trimmed."""
    assert core.clean_reply("<think>hmm</think>\nFinal answer") == "Final answer"
    assert core.clean_reply("  Plain text  ") == "Plain text"


def test_tts_merges_chunks_into_one_wav(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two synthesized chunks must come back as one WAV with both frame counts."""
    calls = {"n": 0}

    def convert(text: str, language_code: str, model: str, speaker: str) -> SimpleNamespace:
        calls["n"] += 1
        audio = _wav(2 if calls["n"] == 1 else 3)
        return SimpleNamespace(audios=[base64.b64encode(audio).decode()])

    client = SimpleNamespace(text_to_speech=SimpleNamespace(convert=convert))
    monkeypatch.setattr(core, "get_client", lambda: client)
    merged = core.tts("a" * 250 + ". " + "b" * 250)
    assert calls["n"] == 2
    with wave.open(io.BytesIO(merged), "rb") as reader:
        assert reader.getframerate() == 16000
        assert reader.getnframes() == 5
        assert reader.readframes(5) == b"\x00\x00" * 5


def test_tts_rejects_blank_text() -> None:
    """Blank input fails fast with a friendly error."""
    with pytest.raises(core.SarvamError):
        core.tts("   ")