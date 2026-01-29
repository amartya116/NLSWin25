import ollama
from pymongo import MongoClient
from .responserev import (calendercreate, calendergetall, calendergetbyid,
                       calenderupdate, calenderdelete, calenderdelete_by_title, calendergetbytitle,
                       weather_get, weather_get_by_day)

import datetime
import json
import re
import os



MONGO_URI = os.getenv("MONGO_URI", "mongodb://host.docker.internal:27017/")
client = MongoClient(MONGO_URI)


os.environ["OLLAMA_HOST"] = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

x = datetime.datetime.now()
v = x.strftime("%A")

client = MongoClient(MONGO_URI)
db = client["nls"]
conversations = db["conversations"]
SYSTEM_PROMPT = """
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
-DELETE_APPOINTMENT_ALL
-DELETE_LAST_APPOINTMENT


Rules:
- Output format: INTENT;PARAM1;PARAM2;...
- Today's day is """ + v + """
- For weather queries: GET_WEATHER;LOCATION or GET_WEATHER_BY_DAY;LOCATION;DAY
- the date and time is """ + str(x) + """ and every appointment should be 60 min unless explicitly stated 
-the description should be a one sentence summery of the request and along with title, it should be necessary even when you are updating.
- For CREATE_APPOINTMENT: CREATE_APPOINTMENT;for example = {"title":"Meeting","description":"Team sync","start_time":"" ,"end_time":"","location":"Office"} figure out title, description and start and end time and location by yourself
- For UPDATE_APPOINTMENT: UPDATE_APPOINTMENT;ID;{"title":"Updated Meeting"}
THIS IS IMPORTANT-When UPDATING appointment u MUST update description and also MUST UPDATE dates and location if these were specified.
- For READ_APPOINTMENT_BY_ID: READ_APPOINTMENT_BY_ID;ID
- For DELETE_APPOINTMENT: DELETE_APPOINTMENT;ID_OR_TITLE (if the user gives a title like "meeting with boss", output that title as the second field)
- For DELETE_APPOINTMENT_ALL: DELETE_APPOINTMENT_ALL
- For DELETE_LAST_APPOINTMENT: DELETE_LAST_APPOINTMENT
- Extract location and day from context if not explicitly mentioned
- Do NOT include explanations, ONLY output the intent line
- Ensure JSON is valid and on a single line
"""
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
    response = ollama.generate(
        model=MODEL,
        prompt=prompt,
    )

    intent = response["response"].strip()
    return intent


def _pick_last_event_id(events):
    """
    Best-effort selection of the 'last' event.
    - If list order is meaningful, last element is used.
    - Otherwise try max numeric id.
    Returns int id or None.
    """
    if not events or not isinstance(events, list):
        return None

    # Try last element first (most APIs return chronological / insertion order)
    last = events[-1]
    if isinstance(last, dict):
        cand = last.get("id") or last.get("eventid")
        if isinstance(cand, int):
            return cand
        if isinstance(cand, str) and cand.isdigit():
            return int(cand)

    # Fallback: choose max numeric id from all events
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
    """Parse the LLM response to extract intent and parameters.

    Expected formats:
      - GET_WEATHER;LOCATION
      - GET_WEATHER_BY_DAY;LOCATION;DAY
      - CREATE_APPOINTMENT;{...json...}
      - READ_APPOINTMENT_ALL
      - READ_APPOINTMENT_BY_ID;ID
      - UPDATE_APPOINTMENT;ID_OR_TITLE;{...json...}
      - DELETE_APPOINTMENT;ID_OR_TITLE
    """
    intent_string = (intent_string or "").strip()

    # Defensive: sometimes models add newlines or extra text. We only take the first line.
    first_line = intent_string.splitlines()[0].strip()

    # Split by ';' but keep meaningful empty-free tokens for ID/title extraction
    raw_parts = [p.strip() for p in first_line.split(";")]
    parts = [p for p in raw_parts if p != ""]

    result = {"intent": parts[0] if parts else "", "params": {}}
    intent = result["intent"]

    # ---- Weather ----
    if intent in ("GET_WEATHER", "GET_WEATHER_BY_DAY"):
        if len(parts) >= 2:
            result["params"]["place"] = parts[1]
        if intent == "GET_WEATHER_BY_DAY" and len(parts) >= 3:
            result["params"]["day"] = parts[2]
        return result

    # ---- Create appointment (JSON after the first ;) ----
    if intent == "CREATE_APPOINTMENT":
        json_str = first_line.split(";", 1)[1].strip() if ";" in first_line else ""
        if json_str:
            try:
                result["params"] = json.loads(json_str)
            except json.JSONDecodeError:
                # best-effort extraction if the model wrapped JSON with extra text
                match = re.search(r"\{.*\}", json_str)
                if match:
                    try:
                        result["params"] = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        pass
        return result

    # ---- Read/Update/Delete appointment ----
    if intent in ("READ_APPOINTMENT_BY_ID", "UPDATE_APPOINTMENT", "DELETE_APPOINTMENT", "DELETE_APPOINTMENT_ALL",
                  "DELETE_LAST_APPOINTMENT"):
        # Intents with no params
        if intent in ("DELETE_APPOINTMENT_ALL", "DELETE_LAST_APPOINTMENT"):
            return result
        if len(parts) >= 2:
            ident = parts[1].strip().strip('"').strip("'")
            if ident.isdigit():
                result["params"]["id"] = int(ident)
            else:
                result["params"]["title"] = ident


        if intent == "UPDATE_APPOINTMENT" and len(parts) >= 3:
            # tolerate extra ';' in accidental formatting
            json_part = ";".join(parts[2:]).strip()
            match = re.search(r"\{.*\}", json_part)
            if match:
                try:
                    result["params"].update(json.loads(match.group(0)))
                except json.JSONDecodeError:
                    pass

        # READ_APPOINTMENT_ALL or unknown
    return result



def process_text_input(user_text: str, dialogue_state=None) -> str:
    """
    Process text input from frontend
    Saves query and response to MongoDB

    Args:
        user_text: Text input from user
        dialogue_state: Optional dialogue state dictionary for context

    Returns:
        Response text
    """
    if dialogue_state is None:
        dialogue_state = {}

    # Step 1: Parse intent from the text
    intent_raw = nlu_parse(user_text, dialogue_state)
    print(f"[NLU] Raw Intent: {intent_raw}")

    # Step 2: Parse the intent response
    parsed_intent = parse_intent_response(intent_raw)
    print(f"[NLU] Parsed Intent: {parsed_intent}")

    # Step 3: Execute the intent to get the response
    response_text = execute_intent(parsed_intent, dialogue_state)
    print(f"[Execution] Response: {response_text}")

    # Step 4: Save to MongoDB
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


#----------------------------


def execute_intent(parsed_intent, dialogue_state=None):
    """Execute the appropriate function based on parsed intent"""
    intent = parsed_intent['intent']
    params = parsed_intent['params']
    
    if dialogue_state is None:
        dialogue_state = {}
    
    # Weather intents
    if intent == 'GET_WEATHER':
        place = params.get('place') or dialogue_state.get('last_location', 'Marburg')
        result = weather_get(place)
        print("GET_WEATHER:---------------" + str(result))
        
        if result and "forecast" in result:
            dialogue_state['last_location'] = place
            
            # Format the forecast inline
            place_name = result.get("place", "Marburg")
            forecast_text = f"Weather forecast for {place_name}:\n\n"
            
            for day_forecast in result["forecast"]:
                day = day_forecast.get("day", "").capitalize()
                temp = day_forecast.get("temperature", {})
                min_temp = temp.get("min", "N/A")
                max_temp = temp.get("max", "N/A")
                weather = day_forecast.get("weather", "N/A")
                
                forecast_text += f"{day}: {weather}, {min_temp}°C - {max_temp}°C\n"
            
            return forecast_text
        
        return f"Could not get weather for {place}"
    
    elif intent == 'GET_WEATHER_BY_DAY':
        place = params.get('place') or dialogue_state.get('last_location', 'Marburg')
        day = params.get('day') or dialogue_state.get('last_date')
        
        if not day:
            return "Please specify a day"
        
        result = weather_get_by_day(place, day)
        print("GET_WEATHER_BY_DAY:---------------" + place)

        
        if result:
            dialogue_state['last_location'] = place
            dialogue_state['last_date'] = day
            
            temp = result['temperature']
            return (f"Weather in {result['place']} on {result['day'].capitalize()}:\n"
                   f"{result['weather'].capitalize()}, "
                   f"{temp['min']}°C - {temp['max']}°C")
        
        return f"Could not get weather for {place} on {day}"
    
    # Appointment intents
    elif intent == 'CREATE_APPOINTMENT':
        result = calendercreate(
            teamid=1123,
            title=params.get('title', ''),
            description=params.get('description', ''),
            start_time=params.get('start_time', ''),
            end_time=params.get('end_time', ''),
            location=params.get('location', '')
        )
        if result:
            dialogue_state['last_appointment_id'] = result.get('id')
            dialogue_state['last_appointment_title'] = params.get('title')
            return f"Appointment created: {params.get('title')}"
        return "Failed to create appointment"
    
    elif intent == 'READ_APPOINTMENT_ALL':
        result = calendergetall(1123)
        return result if result else "No appointments found"

    elif intent == 'READ_APPOINTMENT_BY_ID':
        appointment_id = params.get('id')
        if not appointment_id:
            return "No appointment ID specified"
        result = calendergetbyid(appointment_id)
        if result:
            dialogue_state['last_appointment_id'] = appointment_id
            dialogue_state['last_appointment_title'] = result.get("title")
            return json.dumps(result, indent=2)
        return "Appointment not found"



    elif intent == 'UPDATE_APPOINTMENT':

        appointment_id = params.get('id')
        title = params.get('title')
        # If we got a title instead of an id, resolve to an id first

        if not appointment_id and title:
            ev = calendergetbytitle(1123, title)
            if not ev:
                return f'No appointment found with title "{title}"'
            resolved_id = ev.get("id") or ev.get("eventid")
            if resolved_id is None:
                return f'Found "{title}" but it has no id in the API response'
            appointment_id = resolved_id

        if not appointment_id:
            return "No appointment ID or title specified"

        result = calenderupdate(appointment_id, params)

        if result:
            dialogue_state['last_appointment_id'] = appointment_id
            dialogue_state['last_appointment_title'] = params.get("title") or dialogue_state.get(
                'last_appointment_title')
            return f"Appointment {appointment_id} updated"
        return "Failed to update"


    elif intent == 'DELETE_APPOINTMENT_ALL':
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
            if ok:
                deleted += 1
            else:
                failed += 1

        # Clear last pointers if we deleted everything
        if deleted > 0:
            dialogue_state['last_appointment_id'] = None
            dialogue_state['last_appointment_title'] = None

        if failed == 0:
            return f"Deleted {deleted} appointments"
        return f"Deleted {deleted} appointments, failed to delete {failed}"

    elif intent == 'DELETE_LAST_APPOINTMENT':
        # First try what we *know* is last from conversation context
        last_id = dialogue_state.get('last_appointment_id')
        if last_id:
            ok = calenderdelete(last_id)
            if ok:
                return f"Deleted last appointment (id {last_id})"
            # If it failed, fall back to fetching

        events = calendergetall(1123)
        last_id = _pick_last_event_id(events)
        if not last_id:
            return "No appointments found to delete"

        ok = calenderdelete(last_id)
        if ok:
            dialogue_state['last_appointment_id'] = last_id
            return f"Deleted last appointment (id {last_id})"
        return "Failed to delete last appointment"




    elif intent == 'DELETE_APPOINTMENT':
        # Allow deleting by numeric id OR by title (e.g. "meeting with boss")
        event_id = params.get('id') or dialogue_state.get('last_appointment_id')
        title = params.get('title') or dialogue_state.get('last_appointment_title')

        if event_id:
            result = calenderdelete(event_id)
            return f"Appointment {event_id} deleted" if result else "Failed to delete"

        if title:
            ev = calendergetbytitle(1123, title)
            if not ev:
                return f'No appointment found with title "{title}"'

            resolved_id = ev.get("id") or ev.get("eventid")
            if resolved_id is None:
                return f'Found "{title}" but it has no id in the API response'

            result = calenderdelete(resolved_id)
            if result:
                dialogue_state['last_appointment_id'] = resolved_id
                dialogue_state['last_appointment_title'] = ev.get("title") or title
                return f'Deleted "{ev.get("title", title)}" (id {resolved_id})'
            return "Failed to delete"

        return "No appointment ID or title specified"

    return "Unknown intent"


# ------------------ QUICK TEST ------------------
if __name__ == "__main__":
    print("=" * 60)
    print("MONGODB CONNECTION TEST")
    print("=" * 60)
    
    # Test 1: Check MongoDB connection
    try:
        client.admin.command('ping')
        print("✓ MongoDB connected successfully")
    except Exception as e:
        print(f"✗ MongoDB connection failed: {e}")
        exit(1)
    
    # Test 2: Direct insert without NLU
    print("\nTest 2: Direct MongoDB Insert")
    try:
        result = conversations.insert_one({
            "query": "test query",
            "response": "test response",
            "timestamp": datetime.datetime.now()
        })
        print(f"✓ Direct insert successful! ID: {result.inserted_id}")
        
        # Verify it was inserted
        count = conversations.count_documents({})
        print(f"✓ Total documents in 'conversations': {count}")
        
    except Exception as e:
        print(f"✗ Direct insert failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Using process_text_input function
    print("\nTest 3: Using process_text_input()")
    try:
        test_query = "What's the weather in Berlin?"
        print(f"Input: {test_query}")
        response = process_text_input(test_query)
        print(f"Output: {response}")
        
        # Check total count again
        count = conversations.count_documents({})
        print(f"✓ Total documents in 'conversations': {count}")
        
    except Exception as e:
        print(f"✗ process_text_input failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("✓ Done! Refresh MongoDB Compass to see 'conversations' collection")
    print("=" * 60)
