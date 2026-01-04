from langchain_core.tools import tool
from datetime import datetime, timedelta
from threading import Timer
import subprocess
import re


_alarms: dict[str, Timer] = {}


def _parse_time_expression(time_expr: str) -> tuple[int, int, int, int, str]:
    """Parse time expression into minute, hour, day, month, weekday."""
    time_expr = time_expr.strip().lower()
    
    time_match = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)?', time_expr)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        meridiem = time_match.group(3)
        
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        
        now = datetime.now()
        return minute, hour, now.day, now.month, "*"
    
    minutes_match = re.search(r'(\d+)\s*(?:minutes?|mins?)', time_expr)
    if minutes_match:
        minutes = int(minutes_match.group(1))
        future = datetime.now() + timedelta(minutes=minutes)
        return future.minute, future.hour, future.day, future.month, "*"
    
    hours_match = re.search(r'(\d+)\s*(?:hours?|hrs?)', time_expr)
    if hours_match:
        hours = int(hours_match.group(1))
        future = datetime.now() + timedelta(hours=hours)
        return future.minute, future.hour, future.day, future.month, "*"
    
    raise ValueError(f"Could not parse time expression: {time_expr}")


def _play_alarm():
    """Play the alarm sound."""
    subprocess.Popen(["aplay", "/usr/share/sounds/alarm.wav"])


@tool
def alarm_tool(command: str) -> str:
    """Set, delete, or snooze alarms and reminders.
    
    Args:
        command: Alarm command like "set alarm for 7:00 AM", "wake me up in 30 minutes",
                "remind me in 10 minutes to take a break", "delete alarm", "snooze for 5 minutes"
    
    Returns:
        Confirmation message about the alarm action
    """
    command_lower = command.lower()
    
    set_match = re.search(
        r'(?:set|create|schedule|wake\s+me\s+up)\s+(?:an?\s+)?(?:alarm)?\s*'
        r'(?:for|in|at)\s+(.+?)(?:\s+to\s+|$)',
        command_lower
    )
    if set_match:
        time_expr = set_match.group(1).strip()
        try:
            minute, hour, day, month, _ = _parse_time_expression(time_expr)
            
            now = datetime.now()
            alarm_time = now.replace(minute=minute, hour=hour, second=0, microsecond=0)
            
            if alarm_time < now:
                alarm_time += timedelta(days=1)
            
            delay = (alarm_time - now).total_seconds()
            timer = Timer(delay, _play_alarm)
            timer.start()
            
            alarm_id = f"alarm_{alarm_time.strftime('%Y%m%d%H%M')}"
            _alarms[alarm_id] = timer
            
            formatted_time = alarm_time.strftime('%I:%M %p').lstrip('0')
            return f"Alarm set for {formatted_time}."
            
        except ValueError as e:
            return str(e)
    
    remind_match = re.search(
        r'remind\s+(?:me\s+)?(?:in\s+)?(.+?)\s+to\s+(.+)',
        command_lower
    )
    if remind_match:
        time_expr = remind_match.group(1).strip()
        reminder_text = remind_match.group(2).strip()
        
        try:
            minute, hour, day, month, _ = _parse_time_expression(time_expr)
            
            now = datetime.now()
            reminder_time = now.replace(minute=minute, hour=hour, second=0, microsecond=0)
            
            if "minute" in time_expr or "hour" in time_expr:
                pass
            elif reminder_time < now:
                reminder_time += timedelta(days=1)
            
            delay = (reminder_time - now).total_seconds()
            
            def speak_reminder():
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", 145)
                engine.say(f"Reminder: {reminder_text}")
                engine.runAndWait()
            
            timer = Timer(delay, speak_reminder)
            timer.start()
            
            reminder_id = f"reminder_{reminder_time.strftime('%Y%m%d%H%M')}"
            _alarms[reminder_id] = timer
            
            return f"I'll remind you to {reminder_text}."
            
        except ValueError as e:
            return str(e)
    
    if any(word in command_lower for word in ["delete", "cancel", "remove"]):
        if _alarms:
            for alarm_id, timer in list(_alarms.items()):
                timer.cancel()
            _alarms.clear()
            return "All alarms have been cancelled."
        return "No alarms to cancel."
    
    snooze_match = re.search(r'snooze.*?(\d+)', command_lower)
    if snooze_match:
        snooze_minutes = int(snooze_match.group(1))
        
        snooze_time = datetime.now() + timedelta(minutes=snooze_minutes)
        delay = snooze_minutes * 60
        
        timer = Timer(delay, _play_alarm)
        timer.start()
        
        alarm_id = f"snooze_{snooze_time.strftime('%Y%m%d%H%M')}"
        _alarms[alarm_id] = timer
        
        return f"Alarm snoozed for {snooze_minutes} minutes."
    
    return "I didn't understand that alarm command. Try 'set alarm for 7:00 AM' or 'remind me in 10 minutes to take a break'."
