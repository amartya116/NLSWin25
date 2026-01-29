from __future__ import annotations

import datetime
import json
import os
import re

import ollama
from pymongo import MongoClient

from .responserev import (
    calendercreate, calendergetall, calendergetbyid, calenderupdate, calenderdelete, calendergetbytitle,
    weather_get, weather_get_by_day
)


MONGO_URI = os.getenv("MONGO_URI", "mongodb://host.docker.internal:27017/")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["nls"]
conversations = db["conversations"]

# IMPORTANT: don't override OLLAMA_HOST from OLLAMA_URL.
# Use OLLAMA_HOST for the ollama python client.
os.environ["OLLAMA_HOST"] = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

_WEEKDAYS = {"monday","tuesday","wednesday","thursday","friday","saturday","sunday"}

def extract_weekday_from_text(text: str) -> str | None:
    t = (text or "").lower()
    for d in _WEEKDAYS:
        if re.search(rf"\b{d}\b", t):
            return d
    return None


def user_mentioned_place(text: str) -> bool:
    # Basic but effective: detects "in Berlin", "in Frankfurt am Main", etc.
    return bool(re.search(r"\bin\s+[A-Za-zÄÖÜäöüß]", text or "", re.IGNORECASE))


def _now_context():
    x = datetime.datetime.now()
    v = x.strftime("%A")
    return x, v


x, v = _now_context()

SYSTEM_PROMPT = f"""
You are a Natural Language Understanding (NLU) component for a voice assistant.
Your task: Identify the user's intent from their utterance.

Allowed intents:
- GET_WEATHER
- GET_WEATHER_BY_DAY
- CREATE_APPOINTMENT
- READ_APPOINTMENT_ALL
- READ_APPOINTMENT_BY_ID
- DELETE_APPOINTMENT
- UPDATE_APPOINTMENT
- DELETE_APPOINTMENT_ALL
- DELETE_LAST_APPOINTMENT

Rules:
- Output format: INTENT;PARAM1;PARAM2;...
- Today's day is {v}
- The date and time is {x} and every appointment should be 60 min unless explicitly stated
- For weather queries: output MUST be one of:
  - GET_WEATHER;Berlin
  - GET_WEATHER_BY_DAY;Berlin;Saturday
- IF ASKED ABOUT WEATHER make sure to mention Actual Temperatures in your response.
- IMPORTANT: Do NOT output key/value pairs like LOCATION="..." or DAY="...".
- IMPORTANT: Day must be a weekday word only (Monday...Sunday), no quotes.
- For CREATE_APPOINTMENT: CREATE_APPOINTMENT;{{"title":"...","description":"...","start_time":"...","end_time":"...","location":"..."}} and make sure to mention the title or location of the appointment in your response
- For UPDATE_APPOINTMENT: UPDATE_APPOINTMENT;ID_OR_TITLE;{{"title":"...","description":"...","start_time":"...","end_time":"...","location":"..."}}
  When UPDATING, you MUST also update description and MUST update dates/location if specified by the user.
- For READ_APPOINTMENT_BY_ID: READ_APPOINTMENT_BY_ID;ID
- For READ_APPOINTMENT_ALL: READ_APPOINTMENT_ALL
- For DELETE_APPOINTMENT: DELETE_APPOINTMENT;ID_OR_TITLE
- For DELETE_APPOINTMENT_ALL: DELETE_APPOINTMENT_ALL
- For DELETE_LAST_APPOINTMENT: DELETE_LAST_APPOINTMENT
- If the user does NOT mention a location, do NOT guess one. Leave it out.
- Do NOT include explanations, ONLY output the intent line
- Ensure JSON is valid and on a single line (when used)
- 
""".strip()


def nlu_parse(user_utterance, dialogue_state=None):
    if dialogue_state is None:
        dialogue_state = {}

    context = ""
    if dialogue_state:
        context = f"Context: {', '.join(f'{k}={v}' for k, v in dialogue_state.items())}\n"

    prompt = f"""{SYSTEM_PROMPT}

{context}
User utterance: "{user_utterance}"

Intent:"""

    response = ollama.generate(model=MODEL, prompt=prompt)
    return (response.get("response") or "").strip()


def _pick_last_event_id(events):
    if not events or not isinstance(events, list):
        return None

    last = events[-1]
    if isinstance(last, dict):
        cand = last.get("id") or last.get("eventid")
        if isinstance(cand, int):
            return cand
        if isinstance(cand, str) and cand.isdigit():
            return int(cand)

    ids = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        cand = ev.get("id") or ev.get("eventid")
        if isinstance(cand, int):
            ids.append(cand)
        elif isinstance(cand, str) and cand.isdigit():
            ids.append(int(cand))

    return max(ids) if ids else None


def parse_intent_response(intent_string: str):
    intent_string = (intent_string or "").strip()
    first_line = intent_string.splitlines()[0].strip()

    raw_parts = [p.strip() for p in first_line.split(";")]
    parts = [p for p in raw_parts if p != ""]

    result = {"intent": parts[0] if parts else "", "params": {}}
    intent = result["intent"]

    # ---- Weather (robust: positional + key/value tolerant) ----
    if intent in ("GET_WEATHER", "GET_WEATHER_BY_DAY"):
        place = None
        day = None

        if len(parts) >= 2:
            place = parts[1]
        if len(parts) >= 3:
            day = parts[2]

        m_loc = re.search(r'LOCATION\s*=\s*"?([^";]+)"?', first_line, re.IGNORECASE)
        m_day = re.search(r'DAY\s*=\s*"?([^";]+)"?', first_line, re.IGNORECASE)
        if m_loc:
            place = m_loc.group(1).strip()
        if m_day:
            day = m_day.group(1).strip()

        if isinstance(place, str):
            place = place.strip().strip('"').strip("'")
            if place.lower() in ("anywhere", "location", "unknown", "unspecified"):
                place = None

        if isinstance(day, str):
            day = day.strip().strip('"').strip("'").lower()
            day = re.sub(r"[^a-z]", "", day)  # remove punctuation
            if day not in _WEEKDAYS:
                day = None

        if place:
            result["params"]["place"] = place
        if day:
            result["params"]["day"] = day
            result["intent"] = "GET_WEATHER_BY_DAY"

        return result

    # ---- Create appointment ----
    if intent == "CREATE_APPOINTMENT":
        json_str = first_line.split(";", 1)[1].strip() if ";" in first_line else ""
        if json_str:
            try:
                result["params"] = json.loads(json_str)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", json_str)
                if match:
                    try:
                        result["params"] = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        pass
        return result

    # ---- Read/Update/Delete ----
    if intent in ("READ_APPOINTMENT_BY_ID", "UPDATE_APPOINTMENT", "DELETE_APPOINTMENT",
                  "DELETE_APPOINTMENT_ALL", "DELETE_LAST_APPOINTMENT", "READ_APPOINTMENT_ALL"):
        if intent in ("DELETE_APPOINTMENT_ALL", "DELETE_LAST_APPOINTMENT", "READ_APPOINTMENT_ALL"):
            return result

        if len(parts) >= 2:
            ident = parts[1].strip().strip('"').strip("'")
            if ident.isdigit():
                result["params"]["id"] = int(ident)
            else:
                result["params"]["title"] = ident

        if intent == "UPDATE_APPOINTMENT" and len(parts) >= 3:
            json_part = ";".join(parts[2:]).strip()
            match = re.search(r"\{.*\}", json_part)
            if match:
                try:
                    result["params"].update(json.loads(match.group(0)))
                except json.JSONDecodeError:
                    pass

        return result

    return result


def process_text_input(user_text: str, dialogue_state=None) -> str:
    if dialogue_state is None:
        dialogue_state = {}

    intent_raw = nlu_parse(user_text, dialogue_state)
    print(f"[NLU] Raw Intent: {intent_raw}")

    parsed_intent = parse_intent_response(intent_raw)
    print(f"[NLU] Parsed Intent: {parsed_intent}")

    # ---- Override for "weather on <weekday>" WITHOUT explicit location ----
    # If user says only a day (e.g. "on Friday"), we should:
    # - treat it as GET_WEATHER_BY_DAY
    # - use last_location (so remove any model-invented place)
    day_override = extract_weekday_from_text(user_text)
    if day_override and parsed_intent["intent"] in ("GET_WEATHER", "GET_WEATHER_BY_DAY"):
        if not user_mentioned_place(user_text):
            parsed_intent["intent"] = "GET_WEATHER_BY_DAY"
            parsed_intent["params"]["day"] = day_override
            parsed_intent["params"].pop("place", None)

    response_text = execute_intent(parsed_intent, dialogue_state)

    print(f"[Execution] Response: {response_text}")

    try:
        conversations.insert_one({
            "query": user_text,
            "response": response_text,
            "timestamp": datetime.datetime.now()
        })
        print("[MongoDB] ✓ Saved to database")
    except Exception as e:
        print(f"[MongoDB] ✗ Failed to save: {e}")

    return response_text


def execute_intent(parsed_intent, dialogue_state=None):
    intent = parsed_intent["intent"]
    params = parsed_intent["params"]

    if dialogue_state is None:
        dialogue_state = {}

    # Weather
    if intent == "GET_WEATHER":
        place = params.get("place") or dialogue_state.get("last_location", "Marburg")
        result = weather_get(place)
        print("GET_WEATHER:---------------" + str(result))

        if result and "forecast" in result:
            dialogue_state["last_location"] = place

            place_name = result.get("place", place)
            forecast_text = f"Weather forecast for {place_name}:\n\n"
            for day_forecast in result["forecast"]:
                day = day_forecast.get("day", "").capitalize()
                temp = day_forecast.get("temperature", {})
                forecast_text += f"{day}: {day_forecast.get('weather','N/A')}, {temp.get('min','N/A')}°C - {temp.get('max','N/A')}°C\n"
            return forecast_text

        return f"Could not get weather for {place}"

    if intent == "GET_WEATHER_BY_DAY":
        place = params.get("place") or dialogue_state.get("last_location", "Marburg")
        day = params.get("day") or dialogue_state.get("last_date")

        if not day:
            return "Please specify a day"

        result = weather_get_by_day(place, day)
        print("GET_WEATHER_BY_DAY:---------------" + str(result))

        if result:
            dialogue_state["last_location"] = place
            dialogue_state["last_date"] = day
            temp = result["temperature"]
            return (
                f"Weather in {result['place']} on {result['day'].capitalize()}:\n"
                f"{result['weather'].capitalize()}, {temp['min']}°C - {temp['max']}°C"
            )

        return f"Could not get weather for {place} on {day}"

    # Appointments
    if intent == "CREATE_APPOINTMENT":
        result = calendercreate(
            teamid=1123,
            title=params.get("title", ""),
            description=params.get("description", ""),
            start_time=params.get("start_time", ""),
            end_time=params.get("end_time", ""),
            location=params.get("location", ""),
        )
        if result:
            dialogue_state["last_appointment_id"] = result.get("id")
            dialogue_state["last_appointment_title"] = params.get("title")
            return f"Appointment created: {params.get('title')}"
        return "Failed to create appointment"

    if intent == "READ_APPOINTMENT_ALL":
        result = calendergetall(1123)
        return result if result else "No appointments found"

    if intent == "READ_APPOINTMENT_BY_ID":
        appointment_id = params.get("id")
        if not appointment_id:
            return "No appointment ID specified"
        result = calendergetbyid(appointment_id)
        if result:
            dialogue_state["last_appointment_id"] = appointment_id
            dialogue_state["last_appointment_title"] = result.get("title")
            return json.dumps(result, indent=2)
        return "Appointment not found"

    if intent == "UPDATE_APPOINTMENT":
        appointment_id = params.get("id")
        title = params.get("title")

        if not appointment_id and title:
            ev = calendergetbytitle(1123, title)
            if not ev:
                return f'No appointment found with title "{title}"'
            appointment_id = ev.get("id") or ev.get("eventid")

        if not appointment_id:
            return "No appointment ID or title specified"

        result = calenderupdate(appointment_id, params)
        if result:
            dialogue_state["last_appointment_id"] = appointment_id
            dialogue_state["last_appointment_title"] = params.get("title") or dialogue_state.get("last_appointment_title")
            return f"Appointment {appointment_id} updated"
        return "Failed to update"

    if intent == "DELETE_APPOINTMENT_ALL":
        events = calendergetall(1123)
        if not events:
            return "No appointments to delete"

        deleted = 0
        failed = 0
        for ev in events:
            if not isinstance(ev, dict):
                failed += 1
                continue
            ev_id = ev.get("id") or ev.get("eventid")
            if isinstance(ev_id, str) and ev_id.isdigit():
                ev_id = int(ev_id)
            if not isinstance(ev_id, int):
                failed += 1
                continue

            ok = calenderdelete(ev_id)
            deleted += 1 if ok else 0
            failed += 0 if ok else 1

        if deleted > 0:
            dialogue_state["last_appointment_id"] = None
            dialogue_state["last_appointment_title"] = None

        return f"Deleted {deleted} appointments" if failed == 0 else f"Deleted {deleted} appointments, failed to delete {failed}"

    if intent == "DELETE_LAST_APPOINTMENT":
        last_id = dialogue_state.get("last_appointment_id")
        if last_id and calenderdelete(last_id):
            return f"Deleted last appointment (id {last_id})"

        events = calendergetall(1123)
        last_id = _pick_last_event_id(events)
        if not last_id:
            return "No appointments found to delete"

        ok = calenderdelete(last_id)
        return f"Deleted last appointment (id {last_id})" if ok else "Failed to delete last appointment"

    if intent == "DELETE_APPOINTMENT":
        event_id = params.get("id") or dialogue_state.get("last_appointment_id")
        title = params.get("title") or dialogue_state.get("last_appointment_title")

        if event_id:
            ok = calenderdelete(event_id)
            return f"Appointment {event_id} deleted" if ok else "Failed to delete"

        if title:
            ev = calendergetbytitle(1123, title)
            if not ev:
                return f'No appointment found with title "{title}"'
            resolved_id = ev.get("id") or ev.get("eventid")
            ok = calenderdelete(resolved_id)
            return f'Deleted "{ev.get("title", title)}" (id {resolved_id})' if ok else "Failed to delete"

        return "No appointment ID or title specified"

    return "Unknown intent"
