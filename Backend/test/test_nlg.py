import asyncio
from Backend.app.NLG import generate_nlg

async def t():
    data = {
        "intent": "weather_forecast",
        "entities": {"place": "Marburg"},
        "tool_results": {
            "weather_api": {
                "place": "Marburg",
                "forecast": [
                    {"day": "friday", "temperature": {"min": 6, "max": 14}, "weather": "rain"}
                ]
            }
        },
        "conversation_state": {"locale": "en", "timezone": "Europe/Berlin", "pending_slots": []}
    }

    r = await generate_nlg(data, model="llama3.2")
    print(r.text)

asyncio.run(t())
