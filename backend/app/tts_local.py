import os, sys, shutil, tempfile, subprocess
LAST_TTS_ENGINE = None
from typing import Dict, Any


# Will be filled on each synthesis so we can inspect from /voice
LAST_TTS_ENGINE: str | None = None


def _has(cmd: str) -> bool:
    """Return True if an executable is on PATH."""
    return shutil.which(cmd) is not None


def _piper_bin() -> str:
    """
    Get Piper executable path.
    Prefer env PIPER_BIN, else rely on PATH ('piper' or 'piper.exe').
    """
    val = (os.getenv("PIPER_BIN") or "").strip()
    return val if val else "piper"


def _piper_voice_files(voice_dir: str) -> tuple[str | None, str | None]:
    """Return (onnx_path, json_path) if found in a voice dir, else (None, None)."""
    if not voice_dir or not os.path.isdir(voice_dir):
        return (None, None)
    files = os.listdir(voice_dir)
    onnx = next((f for f in files if f.endswith(".onnx")), None)
    cfg = next((f for f in files if f.endswith(".json")), None)
    if not onnx or not cfg:
        return (None, None)
    return (os.path.join(voice_dir, onnx), os.path.join(voice_dir, cfg))


def synth_to_wav(text: str) -> str:
    """
    Synthesize speech to a temporary WAV file and return its path.

    Engine selection (in order) depends on TTS_ENGINE env:
      - "piper": Piper → eSpeak NG → Windows SAPI
      - "espeak": eSpeak NG → Piper → Windows SAPI
      - "sapi": Windows SAPI → eSpeak NG → Piper
      - "auto" (default): Piper → eSpeak NG → Windows SAPI

    Environment variables:
      - TTS_ENGINE = auto|piper|espeak|sapi
      - PIPER_BIN = path to piper executable (optional if on PATH)
      - PIPER_VOICE_DIR = folder containing <voice>.onnx and <voice>.onnx.json
      - PIPER_ARGS = extra Piper CLI args (e.g. "--length_scale 1.15 --noise_scale 0.5 --noise_w 0.7")
    """
    global LAST_TTS_ENGINE

    if not isinstance(text, str) or not text.strip():
        raise ValueError("Text is empty.")

    out = tempfile.NamedTemporaryFile(prefix="tts_", suffix=".wav", delete=False).name
    engine = (os.getenv("TTS_ENGINE") or "auto").lower().strip()

    def try_piper() -> bool:
        exe = _piper_bin()
        # Must have a valid voice dir with both files
        voice_dir = (os.getenv("PIPER_VOICE_DIR") or "").strip()
        onnx, cfg = _piper_voice_files(voice_dir)
        if not(onnx and cfg):
            return False

        # Piper executable must exist or be on PATH
        if exe != "piper" and not os.path.isfile(exe):
            return False
        if exe == "piper" and not _has("piper"):
            return False

        # Extra args (prosody etc.)
        args = shlex.split(os.getenv("PIPER_ARGS") or "")

        subprocess.run(
            [exe, "-m", onnx, "-c", cfg, "-f", out, "-q", *args],
            input=text.encode("utf-8"),
            check=True,
        )
        LAST_TTS_ENGINE = "piper"
        print("TTS: piper", file=sys.stderr)
        return True

    def try_espeak() -> bool:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            return False
        # -w writes WAV directly
        subprocess.run([exe, "-w", out, text], check=True)
        LAST_TTS_ENGINE = "espeak-ng"
        print("TTS: espeak-ng", file=sys.stderr)
        return True

    def try_sapi() -> bool:
        if os.name != "nt":
            return False
        # Windows built-in SAPI via PowerShell
        ps = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile('%OUT%')
$s.Speak([Console]::In.ReadToEnd())
$s.Dispose()
"""
        ps = ps.replace('%OUT%', out.replace("'", "''"))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       input=text.encode("utf-8"), check=True)
        LAST_TTS_ENGINE = "sapi"
        print("TTS: sapi", file=sys.stderr)
        return True

    order_map = {
        "piper":  ("piper", "espeak", "sapi"),
        "espeak": ("espeak", "piper", "sapi"),
        "sapi":   ("sapi", "espeak", "piper"),
        "auto":   ("piper", "espeak", "sapi"),
    }
    order = order_map.get(engine, order_map["auto"])

    for choice in order:
        if choice == "piper" and try_piper():
            return out
        if choice == "espeak" and try_espeak():
            return out
        if choice == "sapi" and try_sapi():
            return out

    # If we got here, nothing worked.
    raise RuntimeError(
        "No TTS engine available. Install Piper (binary + voice), or eSpeak NG, "
        "or run on Windows for SAPI fallback."
    )


def tts_status() -> Dict[str, Any]:
    """Expose current TTS environment and last engine used."""
    vdir = os.getenv("PIPER_VOICE_DIR", "")
    onnx_ok = False
    json_ok = False
    if os.path.isdir(vdir):
        try:
            files = os.listdir(vdir)
            onnx_ok = any(f.endswith(".onnx") for f in files)
            json_ok = any(f.endswith(".json") for f in files)
        except Exception:
            pass
    return {
        "env_engine": os.getenv("TTS_ENGINE", "auto"),
        "piper_bin": os.getenv("PIPER_BIN", "piper"),
        "piper_voice_dir": vdir,
        "piper_ready": bool(vdir and os.path.isdir(vdir) and onnx_ok and json_ok),
        "piper_args": os.getenv("PIPER_ARGS", ""),
        "last_engine": LAST_TTS_ENGINE,
    }
# ---------- status helper exposed via /voice ----------
def tts_status():
    """Return current TTS env + last engine used."""
    vdir = os.getenv("PIPER_VOICE_DIR", "")
    piper_ready = False
    try:
        if os.path.isdir(vdir):
            files = os.listdir(vdir)
            onnx_ok = any(f.endswith(".onnx") for f in files)
            json_ok = any(f.endswith(".json") for f in files)
            piper_ready = onnx_ok and json_ok
    except Exception:
        piper_ready = False

    return {
        "env_engine": os.getenv("TTS_ENGINE", "auto"),
        "piper_bin": os.getenv("PIPER_BIN", "piper"),
        "piper_voice_dir": vdir,
        "piper_ready": piper_ready,
        "piper_args": os.getenv("PIPER_ARGS", ""),
        "last_engine": LAST_TTS_ENGINE,
    }
