import os
from faster_whisper import WhisperModel

_model = None

def _get_model():
    global _model
    if _model is None:
        name = os.getenv("WHISPER_MODEL", "tiny.en")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        ctype = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        threads = int(os.getenv("CPU_THREADS", "4"))
        _model = WhisperModel(name, device=device, compute_type=ctype, cpu_threads=threads)
    return _model

def transcribe_wav(path: str) -> str:
    model = _get_model()
    segments, _ = model.transcribe(path, vad_filter=True, beam_size=5)
    return " ".join(s.text.strip() for s in segments if s.text)
