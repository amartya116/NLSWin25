import os
import sys
import pyttsx3


def synth_to_wav(text: str) -> None:
    """
    Speak text aloud in real-time using pyttsx3.
    
    Args:
        text: Text to speak
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Text is empty.")
    
    try:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        print(f"[TTS] Spoke: {text}", file=sys.stderr)
    except Exception as e:
        raise RuntimeError(f"TTS failed: {str(e)}")


def tts_status() -> dict:
    """Return TTS status."""
    return {
        "engine": "pyttsx3",
        "platform": sys.platform,
    }
