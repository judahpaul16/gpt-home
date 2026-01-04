from langchain_core.tools import tool
from datetime import datetime, timedelta
from .env_utils import get_env
import caldav
import re


def _get_calendar():
    """Get CalDAV calendar connection."""
    url = get_env("CALDAV_URL")
    username = get_env("CALDAV_USERNAME")
    password = get_env("CALDAV_PASSWORD")
    
    if not all([url, username, password]):
        return None
    
    client = caldav.DAVClient(url, username=username, password=password)
    principal = client.principal()
    calendars = principal.calendars()
    
    return calendars[0] if calendars else None


@tool
def calendar_tool(command: str) -> str:
    """Manage calendar events and tasks.
    
    Args:
        command: Calendar command like "what's on my calendar", "add task called X",
                "what is left to do today", "schedule meeting on 2024-01-15 at 14:00"
    
    Returns:
        Information about calendar events or confirmation of changes
    """
    calendar = _get_calendar()
    
    if not calendar:
        return "Calendar is not configured. Please add your CalDAV credentials in settings."
    
    command_lower = command.lower()
    
    task_create = re.search(r'(?:add|create)\s+(?:a\s+)?task\s+(?:called\s+)?(.+)', command_lower)
    if task_create:
        task_name = task_create.group(1).strip()
        calendar.add_todo(f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTODO
SUMMARY:{task_name}
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR""")
        return f"Task '{task_name}' created successfully."
    
    if any(word in command_lower for word in ["left", "to do", "to-do", "pending", "what else"]):
        todos = calendar.todos()
        pending = [
            t.vobject_instance.vtodo.summary.value 
            for t in todos 
            if t.vobject_instance.vtodo.status.value != "COMPLETED"
        ]
        if pending:
            return f"Your pending tasks are: {', '.join(pending)}"
        return "You have no pending tasks."
    
    if "completed tasks" in command_lower:
        todos = calendar.todos()
        completed = [
            t.vobject_instance.vtodo.summary.value 
            for t in todos 
            if t.vobject_instance.vtodo.status.value == "COMPLETED"
        ]
        if completed:
            return f"Your completed tasks are: {', '.join(completed)}"
        return "You have no completed tasks."
    
    event_create = re.search(
        r'(?:schedule|add|create)\s+(?:an?\s+)?(?:event|meeting|appointment)\s+'
        r'(?:called\s+)?(.+?)\s+on\s+(\d{4}-\d{2}-\d{2})\s+at\s+(\d{1,2}:\d{2})',
        command_lower
    )
    if event_create:
        event_name = event_create.group(1).strip()
        event_date = event_create.group(2)
        event_time = event_create.group(3)
        
        event_dt = datetime.strptime(f"{event_date} {event_time}", "%Y-%m-%d %H:%M")
        event_start = event_dt.strftime("%Y%m%dT%H%M%S")
        event_end = (event_dt + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
        
        calendar.add_event(f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:{event_name}
DTSTART:{event_start}
DTEND:{event_end}
END:VEVENT
END:VCALENDAR""")
        return f"Event '{event_name}' scheduled for {event_date} at {event_time}."
    
    if any(phrase in command_lower for phrase in ["what's on", "what is on", "my calendar", "upcoming"]):
        events = calendar.search(
            start=datetime.now(),
            end=datetime.now() + timedelta(days=30),
            event=True,
            expand=True
        )
        if events:
            event_list = []
            for event in events[:5]:
                summary = event.vobject_instance.vevent.summary.value
                start = event.vobject_instance.vevent.dtstart.value
                formatted = start.strftime('%A, %B %d at %I:%M %p').replace(' 0', ' ')
                event_list.append(f"'{summary}' on {formatted}")
            return "Your upcoming events: " + ", ".join(event_list)
        return "No upcoming events in the next 30 days."
    
    if "next event" in command_lower or "next appointment" in command_lower:
        events = calendar.search(
            start=datetime.now(),
            end=datetime.now() + timedelta(days=30),
            event=True,
            expand=True
        )
        if events:
            event = events[0]
            summary = event.vobject_instance.vevent.summary.value
            start = event.vobject_instance.vevent.dtstart.value
            formatted = start.strftime('%A, %B %d at %I:%M %p').replace(' 0', ' ')
            return f"Your next event is '{summary}' on {formatted}."
        return "No upcoming events found."
    
    return "I didn't understand that calendar command. Try 'what's on my calendar' or 'add task called X'."
