"""Sarvam API wrapper for E-Bhai: chat, speech-to-text, text-to-speech, translate."""

import base64
import io
import json
import logging
import os
import re
import tempfile
import time
import wave
from typing import Any

from sarvamai import SarvamAI

logger = logging.getLogger(__name__)
LANG_CODES = {"English": "en-IN", "Hindi": "hi-IN", "Hinglish": "hi-IN"}
_client: SarvamAI | None = None


class SarvamError(Exception):
    """A short, user-friendly description of something that went wrong."""


def _api_key() -> str:
    """Read the API key from the environment, then from Streamlit secrets."""
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets["SARVAM_API_KEY"]
        except Exception as exc:
            logger.debug("Streamlit secrets unavailable: %s", exc)
    if not key:
        raise SarvamError("Missing SARVAM_API_KEY")
    return str(key)


def get_client() -> SarvamAI:
    """Return the cached SarvamAI client, building it on first use."""
    global _client
    if _client is None:
        key = _api_key()
        try:
            _client = SarvamAI(api_subscription_key=key)
        except Exception as exc:
            logger.exception("could not build the Sarvam client")
            raise SarvamError("Sarvam is unreachable; check your API key.") from exc
    return _client


def clean_reply(text: str) -> str:
    """Drop <think>...</think> reasoning blocks and trim the result."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE).strip()


def extract_json(text: str) -> dict | None:
    """Return the first balanced JSON object embedded in `text`, else None."""
    body = (text or "").replace("```json", "").replace("```", "")
    openings = (i for i, char in enumerate(body) if char == "{")
    for start in openings:
        try:
            data, _ = json.JSONDecoder().raw_decode(body, start)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return None


def split_sentences(text: str, max_len: int = 400) -> list[str]:
    """Split text into non-empty chunks of at most `max_len` characters."""
    pieces: list[str] = []
    for raw in re.split(r"(?<=[.!?।॥])\s+", (text or "").strip()):
        piece = raw.strip()
        while len(piece) > max_len:
            pieces.append(piece[:max_len])
            piece = piece[max_len:]
        if piece:
            pieces.append(piece)
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + 1 + len(piece) <= max_len:
            chunks[-1] = f"{chunks[-1]} {piece}"
        else:
            chunks.append(piece)
    return chunks


def chat(messages: list[dict], model: str = "sarvam-105b") -> str:
    """Ask Sarvam chat, retrying once after ~1s, and return the clean reply."""
    api = get_client().chat
    failure: Exception | None = None
    for attempt in (1, 2):
        try:
            reply = api.completions(model=model, messages=messages)
            return clean_reply(reply.choices[0].message.content)
        except Exception as exc:
            failure = exc
            logger.warning("chat attempt %d failed: %s", attempt, exc)
            if attempt == 1:
                time.sleep(1)
    raise SarvamError("Sarvam chat failed; please try again shortly.") from failure


def stt(file_obj: Any, mode: str = "codemix") -> str:
    """Transcribe an open binary audio file and return the transcript."""
    api = get_client().speech_to_text
    try:
        reply = api.transcribe(file=file_obj, model="saaras:v4", mode=mode)
        return (reply.transcript or "").strip()
    except Exception as exc:
        logger.exception("speech-to-text failed")
        raise SarvamError("Could not understand that audio; please try again.") from exc


def stt_bytes(data: bytes, mode: str = "codemix") -> str:
    """Transcribe raw audio bytes via a temporary .wav file that is always removed."""
    handle, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(handle, "wb") as tmp:
            tmp.write(data)
        with open(path, "rb") as tmp:
            return stt(tmp, mode=mode)
    finally:
        if os.path.exists(path):
            os.remove(path)


def _merge_wavs(wavs: list[bytes]) -> bytes:
    """Merge WAV byte strings into one file, keeping the first file's parameters."""
    params, frames = None, b""
    for data in wavs:
        with wave.open(io.BytesIO(data), "rb") as reader:
            found = (reader.getparams(), reader.readframes(reader.getnframes()))
        params, frames = (params or found[0], frames + found[1])
    channels, width, rate, *_ = params
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setparams((channels, width, rate, len(frames) // max(1, channels * width), "NONE", "not compressed"))
        out.writeframes(frames)
    return buffer.getvalue()


def tts(text: str, lang: str = "hi-IN", speaker: str = "simran_en_customer") -> bytes:
    """Speak `text` as one valid WAV file, chunking long input and merging it."""
    chunks = split_sentences(text)
    if not chunks:
        raise SarvamError("There is nothing to speak.")
    api = get_client().text_to_speech  # "simran_en_customer" is the only verified speaker id
    try:
        wavs = [base64.b64decode("".join(api.convert(text=part, language_code=lang,
                 model="bulbul:v4-flash", speaker=speaker).audios)) for part in chunks]
        return wavs[0] if len(wavs) == 1 else _merge_wavs(wavs)
    except Exception as exc:
        logger.exception("text-to-speech failed")
        raise SarvamError("Could not generate speech; please try again.") from exc


def translate(text: str, target: str = "hi-IN", source: str = "auto") -> str:
    """Translate `text` and return the translated string."""
    api = get_client().text
    try:
        reply = api.translate(input=text, source_language_code=source,
                              target_language_code=target, speaker_gender="Male")
        return (reply.translated_text or "").strip()
    except Exception as exc:
        logger.exception("translation failed")
        raise SarvamError("Could not translate that; please try again.") from exc