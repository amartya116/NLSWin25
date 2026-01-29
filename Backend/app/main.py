from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import whisper
import pyttsx3
import tempfile
import os

from .integration import process_text_input
from .NLG import generate_nlg

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Transcript", "X-Assistant-Text", "X-Execution-Result"]
)



# Load OpenAI Whisper Model
asr_model = whisper.load_model("base")


def run_tts(text: str, output_wav: str) -> None:
    """Convert text to speech using pyttsx3 with more natural voice"""
    try:
        engine = pyttsx3.init()

        # Set voice to a more natural one (female/male depends on installed voices)
        voices = engine.getProperty('voices')
        # Pick a female voice if available, else default
        voice = next((v for v in voices if 'female' in v.name.lower()), voices[0])
        engine.setProperty('voice', voice.id)

        # Adjust speech rate (default is ~200 wpm)
        engine.setProperty('rate', 170)

        # Adjust volume (0.0 to 1.0)
        engine.setProperty('volume', 1.0)

        engine.save_to_file(text, output_wav)
        engine.runAndWait()
        print(f"[TTS] Saved audio to: {output_wav} with voice '{voice.name}'")

    except Exception as e:
        raise RuntimeError(f"TTS failed: {e}")


@app.post("/speech2speech")
async def speech_to_speech(audio: UploadFile = File(...)):
    """
    Complete speech-to-speech pipeline:
    Audio Input → ASR (Whisper) → NLU → Intent Execution → NLG → TTS → Audio Output
    """
    if not audio.content_type or not audio.content_type.startswith(("audio/", "video/")):
        raise HTTPException(status_code=400, detail=f"Upload an audio file. Got: {audio.content_type}")

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, audio.filename or "input.bin")
        out_wav = os.path.join(tmpdir, "output_tts.wav")

        # Save uploaded audio
        data_bytes = await audio.read()
        with open(raw_path, "wb") as f:
            f.write(data_bytes)

        # ASR: Speech to Text using OpenAI Whisper
        try:
            result = asr_model.transcribe(
                raw_path,  # Whisper handles webm/ogg directly
                language="en",
                fp16=False
            )
            transcript = result["text"].strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ASR (Whisper) failed: {e}")

        if not transcript:
            raise HTTPException(status_code=422, detail="Could not transcribe speech (empty result).")

        print(f"[ASR/Whisper] Transcribed: {transcript}")

        # NLU + Intent Execution via integration.py
        try:
            dialogue_state = {}
            execution_result = process_text_input(transcript, dialogue_state)
            print(f"[Integration] Execution Result: {execution_result}")

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Intent processing failed: {e}")

        # NLG: Generate natural language response
        try:
            nlg_input = {
                "intent": "response_generation",
                "entities": {},
                "tool_results": {
                    "execution_result": execution_result
                },
                "conversation_state": {
                    "locale": "en",
                    "timezone": "Europe/Berlin",
                    "pending_slots": []
                }
            }
            
            nlg_result = await generate_nlg(nlg_input, model="llama3.2")
            response_text = nlg_result.text
            print(f"[NLG] Generated Response: {response_text}")
        except Exception as e:
            # Fallback: use raw execution result if NLG fails
            response_text = execution_result
            print(f"[NLG] Failed, using fallback: {e}")

        # TTS: Text to Speech using pyttsx3
        try:
            run_tts(response_text, out_wav)
            #checking if audio output file actually exists
            print("--------TTS file exists:", os.path.exists(out_wav), "size:", os.path.getsize(out_wav) if os.path.exists(out_wav) else None)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

        if not os.path.exists(out_wav) or os.path.getsize(out_wav) == 0:
            raise HTTPException(status_code=500, detail="TTS produced no output.")

        # Return audio response with metadata
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


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "asr_model": "OpenAI Whisper (base)",
        "tts_engine": "pyttsx3"
    }