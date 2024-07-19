from common import *
from weather_codes import weather_codes

async def spotify_action(text: str):
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    if client_id and client_secret:
        try:
            async with aiohttp.ClientSession() as session:
                ip = subprocess.run(["hostname", "-I"], capture_output=True).stdout.decode().split()[0]
                response = await session.post(f"http://{ip}/spotify-control", json={"text": text})
                if response.status == 200:
                    data = await response.json()
                    return data.get("message")
                else:
                    content_text = await response.text()
                    logger.warning(content_text)
                    return f"Received a {response.status} status code. {content_text}"
        except Exception as e:
            logger.error(f"Error: {traceback.format_exc()}")
            raise Exception(f"Something went wrong: {e}")
    raise Exception("No client id or client secret found. Please provide the necessary credentials for Spotify in the web interface.")

async def coords_from_city(city, api_key=None):
    async with aiohttp.ClientSession() as session:
        if api_key:
            response = await session.get(f"http://api.openweathermap.org/geo/1.0/direct?q={city}&appid={api_key}")
            if response.status == 200:
                json_response = await response.json()
                coords = {
                    "lat": json_response[0].get('lat'),
                    "lon": json_response[0].get('lon')
                }
                return coords
        
        # Fallback to Open-Meteo if no API key or OpenWeather fails
        response = await session.get(f"https://nominatim.openstreetmap.org/search?q={city}&format=json")
        if response.status == 200:
            json_response = await response.json()
            coords = {
                "lat": float(json_response[0].get('lat')),
                "lon": float(json_response[0].get('lon'))
            }
            return coords

async def city_from_ip():
    async with aiohttp.ClientSession() as session:
        response = await session.get(f"https://ipinfo.io/json")
        if response.status == 200:
            json_response = await response.json()
            city = json_response.get('city')
            return city

async def open_weather_action(text: str):
    try:
        api_key = os.getenv('OPEN_WEATHER_API_KEY')
        async with aiohttp.ClientSession() as session:
            if re.search(r'(weather|temperature).*\sin\s', text, re.IGNORECASE):
                city_match = re.search(r'in\s([\w\s]+)', text, re.IGNORECASE)
                if city_match:
                    city = city_match.group(1).strip()

                # Current weather
                if not re.search(r'(forecast|future)', text, re.IGNORECASE):
                    coords = await coords_from_city(city, api_key)
                    if coords is None:
                        return f"No weather data available for {city}. Please check the city name and try again."
                    
                    if api_key:
                        response = await session.get(f"https://api.openweathermap.org/data/3.0/onecall?lat={coords.get('lat')}&lon={coords.get('lon')}&appid={api_key}&units=imperial")
                        if response.status == 200:
                            json_response = await response.json()
                            logger.debug(json_response)
                            weather = json_response.get('current').get('weather')[0].get('main')
                            temp = json_response.get('current').get('temp')
                            return f"It is currently {round(float(temp))} degrees and {weather.lower()} in {city}."
                    
                    # Fallback to Open-Meteo
                    response = await session.get(f"https://api.open-meteo.com/v1/forecast?latitude={coords.get('lat')}&longitude={coords.get('lon')}&current_weather=true&temperature_unit=fahrenheit")
                    if response.status == 200:
                        json_response = await response.json()
                        weather_code = json_response.get('current_weather').get('weathercode')
                        temp = json_response.get('current_weather').get('temperature')
                        weather_description = weather_codes[str(weather_code)]['day']['description'] if datetime.now().hour < 18 else weather_codes[str(weather_code)]['night']['description']
                        return f"It is currently {round(float(temp))} degrees and {weather_description.lower()} in {city}."

                # Weather forecast
                else:
                    coords = await coords_from_city(city, api_key)
                    tomorrow = datetime.now() + timedelta(days=1)
                    if coords is None:
                        return f"No weather data available for {city}. Please check the city name and try again."
                    
                    if api_key:
                        response = await session.get(f"https://api.openweathermap.org/data/3.0/onecall?lat={coords.get('lat')}&lon={coords.get('lon')}&appid={api_key}&units=imperial")
                        if response.status == 200:
                            json_response = await response.json()
                            # next few days
                            forecast = []
                            for day in json_response.get('daily'):
                                forecast.append({
                                    'weather': day.get('weather')[0].get('main'),
                                    'temp': day.get('temp').get('day'),
                                    'date': datetime.fromtimestamp(day.get('dt')).strftime('%A')
                                })
                            # tomorrow
                            tomorrow_forecast = list(filter(lambda x: x.get('date') == tomorrow.strftime('%A'), forecast))[0]
                            speech_responses = []
                            speech_responses.append(f"Tomorrow, it will be {tomorrow_forecast.get('temp')}\u00B0F and {tomorrow_forecast.get('weather')} in {city}.")
                            for day in forecast:
                                if day.get('date') != tomorrow.strftime('%A'):
                                    speech_responses.append(f"On {day.get('date')}, it will be {round(float(day.get('temp')))} degrees and {day.get('weather').lower()} in {city}.")
                            return ' '.join(speech_responses)
                    
                    # Fallback to Open-Meteo
                    response = await session.get(f"https://api.open-meteo.com/v1/forecast?latitude={coords.get('lat')}&longitude={coords.get('lon')}&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit")
                    if response.status == 200:
                        json_response = await response.json()
                        forecast = []
                        for day in json_response.get('daily'):
                            day_weather_code = day.get('weathercode')
                            day_weather_description = weather_codes[str(day_weather_code)]['day']['description'] if datetime.now().hour < 18 else weather_codes[str(day_weather_code)]['night']['description']
                            forecast.append({
                                'temp_max': day.get('temperature_2m_max'),
                                'temp_min': day.get('temperature_2m_min'),
                                'weather_description': day_weather_description,
                                'date': day.get('time')
                            })
                        tomorrow_forecast = list(filter(lambda x: x.get('date') == tomorrow.strftime('%Y-%m-%d'), forecast))[0]
                        speech_responses = []
                        speech_responses.append(f"Tomorrow, it will be between {tomorrow_forecast.get('temp_min')}\u00B0F and {tomorrow_forecast.get('temp_max')}\u00B0F and {tomorrow_forecast.get('weather_description').lower()} in {city}.")
                        for day in forecast:
                            if day.get('date') != tomorrow.strftime('%Y-%m-%d'):
                                speech_responses.append(f"On {day.get('date')}, it will be between {day.get('temp_min')}\u00B0F and {day.get('temp_max')}\u00B0F and {day.get('weather_description').lower()} in {city}.")
                        return ' '.join(speech_responses)

            else:
                # General weather based on IP address location
                city = await city_from_ip()
                coords = await coords_from_city(city, api_key)
                if city is None:
                    return f"Could not determine your city based on your IP address. Please provide a city name."
                if coords is None:
                    return f"No weather data available for {city}."
                
                if api_key:
                    response = await session.get(f"http://api.openweathermap.org/data/3.0/onecall?lat={coords.get('lat')}&lon={coords.get('lon')}&appid={api_key}&units=imperial")
                    if response.status == 200:
                        json_response = await response.json()
                        logger.debug(json_response)
                        weather = json_response.get('current').get('weather')[0].get('main')
                        temp = json_response.get('current').get('temp')
                        return f"It is currently {round(float(temp))} degrees and {weather.lower()} in your location."
                
                # Fallback to Open-Meteo
                response = await session.get(f"https://api.open-meteo.com/v1/forecast?latitude={coords.get('lat')}&longitude={coords.get('lon')}&current_weather=true&temperature_unit=fahrenheit")
                if response.status == 200:
                    json_response = await response.json()
                    weather_code = json_response.get('current_weather').get('weathercode')
                    temp = json_response.get('current_weather').get('temperature')
                    weather_description = weather_codes[str(weather_code)]['day']['description'] if datetime.now().hour < 18 else weather_codes[str(weather_code)]['night']['description']
                    return f"It is currently {round(float(temp))} degrees and {weather_description.lower()} in {city}."
                
        raise Exception("No Open Weather API key found. Please enter your API key for Open Weather in the web interface or try reconnecting the service.")

    except Exception as e:
        if '404' in str(e):
            return f"Weather information for {city} is not available."
        else:
            logger.error(f"Error: {traceback.format_exc()}")
            return f"Something went wrong. {e}"

async def philips_hue_action(text: str):
    bridge_ip = os.getenv('PHILIPS_HUE_BRIDGE_IP')
    username = os.getenv('PHILIPS_HUE_USERNAME')
    
    if bridge_ip and username:
        try:
            b = Bridge(bridge_ip, username)
            b.connect()

            # Turn on or off all lights
            on_off_pattern = r'(\b(turn|shut|cut|put)\s)?.*(on|off)\b'
            match = re.search(on_off_pattern, text, re.IGNORECASE)
            if match:
                if 'on' in match.group(0):
                    b.set_group(0, 'on', True)
                    return "Turning on all lights."
                else:
                    b.set_group(0, 'on', False)
                    return "Turning off all lights."

            # Change light color
            color_pattern = r'\b(red|green|blue|yellow|purple|orange|pink|white|black)\b'
            match = re.search(color_pattern, text, re.IGNORECASE)
            if match:
                # convert color to hue value
                color = {
                    'red': 0,
                    'green': 25500,
                    'blue': 46920,
                    'yellow': 12750,
                    'purple': 56100,
                    'orange': 6000,
                    'pink': 56100,  # Closest to purple for hue
                    'white': 15330,  # Closest to a neutral white
                }.get(match.group(1).lower())
                b.set_group(0, 'on', True)
                b.set_group(0, 'hue', color)
                return f"Changing lights {match.group(1)}."

            # Change light brightness
            brightness_pattern = r'(\b(dim|brighten)\b)?.*?\s.*?to\s(\d{1,3})\b'
            match = re.search(brightness_pattern, text, re.IGNORECASE)
            if match:
                brightness = int(match.group(3))
                b.set_group(0, 'on', True)
                b.set_group(0, 'bri', brightness)
                return f"Setting brightness to {brightness}."

            raise Exception("I'm sorry, I don't know how to handle that request.")
        except Exception as e:
            logger.error(f"Error: {traceback.format_exc()}")
            return f"Something went wrong: {e}"
    
    raise Exception("No philips hue bridge IP found. Please enter your bridge IP for Phillips Hue in the web interface or try reconnecting the service.")

async def llm_action(text, retries=3):
    # Load settings from settings.json
    settings = load_settings()
    max_tokens = settings.get("max_tokens")
    temperature = settings.get("temperature")
    model = settings.get("model")

    for i in range(retries):
        try:
            response = completion(
                model=model,
                messages=[
                    {"role": "system", "content": f"You are a helpful assistant. {settings.get('custom_instructions')}"},
                    {"role": "user", "content": f"Human: {text}\nAI:"}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            response_content = response.choices[0].message.content.strip()
            if response_content:  # Check if the response is not empty
                return response_content
            else:
                logger.warning(f"Retry {i+1}: Received empty response from LLM.")
        except litellm.exceptions.BadRequestError as e:
            logger.error(traceback.format_exc())
            return f"The API key you provided for `{model}` is not valid. Double check the API key corresponds to the model/provider you are trying to call."
        except Exception as e:
            logger.error(f"Error on try {i+1}: {e}")
            if i == retries - 1:  # If this was the last retry
                return f"Something went wrong after {retries} retries: {e}\n{traceback.format_exc()}"
        await asyncio.sleep(0.5)  # Wait before retrying

alarms = {}

def set_alarm(command, minute, hour, day_of_month, month, day_of_week, comment):
    now = datetime.now()
    alarm_time = now.replace(minute=minute, hour=hour, day=day_of_month, month=month, second=0, microsecond=0)
    
    if alarm_time < now:
        alarm_time += timedelta(days=1)
    
    delay = (alarm_time - now).total_seconds()
    timer = Timer(delay, lambda: subprocess.Popen(command, shell=True))
    timer.start()
    alarms[comment] = timer
    return "Alarm set successfully."

def delete_alarm(comment):
    if comment in alarms:
        alarms[comment].cancel()
        del alarms[comment]
        return "Alarm deleted successfully."
    else:
        return "No such alarm to delete."

def snooze_alarm(comment, snooze_minutes):
    if comment in alarms:
        alarms[comment].cancel()
        del alarms[comment]
        
        now = datetime.now()
        snooze_time = now + timedelta(minutes=snooze_minutes)
        delay = (snooze_time - now).total_seconds()
        command = "aplay /usr/share/sounds/alarm.wav"
        timer = Timer(delay, lambda: subprocess.Popen(command, shell=True))
        timer.start()
        alarms[comment] = timer
        return "Alarm snoozed successfully."
    else:
        return "No such alarm to snooze."

def parse_time_expression(time_expression):
    if re.match(r'\d+:\d+', time_expression):  # HH:MM format
        hour, minute = map(int, time_expression.split(':'))
        return minute, hour, '*', '*', '*'
    elif re.match(r'\d+\s*minutes?', time_expression):  # N minutes from now
        minutes = int(re.search(r'\d+', time_expression).group())
        now = datetime.now() + timedelta(minutes=minutes)
        return now.minute, now.hour, now.day, now.month, '*'
    else:
        raise ValueError("Invalid time expression")

def set_reminder(command, minute, hour, day_of_month, month, day_of_week, comment):
    now = datetime.now()
    reminder_time = now.replace(minute=minute, hour=hour, day=day_of_month, month=month, second=0, microsecond=0)
    
    if reminder_time < now:
        reminder_time += timedelta(days=1)
    
    delay = (reminder_time - now).total_seconds()
    Timer(delay, lambda: subprocess.Popen(command, shell=True)).start()
    return "Reminder set successfully."

async def alarm_reminder_action(text):
    set_match = re.search(
        r'\b(?:set|create|schedule|wake\s+me\s+up)\s+(?:an\s+)?alarm\b.*?\b(?:for|in|at)\s*(\d{1,2}:\d{2}|\d+\s*(?:minutes?|mins?|hours?|hrs?))\b' +
        r'|\bwake\s+me\s+up\b.*?\b(?:in|at)\s*(\d{1,2}:\d{2}|\d+\s*(?:minutes?|mins?|hours?|hrs?))\b',
        text, 
        re.IGNORECASE
    )
    delete_match = re.search(
        r'\b(?:delete|remove|cancel)\s+(?:an\s+)?alarm\b.*?\b(?:called|named)\s*(\w+)', 
        text, 
        re.IGNORECASE
    )
    snooze_match = re.search(
        r'\b(?:snooze|delay|postpone)\s+(?:an\s+)?alarm\b.*?\b(?:for|by)\s*(\d+\s*(?:minutes?|mins?))\b', 
        text, 
        re.IGNORECASE
    )
    remind_match = re.search(
        r'\b(?:remind)\s+(?:me)\s+(?:to|in)\s*(\d+\s*(?:minutes?|mins?|hours?|hrs?))\s+to\s*(.+)', 
        text, 
        re.IGNORECASE
    )

    if set_match:
        # Check which group captured the time expression
        time_expression = set_match.group(1) or set_match.group(2)
        if time_expression is None:
            return "No time specified for the alarm."
        minute, hour, dom, month, dow = parse_time_expression(time_expression)
        command = "aplay /usr/share/sounds/alarm.wav"
        comment = "Alarm"
        return set_alarm(command, minute, hour, dom, month, dow, comment)
    elif delete_match:
        comment = delete_match.group(1)
        return delete_alarm(comment)
    elif snooze_match:
        snooze_time = snooze_match.group(1)
        snooze_minutes = int(re.search(r'\d+', snooze_time).group())
        comment = "Alarm"
        return snooze_alarm(comment, snooze_minutes)
    elif remind_match:
        time_expression = remind_match.group(1)
        reminder_text = remind_match.group(2)
        if time_expression is None:
            return "No time specified for the reminder."
        minute, hour, dom, month, dow = parse_time_expression(time_expression)
        command = f"""
bash -c 'source /env/bin/activate && python -c "import pyttsx3; 
engine = pyttsx3.init(); 
engine.setProperty(\\"rate\\", 145); 
engine.say(\\"Reminder: {reminder_text}\\"); 
engine.runAndWait()"'
        """
        comment = "Reminder"
        return set_reminder(command, minute, hour, dom, month, dow, comment)
    else:
        return "Invalid command."

async def caldav_action(text: str):
    url = os.getenv('CALDAV_URL')
    username = os.getenv('CALDAV_USERNAME')
    password = os.getenv('CALDAV_PASSWORD')

    if not url or not username or not password:
        return "CalDAV server credentials are not properly set in environment variables."

    try:
        client = caldav.DAVClient(url, username=username, password=password)
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return "No calendars found."

        calendar = calendars[0]  # Use the first found calendar

        task_create_match = re.search(r'\b(?:add|create)\s+a?\s+task\s+called\s+(.+)', text, re.IGNORECASE)
        task_delete_match = re.search(r'\b(?:delete|remove)\s+(a )?task\s+called\s+(\w+)', text, re.IGNORECASE)
        task_update_match = re.search(r'\b(?:update|change|modify)\s+(a )?task\s+called\s+(\w+)\s+to\s+(\w+)', text, re.IGNORECASE)
        tasks_query_match = re.search(r'\b(left|to do|to-do|what else)\b', text, re.IGNORECASE)
        completed_tasks_query_match = re.search(r'\bcompleted\s+tasks\b', text, re.IGNORECASE)

        if task_create_match:
            task_name = task_create_match.group(1).strip()
            task = calendar.add_todo(f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTODO
SUMMARY:{task_name}
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR
""")
            return f"Task '{task_name}' created successfully."

        elif task_update_match:
            task_name = task_update_match.group(2)
            new_task_name = task_update_match.group(3)
            tasks = calendar.todos()
            for task in tasks:
                if task_name.lower() in task.instance.vtodo.summary.value.lower():
                    task.instance.vtodo.summary.value = new_task_name
                    task.save()
                    return f"Task '{task_name}' updated to '{new_task_name}' successfully."

        elif task_delete_match:
            task_name = task_delete_match.group(1)
            tasks = calendar.todos()
            for task in tasks:
                if task_name.lower() in task.instance.vtodo.summary.value.lower():
                    task.delete()
                    return f"Task '{task_name}' deleted successfully."

        if tasks_query_match:
            tasks = calendar.todos()
            pending_task_details = []
            for task in tasks:
                if task.vobject_instance.vtodo.status.value != "COMPLETED":
                    summary = task.vobject_instance.vtodo.summary.value
                    status = task.vobject_instance.vtodo.status.value
                    pending_task_details.append(f"'{summary}' (Status: {status})")
            if pending_task_details:
                return "Your pending tasks are: " + ", ".join(pending_task_details)
            else:
                return "You have no pending tasks."

        elif completed_tasks_query_match:
            tasks = calendar.todos()
            completed_task_details = []
            for task in tasks:
                if task.vobject_instance.vtodo.status.value == "COMPLETED":
                    summary = task.vobject_instance.vtodo.summary.value
                    completed_task_details.append(f"'{summary}'")
            if completed_task_details:
                return "Your completed tasks are: " + ", ".join(completed_task_details)
            else:
                return "You have no completed tasks."

        create_match = re.search(r'\b(?:add|create|schedule)\s+an?\s+(event|appointment)\s+called\s+(\w+)\s+on\s+(\d{4}-\d{2}-\d{2})\s+at\s+(\d{1,2}:\d{2})', text, re.IGNORECASE)
        update_match = re.search(r'\b(?:update|change|modify)\s+the\s+(event|appointment)\s+called\s+(\w+)\s+to\s+(\w+)\s+on\s+(\d{4}-\d{2}-\d{2})\s+at\s+(\d{1,2}:\d{2})', text, re.IGNORECASE)
        delete_match = re.search(r'\b(?:delete|remove|cancel)\s+the\s+(event|appointment)\s+called\s+(\w+)', text, re.IGNORECASE)
        next_event_match = re.search(r"\bwhat'? ?i?s\s+my\s+next\s+(event|appointment)\b", text, re.IGNORECASE)
        calendar_query_match = re.search(r"\bwhat'? ?i?s\s+on\s+my\s+calendar\b", text, re.IGNORECASE)

        if create_match:
            event_name = create_match.group(1)
            event_time = datetime.strptime(f"{create_match.group(2)} {create_match.group(3)}", "%Y-%m-%d %H:%M")
            event_start = event_time.strftime("%Y%m%dT%H%M%S")
            event_end = (event_time + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")  # Assuming 1 hour duration

            event = calendar.add_event(f"""
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:{event_name}
DTSTART:{event_start}
DTEND:{event_end}
END:VEVENT
END:VCALENDAR
""")
            return f"Event '{event_name}' created successfully."

        elif update_match:
            event_name = update_match.group(2)
            new_event_name = update_match.group(3)
            event_time = datetime.strptime(f"{update_match.group(4)} {update_match.group(5)}", "%Y-%m-%d %H:%M")
            event_start = event_time.strftime("%Y%m%dT%H%M%S")
            event_end = (event_time + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")  # Assuming 1 hour duration

            events = calendar.search(start=datetime.now(), end=datetime.now() + timedelta(days=365), event=True, expand=True)  # Search within the next year
            for event in events:
                if event_name.lower() in event.instance.vevent.summary.value.lower():
                    event.instance.vevent.summary.value = new_event_name
                    event.instance.vevent.dtstart.value = event_start
                    event.instance.vevent.dtend.value = event_end
                    event.save()
                    return f"Event '{event_name}' updated to '{new_event_name}' successfully."

        elif delete_match:
            event_name = delete_match.group(1)
            events = calendar.search(start=datetime.now(), end=datetime.now() + timedelta(days=365), event=True, expand=True)  # Search within the next year
            for event in events:
                if event_name.lower() in event.instance.vevent.summary.value.lower():
                    event.delete()
                    return f"Event '{event_name}' deleted successfully."

        elif next_event_match:
            events = calendar.search(start=datetime.now(), end=datetime.now() + timedelta(days=30), event=True, expand=True)  # Next 30 days
            if events:
                next_event = events[0]
                summary = next_event.vobject_instance.vevent.summary.value
                start_time = next_event.vobject_instance.vevent.dtstart.value
                return f"Your next event is '{summary}' on {start_time.strftime('%A, %B %d at %I:%M %p').replace(' 0', ' ')}"
            else:
                return "No upcoming events found."

        elif calendar_query_match:
            events = calendar.search(start=datetime.now(), end=datetime.now() + timedelta(days=30), event=True, expand=True)  # Next 30 days
            if events:
                event_details = []
                for event in events:
                    summary = event.vobject_instance.vevent.summary.value
                    start_time = event.vobject_instance.vevent.dtstart.value
                    formatted_start_time = start_time.strftime('%A, %B %d at %I:%M %p').replace(' 0', ' ')
                    event_details.append(f"'{summary}' on {formatted_start_time}")
                return "Your upcoming events are: " + ", ".join(event_details)
            else:
                return "No events on your calendar for the next 30 days."
    except caldav.lib.error.AuthorizationError:
        return "Authorization failure: Please check your username and password."
    except caldav.lib.error.NotFoundError:
        return "Resource not found: Check the specified CalDAV URL."
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

    return "No valid CalDAV command found."
