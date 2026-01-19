from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from faster_whisper import WhisperModel
import subprocess
import tempfile
import os
from fastapi.middleware.cors import CORSMiddleware

from app.NLG import generate_nlg

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Transcript", "X-Assistant-Text"],
)



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

        data_bytes = await audio.read()
        with open(raw_path, "wb") as f:
            f.write(data_bytes)

        try:
            convert_to_wav16k_mono(raw_path, wav_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"ffmpeg conversion failed: {e}")

        try:
            segments, _info = asr_model.transcribe(wav_path, language="en")
            transcript = "".join(seg.text for seg in segments).strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ASR failed: {e}")

        if not transcript:
            raise HTTPException(status_code=422, detail="Could not transcribe speech (empty result).")

        # ---------------------------------------------------------
        # NLG with json example from lecture (until we put the guys's code)
        # ---------------------------------------------------------
        WEATHER_API_RES = {
            "place": "Marburg",
            "forecast": [
                {"day": "thursday", "temperature": {"min": 7, "max": 15}, "weather": "few clouds"},
                {"day": "friday", "temperature": {"min": 6, "max": 14}, "weather": "rain"},
                {"day": "saturday", "temperature": {"min": 5, "max": 11}, "weather": "clear sky"}
            ]
        }

        nlg_input = {
            "intent": "weather_forecast",
            "entities": {
                "place": WEATHER_API_RES["place"],
                "day": WEATHER_API_RES["day"],
            },
            "tool_results": {
                "weather_api": WEATHER_API_RES
            },
            "conversation_state": {
                "locale": "en",
                "timezone": "Europe/Berlin",
                "pending_slots": []
            }
        }

    #------------------------------------------------------------
        # up up
    #------------------------------------------------------------

        try:
            nlg_result = await generate_nlg(nlg_input, model="llama3.2")
            response_text = nlg_result.text
        except Exception:
            # extra safety: if anything weird happens, fallback to transcript
            response_text = transcript

        # TTS should speak the response, not the transcript
        try:
            run_piper_tts(response_text, out_wav)
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
                "X-Transcript": transcript,
                "X-Assistant-Text": response_text,
                "Content-Disposition": 'attachment; filename="speech_output.wav"',
            },
        )


