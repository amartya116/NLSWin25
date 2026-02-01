from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import json
import os
import httpx


DEFAULT_OLLAMA_URL = (
    os.getenv("OLLAMA_URL")
    or os.getenv("OLLAMA_HOST")
    or "http://host.docker.internal:11434"
)
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


@dataclass
class NlgResult:
    text: str
    follow_up_question: Optional[str] = None
    to_confirm: bool = False


class OllamaNlgError(RuntimeError):
    """Raised when Ollama is unreachable or returns invalid output."""


def _prompt_builder(nlg_input: Dict[str, Any]) -> str:
    tool_results = nlg_input.get("tool_results", {}) or {}
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
- if execution_result is one of:
  - MISSING_TITLE_READ_APPOINTMENT
  - MISSING_TITLE_UPDATE_APPOINTMENT
  - MISSING_TITLE_DELETE_APPOINTMENT
set "follow_up_question" and keep "text" very short (e.g., "Sure.")
- if MISSING_FIELDS_CREATE_APPOINTMENT → ask: “What’s the appointment title and what time should it start?”

Execution Result:
{execution_result}

Convert this into natural speech output.
""".strip()


def _fallback(nlg_input: Dict[str, Any]) -> NlgResult:
    tool_results = (nlg_input or {}).get("tool_results", {}) or {}
    execution_result = tool_results.get("execution_result", "")

    if execution_result == "MISSING_TITLE_READ_APPOINTMENT":
        return NlgResult(text="Sure.", follow_up_question="What’s the appointment title?")
    if execution_result == "MISSING_TITLE_UPDATE_APPOINTMENT":
        return NlgResult(text="Okay.", follow_up_question="Which appointment title should I update?")
    if execution_result == "MISSING_TITLE_DELETE_APPOINTMENT":
        return NlgResult(text="Alright.", follow_up_question="Which appointment title should I delete?")

    if isinstance(execution_result, str) and execution_result.strip():
        return NlgResult(text=execution_result.strip())

    return NlgResult(text="Sorry, I couldn't generate a response right now. Please try again.")


def parse_nlg_output(raw: str) -> NlgResult:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OllamaNlgError(f"Model did not return valid JSON: {e}")

    if not isinstance(obj, dict):
        raise OllamaNlgError("Model output JSON is not an object")

    text = obj.get("text")
    if not isinstance(text, str) or not text.strip():
        raise OllamaNlgError("Missing/invalid 'text' field")

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


async def generate_nlg(
    nlg_input: Dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    timeout_s: float = 20.0,
    fallback_on_error: bool = True,
) -> NlgResult:
    prompt = _prompt_builder(nlg_input)

    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    endpoint = ollama_url.rstrip("/")
    if not endpoint.endswith("/api/generate"):
        endpoint = endpoint + "/api/generate"

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(endpoint, json=body)
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
        res= parse_nlg_output(raw)
    except OllamaNlgError:
        if fallback_on_error:
            return _fallback(nlg_input)
        raise

    tool_results= (nlg_input or {}).get("tool_results", {}) or {}
    execution_result=tool_results.get("execution_result", "")

    missing_title = {
        "MISSING_TITLE_READ_APPOINTMENT",
        "MISSING_TITLE_UPDATE_APPOINTMENT",
        "MISSING_TITLE_DELETE_APPOINTMENT",
    }
    print(f"thios is exec result ----- +  {execution_result}")
    if execution_result in missing_title and not res.follow_up_question:

            return _fallback(nlg_input)

    return res
