from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from faster_whisper import WhisperModel
import subprocess
import tempfile
import os
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()


#HTTP bullshit for ui
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Transcript"],  # so frontend can read it
)
# --------------------------------------------------- 



asr_model = WhisperModel("small", device="cpu", compute_type="int8")

PIPER_BIN = "piper"
PIPER_VOICE_ONNX = "models/piper/en_US-lessac-medium.onnx"
PIPER_VOICE_JSON = "models/piper/en_US-lessac-medium.onnx.json"


def convert_to_wav16k_mono(input_path: str, output_path: str) -> None:
    cmd = ["ffmpeg", "-y", "-i", input_path, "-ac", "1", "-ar", "16000", "-f", "wav", output_path]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", errors="ignore"))


def run_piper_tts(text: str, output_wav: str) -> None:
    cmd = [
        PIPER_BIN,
        "--model", PIPER_VOICE_ONNX,
        "--config", PIPER_VOICE_JSON,
        "--output_file", output_wav
    ]
    r = subprocess.run(cmd, input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", errors="ignore"))


@app.post("/speech2speech")
async def speech_to_speech(audio: UploadFile = File(...)):
    if not audio.content_type or not audio.content_type.startswith(("audio/", "video/")):
        raise HTTPException(status_code=400, detail=f"Upload an audio file. Got: {audio.content_type}")

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, audio.filename or "input.bin")
        wav_path = os.path.join(tmpdir, "input_16k.wav")
        out_wav = os.path.join(tmpdir, "output_tts.wav")

        data = await audio.read()
        with open(raw_path, "wb") as f:
            f.write(data)

        try:
            convert_to_wav16k_mono(raw_path, wav_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"ffmpeg conversion failed: {e}")

        try:
            # Perform ASR
            segments, _info = asr_model.transcribe(wav_path, language="en")
            text = "".join(seg.text for seg in segments).strip()

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ASR failed: {e}")

        if not text:
            raise HTTPException(status_code=422, detail="Could not transcribe speech (empty result).")

        try:
            run_piper_tts(text, out_wav)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

        if not os.path.exists(out_wav) or os.path.getsize(out_wav) == 0:
            raise HTTPException(status_code=500, detail="TTS produced no output wav file.")

        with open(out_wav, "rb") as f:
            audio_bytes = f.read()

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "X-Transcript": text,
                "Content-Disposition": 'attachment; filename="speech_output.wav"',
            },
        )


