import requests

teamid = 1123

# ============= APPOINTMENT FUNCTIONS =============
def calendercreate(teamid,title,description,start_time,end_time,location):
    try:
        url = f'https://api.responsible-nlp.net/calendar.php?calenderid={1123}'
        payload = {
            "id": teamid,
            "title": title,
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "location": location
        }
        headers = {
            "Content-Type": "application/json",
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return (response.json())
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
    
def calendergetall(teamid):
    try:
        url = f'https://api.responsible-nlp.net/calendar.php?calenderid={teamid}'
        headers = {
            "Content-Type": "application/json",
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return (response.json())
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
    
def calendergetbyid(eventid):
    try:
        url = f'https://api.responsible-nlp.net/calendar.php?calenderid={teamid}&id={eventid}'
        headers = {
            "Content-Type": "application/json",
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return (response.json())
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
    
def calenderupdate(eventid,title,description,start_time,end_time,location):
    try:
        url = f'https://api.responsible-nlp.net/calendar.php?calenderid={teamid}&id={eventid}'
        payload = {
            "id": eventid,
            "title": title,
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "location": location
        }
        headers = {
            "Content-Type": "application/json",
        }

        response = requests.put(url, json=payload, headers=headers)
        response.raise_for_status()

        return (response.json())
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None
    
def calenderdelete(eventid):
    try:
        url = f'https://api.responsible-nlp.net/calendar.php?calenderid={teamid}&id={eventid}'
        headers = {
            "Content-Type": "application/json",
        }

        response = requests.delete(url, headers=headers)
        response.raise_for_status()

        return (response.json())
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None


# ============= WEATHER FUNCTIONS =============
def weather_get(place):
    """
    Get weather forecast for a specific place.
    
    Args:
        place (str): The name of the place to get weather for
        
    Returns:
        dict: Weather forecast data including place and 7-day forecast, or None if error
    """
    try:
        url = 'https://api.responsible-nlp.net/weather.php'
        
        # Use form data instead of JSON (as per API specification)
        payload = {"place": place}
        
        # Send as form data
        response = requests.post(url, data=payload)
        response.raise_for_status()

        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None


def weather_get_by_day(place, day):
    """
    Get weather forecast for a specific day at a specific place.
    
    Args:
        place (str): The name of the place to get weather for
        day (str): The day to filter (e.g., "monday", "tuesday", etc.)
        
    Returns:
        dict: Weather data for the specific day, or None if not found/error
    """
    try:
        weather_data = weather_get(place)
        
        if weather_data and "forecast" in weather_data:
            for forecast in weather_data["forecast"]:
                if forecast.get("day", "").lower() == day.lower():
                    return {
                        "place": weather_data["place"],
                        "day": forecast["day"],
                        "temperature": forecast["temperature"],
                        "weather": forecast["weather"]
                    }
        
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


# ============= TEST =============
if __name__ == "__main__":
    print("Testing weather API...")
    print("=" * 60)
    
    # Test 1: Get full forecast
    print("\n1. Testing weather_get('Marburg'):")
    result = weather_get("Marburg")
    print(result)
    
    # Test 2: Get specific day
    if result:
        print("\n2. Testing weather_get_by_day('Marburg', 'friday'):")
        day_result = weather_get_by_day("Marburg", "friday")
        print(day_result)
        
        # Test 3: Format inline
        print("\n3. Formatted output:")
        if result and "forecast" in result:
            print(f"Weather forecast for {result['place']}:\n")
            for day_forecast in result["forecast"]:
                day = day_forecast.get("day", "").capitalize()
                temp = day_forecast.get("temperature", {})
                weather = day_forecast.get("weather", "N/A")
                print(f"{day}: {weather}, {temp.get('min')}°C - {temp.get('max')}°C")
    
    print("\n" + "=" * 60)