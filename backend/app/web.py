import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from app.asr_local import transcribe_wav            # your ASR function
from app.tts_local import synth_to_wav, tts_status  # TTS + status

app = FastAPI(title="VA Backend", version="0.2.0")

# CORS for local dev (UI at Vite 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "*",  # dev convenience; tighten later if needed
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/voice")
def voice_status():
    """Report which TTS engine is configured/used."""
    return tts_status()


@app.post("/tts", response_class=FileResponse)
def tts(background_tasks: BackgroundTasks, text: str = Form(...)):
    """
    Text → Speech (WAV).
    Body: application/x-www-form-urlencoded with 'text' field.
    """
    try:
        wav_path = synth_to_wav(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Clean up the temp file after it's sent
    background_tasks.add_task(lambda p: os.path.exists(p) and os.remove(p), wav_path)
    return FileResponse(
        wav_path,
        media_type="audio/wav",
        filename="tts.wav",
        background=background_tasks,
    )


@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    """
    Speech (WAV/other) → Text.
    Upload a short audio file; backend will transcribe.
    """
    # Save upload to a temp path
    import tempfile, shutil
    suffix = os.path.splitext(file.filename or "")[-1] or ".wav"
    with tempfile.NamedTemporaryFile(prefix="stt_", suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        with file.file as fsrc, open(tmp_path, "wb") as fdst:
            shutil.copyfileobj(fsrc, fdst)

    try:
        text = transcribe_wav(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ASR failed: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return JSONResponse({"text": text})
