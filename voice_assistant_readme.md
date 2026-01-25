# Voice Assistant - Speech-to-Speech System

A complete voice-powered assistant that processes spoken queries, understands intents, executes actions, and responds with natural speech.

## System Architecture

```
Audio Input → ASR (Whisper) → NLU (Ollama) → Intent Execution → NLG (Ollama) → TTS (pyttsx3) → Audio Output
```

### Pipeline Components

1. **ASR (Automatic Speech Recognition)**: OpenAI Whisper converts speech to text
2. **NLU (Natural Language Understanding)**: Ollama's Llama3 model extracts user intent
3. **Intent Execution**: Calls appropriate APIs (weather, calendar)
4. **NLG (Natural Language Generation)**: Ollama's Llama3.2 generates natural responses
5. **TTS (Text-to-Speech)**: pyttsx3 converts text response to speech
6. **MongoDB**: Stores conversation history

## Features

- **Weather Queries**: Get weather forecasts for any location
- **Calendar Management**: Create, read, update, and delete appointments
- **Natural Conversations**: Understands context and generates human-like responses
- **Speech Interface**: Complete audio-to-audio interaction
- **Conversation History**: All interactions saved to MongoDB

## Project Structure

```
NLSWin25-Rim/
├── Backend/
│   └── app/
│       ├── main.py              # FastAPI server, ASR & TTS
│       ├── integration.py       # NLU & intent execution
│       ├── NLG.py              # Natural language generation
│       ├── responserev.py       # API calls (weather, calendar)
│       └── tts_local.py        # Local TTS utilities
└── Frontend/
    └── index.html              # Web interface
```

## Prerequisites

### Required Software

1. **Python 3.10+**
2. **FFmpeg** (required by Whisper for audio processing)
3. **MongoDB** (for conversation storage)
4. **Ollama** (for LLM-based NLU and NLG)

### Python Dependencies

```bash
pip install fastapi uvicorn python-multipart
pip install openai-whisper
pip install pyttsx3
pip install ollama
pip install pymongo
pip install httpx
```

## Installation Guide

### Step 1: Install FFmpeg

**Windows:**
1. Download from: https://www.gyan.dev/ffmpeg/builds/
2. Download `ffmpeg-release-essentials.zip`
3. Extract and move to `C:\ffmpeg`
4. Add to PATH:
   - Open PowerShell as Administrator
   - Run: `[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\ffmpeg\bin", "Machine")`
5. Verify: `ffmpeg -version`

**Mac:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

### Step 2: Install MongoDB

Download and install from: https://www.mongodb.com/try/download/community

Start MongoDB:
```bash
mongod
```

### Step 3: Install Ollama

Download from: https://ollama.ai

Pull required models:
```bash
ollama pull llama3
ollama pull llama3.2
```

Start Ollama:
```bash
ollama serve
```

### Step 4: Install Python Dependencies

```bash
cd Backend/app
pip install -r requirements.txt
```

Or install manually:
```bash
pip install fastapi uvicorn python-multipart openai-whisper pyttsx3 ollama pymongo httpx
```

## Running the Application

### Step 1: Start MongoDB

```bash
mongod
```

### Step 2: Start Ollama

```bash
ollama serve
```

### Step 3: Start the Backend Server

```bash
cd Backend/app
uvicorn main:app --reload
```

The server will start at: `http://127.0.0.1:8000`

### Step 4: Open the Frontend

**Option A: Direct File**
- Open `Frontend/index.html` in your browser

**Option B: Local Server (recommended)**
```bash
cd Frontend
python -m http.server 3000
```
Then open: `http://localhost:3000/index.html`

## Usage

1. Click the **microphone button** to start recording
2. Speak your query (e.g., "What's the weather in Berlin?")
3. Click the microphone again to stop recording
4. The system will:
   - Transcribe your speech
   - Understand your intent
   - Execute the appropriate action
   - Generate a natural response
   - Speak the response back to you
5. Click the **speaker button** to replay the response

## Supported Intents

### Weather Queries
- "What's the weather in [location]?"
- "Tell me the weather for [location] on [day]"

### Appointments
- "Create an appointment for [title] at [time]"
- "Show all my appointments"
- "Delete appointment [id]"
- "Update appointment [id]"

## API Endpoints

### POST /speech2speech
Complete speech-to-speech pipeline

**Request:**
- Form data with audio file

**Response:**
- WAV audio file
- Headers:
  - `X-Transcript`: The recognized text
  - `X-Assistant-Text`: The generated response text

### GET /health
Health check endpoint

**Response:**
```json
{
  "status": "healthy",
  "asr_model": "OpenAI Whisper (base)",
  "tts_engine": "pyttsx3"
}
```

## Configuration

### Whisper Model Size
In `main.py`, change model size:
```python
asr_model = whisper.load_model("base")  # Options: tiny, base, small, medium, large
```

### Ollama Models
In `integration.py` and `main.py`:
```python
MODEL = "llama3"        # For NLU
model="llama3.2"        # For NLG
```

### MongoDB Connection
In `integration.py`:
```python
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "nls"
```

## Troubleshooting

### FFmpeg Not Found
**Error:** `The system cannot find the file specified`

**Solution:**
1. Verify FFmpeg is installed: `ffmpeg -version`
2. If not found, reinstall and add to PATH
3. Restart terminal and server

### Ollama Connection Failed
**Error:** `Ollama request failed`

**Solution:**
1. Check Ollama is running: `ollama list`
2. Start Ollama: `ollama serve`
3. Verify models are installed: `ollama pull llama3 && ollama pull llama3.2`

### MongoDB Connection Failed
**Error:** `MongoDB connection failed`

**Solution:**
1. Start MongoDB: `mongod`
2. Check connection string in `integration.py`

### CORS Errors
**Error:** `CORS policy: No 'Access-Control-Allow-Origin' header`

**Solution:**
- Serve frontend via HTTP server, not file://
- Or ensure main.py has CORS middleware (already configured)

### pyttsx3 TTS Not Working
**Error:** `TTS failed`

**Solution:**
- Windows: Should work by default
- Linux: `sudo apt install espeak`
- Mac: Should work by default

## MongoDB Database Structure

### Collection: conversations

```json
{
  "_id": ObjectId,
  "query": "What's the weather in Berlin?",
  "response": "Weather forecast for Berlin: ...",
  "timestamp": ISODate
}
```

## Performance Notes

- **First request is slow**: Whisper loads model into memory (~1-2 seconds)
- **Subsequent requests**: Fast (~0.5-1 second for transcription)
- **NLG with Ollama**: Depends on model size and hardware
- **Recommended**: Use GPU for faster Whisper and Ollama inference

## Future Improvements

- [ ] Add session-based dialogue state management
- [ ] Support multiple languages
- [ ] Implement voice activity detection (VAD)
- [ ] Add streaming responses
- [ ] Deploy with Docker
- [ ] Add authentication
- [ ] Improve NLG prompts for better responses
- [ ] Add more intent types (emails, reminders, etc.)

## License

MIT License

## Contributors

Built as part of the Natural Language Systems course (Winter 2025)

## Support

For issues or questions, please refer to the course materials or contact the development team.
