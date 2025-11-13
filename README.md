# Local Voice Assistant — Milestone 1 (Working ASR + TTS)

This repo contains a **local-first** voice assistant:
- **Backend** (FastAPI, Python): ASR with CPU **Whisper** (`faster-whisper`), TTS with **Windows SAPI** by default (works out‑of‑the‑box on Windows). Optional cross‑platform TTS with **Piper** or **eSpeak NG**.
- **Frontend** (React + Vite): minimal UI to ping the backend, send audio, and play TTS.

>  No cloud models. All processing happens locally.  
>  Tested target: **Milestone 1** (ASR + TTS working).

---

## Repository Layout

```
/client     # React (Vite) app (UI)  -> http://localhost:5173
/backend    # FastAPI app (API)      -> http://localhost:8000
```

> If your backend currently lives outside the repo (e.g., `C:\va-backend`), move or copy it into this repo as `/backend` so teammates can run it easily.

---

## Prerequisites

- **Windows** (primary dev):  
  - Python **3.11+** (from https://www.python.org)  
  - Node.js **LTS (v20+)** (from https://nodejs.org)  
  - *(Optional)* FFmpeg if you plan to handle odd audio formats
- **macOS/Linux** (teammates): Python 3.11+, Node.js LTS
- *(Optional)* For cross‑platform TTS:
  - **Piper** binary + voice files (e.g., `en_US-amy-high`)
  - **eSpeak NG** (`brew install espeak` on macOS)

> **Windows defaults to SAPI** TTS so you don’t need extra installs. macOS/Linux users should use **Piper** or **eSpeak NG**.

---

## 1) Backend — FastAPI (Windows steps)

From the repo root in **PowerShell**:

```powershell
cd backend
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
# (If requirements.txt is missing, install these manually:)
# pip install fastapi "uvicorn[standard]" python-multipart requests soundfile faster-whisper

# Use Windows built-in TTS for zero setup
$env:TTS_ENGINE = "sapi"

# Run the API
.\.venv\Scripts\python.exe -m uvicorn app.web:app --host 127.0.0.1 --port 8000 --reload
```

Quick checks (open in browser):
- **Health** → http://localhost:8000/health  → should return `{ "ok": true }`
- **Docs (Swagger)** → http://localhost:8000/docs

### API (Milestone 1)

- `GET /health` → `{ ok: true }`
- `GET /voice` → Shows current TTS config and **last engine** used.
- `POST /tts` (form field `text`) → returns a WAV file (audio/wav).
- `POST /stt` (file upload) → returns `{ "text": "<transcript>" }`.

> ASR uses **faster‑whisper** (CPU). TTS defaults to **SAPI** on Windows.


### TTS options

**Default (Windows SAPI):**  
Nothing to install.
```powershell
$env:TTS_ENGINE = "sapi"
```

**Piper (cross‑platform, nicer voices):**  
Install Piper + download a voice (folder must contain **both** `.onnx` and `.onnx.json` files):
```powershell
$env:TTS_ENGINE      = "piper"
$env:PIPER_BIN       = "C:\path\to\piper.exe"                # full path to piper
$env:PIPER_VOICE_DIR = "C:\path\to\voices\en_US-amy-high"    # folder with .onnx + .json
# (optional prosody tuning)
$env:PIPER_ARGS      = "--length_scale 1.05 --noise_scale 0.35 --noise_w 0.5"
```

**eSpeak NG (simple on mac/Linux):**
```bash
export TTS_ENGINE=espeak
```

> Do **not** commit Piper voice files to Git—they are large. Add the voice folder to `.gitignore`.

---

## 2) Frontend — React + Vite

Open a **second** terminal (keep backend running).

```powershell
cd client
npm install
npm run dev
```
Open: **http://localhost:5173**

If the UI needs the backend URL, set it to: `http://localhost:8000`.

---

## Typical Dev Workflow

- Terminal A → **Backend** (Uvicorn)  
  ```powershell
  cd backend
  .\.venv\Scripts\Activate.ps1
  $env:TTS_ENGINE="sapi"
  .\.venv\Scripts\python.exe -m uvicorn app.web:app --host 127.0.0.1 --port 8000 --reload
  ```

- Terminal B → **Frontend** (Vite)  
  ```powershell
  cd client
  npm run dev
  ```

- Test end-to-end:
  - UI at http://localhost:5173
  - Swagger at http://localhost:8000/docs
  - Check which TTS ran: call `/tts`, then open `/voice` and confirm `"last_engine"` is `"sapi"` / `"piper"` / `"espeak-ng"`

---

## Troubleshooting

- **“Venv not active”**: prompt should show `(.venv)`. If not:
  ```powershell
  cd backend
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\Activate.ps1
  ```
- **UI can’t reach backend**: ensure `http://localhost:8000/health` works and the UI points to `http://localhost:8000` (no https).
- **Piper not used / robotic sound**: fall back to SAPI on Windows (`$env:TTS_ENGINE="sapi"`) or verify Piper paths and voices; `/voice` must show `"piper_ready": true` and `"last_engine": "piper"` after a `/tts` call.

---

## Milestones

- **Milestone 1** — ASR (Whisper) + TTS (SAPI/Piper/eSpeak) + UI connectivity
- **Milestone 2** — Weather + Calendar API wrappers (local only)
- **Milestone 3** — Full voice assistant loop (keeps conversation history; references previous turn)
- **Milestone 4** — Docker image + evaluation report

---

## .gitignore (recommended)

```
# Python
backend/.venv/
backend/**/__pycache__/
backend/*.pyc

# Piper voices (large)
backend/piper_voices/

# Node
client/node_modules/
client/dist/

# Env / OS
*.env
.DS_Store
Thumbs.db
```
