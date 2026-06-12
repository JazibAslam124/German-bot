# tts.py - Text-to-speech via edge-tts (free, no API key)

import io
import asyncio
import edge_tts

# Good German voices:
# Female: de-DE-KatjaNeural, de-DE-SeraphinaMultilingualNeural
# Male:   de-DE-ConradNeural, de-DE-FlorianMultilingualNeural
DE_VOICE = "de-DE-KatjaNeural"


def _extract_german(text: str) -> str:
    """Extract only the [FRAGE] part for TTS — skip [KORREKTUR] corrections."""
    if "[FRAGE]" in text:
        frage_part = text.split("[FRAGE]", 1)[1].strip()
        return frage_part
    # If no label found, speak the whole thing (e.g. opening question)
    return text


async def synthesize(text: str) -> bytes | None:
    """Convert text to MP3 bytes using edge-tts. Returns None on failure."""
    spoken = _extract_german(text)
    if not spoken.strip():
        return None
    try:
        communicate = edge_tts.Communicate(spoken, DE_VOICE)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        audio = buf.read()
        return audio if audio else None
    except Exception as e:
        print(f"   [TTS] edge-tts failed: {e}")
        return None