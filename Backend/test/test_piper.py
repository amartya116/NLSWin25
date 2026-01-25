from piper import PiperVoice
import wave

voice = PiperVoice.load(
    "models/piper/en_US-lessac-medium.onnx",
    config_path="models/piper/en_US-lessac-medium.onnx.json"
)

with wave.open("test.wav", "wb") as wf:
    voice.synthesize_wav("Hello, this is a test.", wf)

print("test.wav created")
