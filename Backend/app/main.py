from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import whisper
import pyttsx3
import tempfile
import os
import re

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


def _pick_best_voice(engine: pyttsx3.Engine):
    voices = engine.getProperty("voices") or []

    def score(v):
        name = (getattr(v, "name", "") or "").lower()
        vid = (getattr(v, "id", "") or "").lower()
        s = 0
        if "english" in name or "english" in vid:
            s += 10
        if re.search(r"\ben\b", name) or re.search(r"\ben\b", vid):
            s += 5
        if "afrikaans" in name or "afrikaans" in vid:
            s -= 10
        return s

    return sorted(voices, key=score, reverse=True)[0] if voices else None


def run_tts(text: str, output_wav: str) -> None:
    try:
        engine = pyttsx3.init()

        best = _pick_best_voice(engine)
        if best:
            engine.setProperty("voice", best.id)
            print(f"[TTS] Using voice: {best.name}")

        engine.setProperty("rate", 170)
        engine.setProperty("volume", 1.0)

        engine.save_to_file(text, output_wav)
        engine.runAndWait()

        print(f"[TTS] Saved audio to: {output_wav}")
    except Exception as e:
        raise RuntimeError(f"TTS failed: {e}")

def _safe_header(v: str) -> str:
    return (v or "").replace("\r", " ").replace("\n", " ").strip()


@app.post("/speech2speech")
async def speech_to_speech(audio: UploadFile = File(...)):
    if not audio.content_type or not audio.content_type.startswith(("audio/", "video/")):
        raise HTTPException(status_code=400, detail=f"Upload an audio file. Got: {audio.content_type}")

    with tempfile.TemporaryDirectory(dir=".") as tmpdir:
        raw_path = os.path.join(tmpdir, audio.filename or "input.bin")
        out_wav = os.path.join(tmpdir, "output_tts.wav")

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
            run_tts(response_text, out_wav)
            print("--------TTS file exists:", os.path.exists(out_wav), "size:", os.path.getsize(out_wav) if os.path.exists(out_wav) else None)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

        if not os.path.exists(out_wav) or os.path.getsize(out_wav) == 0:
            raise HTTPException(status_code=500, detail="TTS produced no output.")

        with open(out_wav, "rb") as f:
            audio_bytes = f.read()

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "X-Transcript": _safe_header(transcript),
                "X-Assistant-Text": _safe_header(response_text),
                "Content-Disposition": 'attachment; filename="speech_output.wav"',
            },
        )


@app.get("/health")
async def health_check():
    return {"status": "healthy", "asr_model": "whisper(base)", "tts_engine": "pyttsx3"}
