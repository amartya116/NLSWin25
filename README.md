## Audio Assist

Audio input (microphone or file) → Whisper ASR → Piper TTS → audio output (WAV)
Backend is built with FastAPI.
Frontend is plain HTML / CSS / JavaScript using browser microphone recording type shii

MUST 
  Install requirEments.txt

### how to run 
cd backend/app
uvicorn main:app --reload

### In another terminal
cd frontend
python -m http.server 5500

### then launch localhost


### NLG is working to test :

python -m  Backend.test.test_nlg


### might need to add this in case of errors 

cd your_path/NLSWin25 
touch backend/__init__.py backend/app/__init__.py backend/test/__init__.py
