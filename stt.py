# stt.py - Speech-to-text via Groq Whisper

import io
import os
from groq import AsyncGroq

_client: AsyncGroq | None = None


def get_client() -> AsyncGroq | None:
    global _client
    if _client is None:
        key = os.getenv("GROQ_STT_KEY") or os.getenv("GROQ_API_KEY", "")
        if key:
            _client = AsyncGroq(api_key=key)
        else:
            print("   [STT] No Groq key found — voice input disabled.")
    return _client


async def transcribe(audio_bytes: bytes, hint_language: str = "de") -> str | None:
    """
    Transcribe audio bytes (ogg/mp3/wav) to text.
    hint_language: ISO code hint — 'de' for German answers.
    Returns stripped transcript string, or None on failure.
    """
    client = get_client()
    if not client:
        return None
    try:
        buf = io.BytesIO(audio_bytes)
        buf.name = "voice.ogg"
        result = await client.audio.transcriptions.create(
            file=buf,
            model="whisper-large-v3",
            language=hint_language,
            response_format="text",
        )
        text = result.strip() if result else ""
        return text if len(text) >= 2 else None
    except Exception as e:
        print(f"   [STT] Transcription failed: {e}")
        return None