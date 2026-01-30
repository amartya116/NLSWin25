from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import whisper
import pyttsx3
import tempfile
import os
import re
import threading
import time
import uuid




from .integration import process_text_input
from .NLG import generate_nlg

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Transcript", "X-Assistant-Text"],
)

asr_model = whisper.load_model("base")

# Simple in-memory session state (persists last_location, last_date, etc. between requests)
SESSION_STATE = {}

TTS_LOCK = threading.Lock()
TTS_ENGINE = pyttsx3.init()

_best_voice = _pick_best_voice(TTS_ENGINE)
if _best_voice:
    TTS_ENGINE.setProperty("voice", _best_voice.id)
    print(f"[TTS] Default voice: {_best_voice.name} ({_best_voice.id})")
else:
    print("[TTS] Default voice: (none found)")

TTS_ENGINE.setProperty("rate", 160)   # less “chipmunk”
TTS_ENGINE.setProperty("volume", 1.0)


def _pick_best_voice(engine: pyttsx3.Engine):
    voices = engine.getProperty("voices") or []

    def score(v):
        name = (getattr(v, "name", "") or "").lower()
        vid = (getattr(v, "id", "") or "").lower()
        s = 0

        # strongly avoid Caribbean / weird accents
        if "caribbean" in name or "caribbean" in vid:
            s -= 200

        # prefer US/UK if present
        if any(k in name or k in vid for k in ["en-us", "en_us", "united states", "american"]):
            s += 100
        if any(k in name or k in vid for k in ["en-gb", "en_gb", "united kingdom", "great britain", "british"]):
            s += 90

        # generic English
        if "english" in name or "english" in vid:
            s += 20

        return s

    return max(voices, key=score) if voices else None



def run_tts(text: str) -> str:
    out_wav = f"/tmp/nls_tts_{uuid.uuid4().hex}.wav"
    os.makedirs("/tmp", exist_ok=True)

    with TTS_LOCK:
        # pyttsx3 can be flaky; make sure any old queue is cleared
        try:
            TTS_ENGINE.stop()
        except Exception:
            pass

        TTS_ENGINE.save_to_file(text, out_wav)
        TTS_ENGINE.runAndWait()

    # Wait for file to actually appear (espeak can finalize asynchronously)
    for _ in range(50):  # up to 5 seconds
        if os.path.exists(out_wav) and os.path.getsize(out_wav) > 0:
            return out_wav
        time.sleep(0.1)

    raise RuntimeError(f"TTS produced no output: {out_wav}")

def _safe_header(v: str) -> str:
    return (v or "").replace("\r", " ").replace("\n", " ").strip()


@app.post("/speech2speech")
async def speech_to_speech(audio: UploadFile = File(...)):
    if not audio.content_type or not audio.content_type.startswith(("audio/", "video/")):
        raise HTTPException(status_code=400, detail=f"Upload an audio file. Got: {audio.content_type}")

    with tempfile.TemporaryDirectory(dir=".") as tmpdir:
        raw_path = os.path.join(tmpdir, audio.filename or "input.bin")

        data_bytes = await audio.read()
        with open(raw_path, "wb") as f:
            f.write(data_bytes)

        # ASR
        try:
            result = asr_model.transcribe(raw_path, language="en", fp16=False)
            transcript = (result.get("text") or "").strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ASR (Whisper) failed: {e}")

        if not transcript:
            raise HTTPException(status_code=422, detail="Could not transcribe speech (empty result).")

        print(f"[ASR/Whisper] Transcribed: {transcript}")

        # Persistent dialogue state (single-session default)
        session_id = "default"
        dialogue_state = SESSION_STATE.setdefault(session_id, {})

        # NLU + execution
        try:
            execution_result = process_text_input(transcript, dialogue_state)
            print(f"[Integration] Execution Result: {execution_result}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Intent processing failed: {e}")

        # NLG
        try:
            nlg_input = {
                "intent": "response_generation",
                "entities": {},
                "tool_results": {"execution_result": execution_result},
                "conversation_state": {
                    "locale": "en",
                    "timezone": "Europe/Berlin",
                    "pending_slots": [],
                },
            }
            nlg_result = await generate_nlg(nlg_input)
            response_text = nlg_result.text
            print(f"[NLG] Generated Response: {response_text}")
        except Exception as e:
            response_text = execution_result
            print(f"[NLG] Failed, using fallback: {e}")

        # TTS
        try:
            out_wav = run_tts(response_text)
            print("--------TTS file exists:", os.path.exists(out_wav), "size:", os.path.getsize(out_wav))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

        with open(out_wav, "rb") as f:
            audio_bytes = f.read()

        # cleanup
        try:
            os.remove(out_wav)
        except Exception:
            pass
                


@app.get("/health")
async def health_check():
    return {"status": "healthy", "asr_model": "whisper(base)", "tts_engine": "pyttsx3"}
