from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import json
import os
import httpx

DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


@dataclass
class NlgResult:
    text: str # to be sent to TTS / spoken output
    follow_up_question: Optional[str] =None # clarification question if one of the info is missing
    to_confirm: bool = False # ask for confirmation if true


# ---- helper function ---

# Takes the input from nlg input object and returns prompt
def _prompt_builder(nlg_input: Dict[str, Any]) -> str:
    tool_results = nlg_input.get("tool_results", {})
    execution_result = tool_results.get("execution_result", "")
    
    return f"""
    You are an NLG component for a voice assistant.
    Return ONLY valid JSON with exactly these keys:
    {{
      "text": string,
      "follow_up_question": string|null,
      "to_confirm": boolean
    }}
    
    Rules:
    - Convert the execution result into natural, conversational speech
    - Keep responses short (1-2 sentences) and speakable
    - If the result contains structured data (like weather forecasts), summarize it naturally
    - If information is missing, ask ONE short follow-up question
    
    Execution Result:
    {execution_result}
    
    Convert this into natural speech output.
    """.strip()

### the nlg_input just seperates instriction from our data
## so we insert the json input and keep non englisch characters readable

#--------- ERROOOOOR MSG -------------------
class OllamaNlgError(RuntimeError):
    """Raised when Ollama is unreachable or returns invalid output."""


def _fallback(nlg_input: Dict[str, Any]) -> NlgResult:
    """
    Deterministic fallback so your assistant always answers,
    even if the model fails.
    """
    intent = (nlg_input or {}).get("intent", "unknown")
    entities = (nlg_input or {}).get("entities", {}) or {}
    tool_results = (nlg_input or {}).get("tool_results", {}) or {}

    # Minimal weather fallback based on weather API response
    if intent.startswith("weather") and "weather_api" in tool_results:
        w = tool_results["weather_api"]
        place = w.get("place") or entities.get("place") or "that location"
        forecast = w.get("forecast") or []
        if forecast:
            first = forecast[0]
            day = first.get("day", "that day")
            t = first.get("temperature", {}) or {}
            mn = t.get("min")
            mx = t.get("max")
            cond = first.get("weather", "unknown weather")
            parts = [f"In {place} on {day}, expect {cond}."]
            if mn is not None and mx is not None:
                parts.append(f"Temperatures range from {mn} to {mx} degrees.")
            return NlgResult(text=" ".join(parts))

    # Generic fallback
    return NlgResult( text="Sorry, I couldn't generate a response right now. Please try again." )

def parse_nlg_output(raw: str) -> NlgResult:
    """
    Parse and validate Ollama JSON output.
    Raises OllamaNlgError if invalid.
    """
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OllamaNlgError(f"Model did not return valid JSON: {e}")

    if not isinstance(obj, dict):
        raise OllamaNlgError("Model output JSON is not an object")

    # Required: text
    text = obj.get("text")
    if not isinstance(text, str) or not text.strip():
        raise OllamaNlgError("Missing/invalid 'text' field")


    # validation
    follow = obj.get("follow_up_question", None)
    if follow is not None and not isinstance(follow, str):
        raise OllamaNlgError("Invalid 'follow_up_question' field")

    to_confirm = obj.get("to_confirm", False)
    if not isinstance(to_confirm, bool):
        raise OllamaNlgError("Invalid 'to_confirm' field")

    return NlgResult(
        text=text.strip(),
        follow_up_question=follow.strip() if isinstance(follow, str) else None,
        to_confirm=to_confirm,
    )


#---------------- THE function that does it all----------

async def generate_nlg(
    nlg_input: Dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,

    ollama_url: str = DEFAULT_OLLAMA_URL,
    timeout_s: float = 20.0, #API only waits for 20s max
    fallback_on_error: bool = True,
) -> NlgResult:
    """
    - nlg_input: dict containing intent/entities/tool_results/conversation_state
    - returns: NlgResult
    """
    prompt = _prompt_builder(nlg_input) # this is to convert the jsonn to a full prompt (instruction + the data)

    body = {
        "model": model,
        "prompt": prompt,
        "stream": False, # for one full sentence
        "format": "json",  # JSON-only output
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(ollama_url, json=body)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        if fallback_on_error:
            return _fallback(nlg_input)
        raise OllamaNlgError(f"Ollama request failed: {e}") from e

    raw = (data.get("response") or "").strip()
    if not raw:
        if fallback_on_error:
            return _fallback(nlg_input)
        raise OllamaNlgError("Empty response from Ollama")

    try:
        return parse_nlg_output(raw)
    except OllamaNlgError:
        if fallback_on_error:
            return _fallback(nlg_input)
        raise

