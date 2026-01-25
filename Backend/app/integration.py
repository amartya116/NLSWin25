import ollama
from pymongo import MongoClient
from responserev import (calendercreate, calendergetall, calendergetbyid, 
                       calenderupdate, calenderdelete, weather_get, 
                       weather_get_by_day)
from tts_local import synth_to_wav
import datetime
import json
import re


# MongoDB Configuration
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "nls"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
conversations = db["conversations"]

x = datetime.datetime.now()
v = x.strftime("%A")
MODEL = "llama3"

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

Rules:
- Output format: INTENT;PARAM1;PARAM2;...
- Today's day is """ + v + """
- For weather queries: GET_WEATHER;LOCATION or GET_WEATHER_BY_DAY;LOCATION;DAY
- For CREATE_APPOINTMENT: CREATE_APPOINTMENT;{"title":"Meeting","description":"Team sync","start_time":"2024-01-20 10:00","end_time":"2024-01-20 11:00","location":"Office"}
- For UPDATE_APPOINTMENT: UPDATE_APPOINTMENT;ID;{"title":"Updated Meeting"}
- For READ_APPOINTMENT_BY_ID: READ_APPOINTMENT_BY_ID;ID
- For DELETE_APPOINTMENT: DELETE_APPOINTMENT;ID
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
        prompt=prompt
    )

    intent = response["response"].strip()
    return intent


def parse_intent_response(intent_string):
    """Parse the LLM response to extract intent and parameters"""
    parts = intent_string.split(';', 1)  # Split only on FIRST semicolon
    
    result = {
        'intent': parts[0].strip(),
        'params': {}
    }
    
    # Extract parameters based on intent type
    if 'GET_WEATHER' in result['intent']:
        subparts = intent_string.split(';')
        if len(subparts) > 1:
            result['params']['place'] = subparts[1].strip()
        if len(subparts) > 2:
            result['params']['day'] = subparts[2].strip()
    
    elif 'APPOINTMENT' in result['intent']:
        # For CREATE_APPOINTMENT, expect JSON after semicolon
        if result['intent'] == 'CREATE_APPOINTMENT':
            if len(parts) > 1:
                json_str = parts[1].strip()
                try:
                    result['params'] = json.loads(json_str)
                    print(f"[DEBUG] Parsed appointment JSON: {result['params']}")
                except json.JSONDecodeError as e:
                    print(f"[ERROR] Failed to parse JSON: {e}")
                    print(f"[ERROR] Raw string: {json_str}")
                    # Try to extract JSON pattern
                    json_match = re.search(r'\{[^}]+\}', json_str)
                    if json_match:
                        try:
                            result['params'] = json.loads(json_match.group())
                            print(f"[DEBUG] Extracted JSON: {result['params']}")
                        except:
                            pass
        
        # For UPDATE/READ/DELETE, extract ID first, then JSON if present
        elif result['intent'] in ['UPDATE_APPOINTMENT', 'READ_APPOINTMENT_BY_ID', 'DELETE_APPOINTMENT']:
            subparts = intent_string.split(';')
            if len(subparts) > 1 and subparts[1].strip().isdigit():
                result['params']['id'] = int(subparts[1].strip())
            
            # For UPDATE, also look for JSON
            if result['intent'] == 'UPDATE_APPOINTMENT' and len(subparts) > 2:
                try:
                    result['params'].update(json.loads(subparts[2].strip()))
                except:
                    pass
    
    return result
    """Parse the LLM response to extract intent and parameters"""
    parts = intent_string.split(';')
    
    result = {
        'intent': parts[0].strip(),
        'params': {}
    }
    
    # Extract parameters based on intent type
    if 'GET_WEATHER' in result['intent']:
        if len(parts) > 1:
            result['params']['place'] = parts[1].strip()
        if len(parts) > 2:
            result['params']['day'] = parts[2].strip()
    
    elif 'APPOINTMENT' in result['intent']:
        # Try to extract JSON if present
        json_match = re.search(r'\{.*\}', intent_string, re.DOTALL)
        if json_match:
            try:
                result['params'] = json.loads(json_match.group())
            except:
                pass
        
        # Extract ID for read/update/delete
        if len(parts) > 1 and parts[1].strip().isdigit():
            result['params']['id'] = int(parts[1].strip())
    
    return result


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
        
        if result and "forecast" in result:
            dialogue_state['last_location'] = place
            
            # Format the forecast inline
            place_name = result.get("place", "Unknown")
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
            return f"Appointment created: {params.get('title')}"
        return "Failed to create appointment"
    
    elif intent == 'READ_APPOINTMENT_ALL':
        result = calendergetall(1123)
        return result if result else "No appointments found"
    
    elif intent == 'READ_APPOINTMENT_BY_ID':
        event_id = params.get('id') or dialogue_state.get('last_appointment_id')
        if not event_id:
            return "No appointment ID specified"
        result = calendergetbyid(event_id)
        return result if result else f"Appointment {event_id} not found"
    
    elif intent == 'UPDATE_APPOINTMENT':
        event_id = params.get('id') or dialogue_state.get('last_appointment_id')
        if not event_id:
            return "No appointment ID specified"
        result = calenderupdate(
            eventid=event_id,
            title=params.get('title', ''),
            description=params.get('description', ''),
            start_time=params.get('start_time', ''),
            end_time=params.get('end_time', ''),
            location=params.get('location', '')
        )
        return f"Appointment {event_id} updated" if result else "Failed to update"
    
    elif intent == 'DELETE_APPOINTMENT':
        event_id = params.get('id') or dialogue_state.get('last_appointment_id')
        if not event_id:
            return "No appointment ID specified"
        result = calenderdelete(event_id)
        return f"Appointment {event_id} deleted" if result else "Failed to delete"
    
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


def process_audio_to_audio(audio_path: str, dialogue_state=None) -> str:
    """
    Complete pipeline: Audio → Text (ASR) → Intent → Execution → Speech (TTS)
    Saves query and response to MongoDB
    
    Args:
        audio_path: Path to the input audio file (WAV format)
        dialogue_state: Optional dialogue state dictionary for context
    
    Returns:
        Path to the output WAV file with the response
    """
    if dialogue_state is None:
        dialogue_state = {}
    
    # Step 1: Convert audio to text using ASR
    user_text = transcribe_wav(audio_path)
    print(f"[ASR] Transcribed: {user_text}")
    
    # Step 2: Parse intent from the transcribed text
    intent_raw = nlu_parse(user_text, dialogue_state)
    print(f"[NLU] Raw Intent: {intent_raw}")
    
    # Step 3: Parse the intent response
    parsed_intent = parse_intent_response(intent_raw)
    print(f"[NLU] Parsed Intent: {parsed_intent}")
    
    # Step 4: Execute the intent to get the natural language response
    response_text = execute_intent(parsed_intent, dialogue_state)
    print(f"[Execution] Response: {response_text}")
    
    # Step 5: Save to MongoDB
    conversations.insert_one({
        "query": user_text,
        "response": response_text,
        "timestamp": datetime.datetime.now()
    })
    
    # Step 6: Convert the response text to speech using TTS
    output_audio_path = synth_to_wav(response_text)
    print(f"[TTS] Output: {output_audio_path}")
    
    return output_audio_path