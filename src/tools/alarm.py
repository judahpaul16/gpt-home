"""
Alarm and reminder tool for GPT Home.

Provides functionality to set, delete, and snooze alarms and reminders.
Uses the user's configured speech engine for reminder announcements.
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from threading import Timer

from langchain_core.tools import tool

_alarms: dict[str, Timer] = {}
SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"


def _load_settings() -> dict:
    """Load settings from settings.json."""
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _parse_time_expression(time_expr: str) -> datetime:
    """
    Parse time expression and return the target datetime directly.

    This avoids the bug where we parse to components and then reconstruct,
    which can cause timing issues with relative times like "in X minutes".
    """
    time_expr = time_expr.strip().lower()
    now = datetime.now()

    # Handle "in X minutes" or "X minutes"
    minutes_match = re.search(r"(\d+)\s*(?:minutes?|mins?)", time_expr)
    if minutes_match:
        minutes = int(minutes_match.group(1))
        return now + timedelta(minutes=minutes)

    # Handle "in X hours" or "X hours"
    hours_match = re.search(r"(\d+)\s*(?:hours?|hrs?)", time_expr)
    if hours_match:
        hours = int(hours_match.group(1))
        return now + timedelta(hours=hours)

    # Handle "in X hours and Y minutes" or similar
    hours_mins_match = re.search(
        r"(\d+)\s*(?:hours?|hrs?)\s*(?:and\s*)?(\d+)\s*(?:minutes?|mins?)", time_expr
    )
    if hours_mins_match:
        hours = int(hours_mins_match.group(1))
        minutes = int(hours_mins_match.group(2))
        return now + timedelta(hours=hours, minutes=minutes)

    # Handle absolute time like "7:00 AM" or "7:00"
    time_match = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)?", time_expr)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        meridiem = time_match.group(3)

        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If the time has already passed today, schedule for tomorrow
        if target <= now:
            target += timedelta(days=1)

        return target

    raise ValueError(f"Could not parse time expression: {time_expr}")


def _play_alarm():
    """Play the alarm sound."""
    subprocess.Popen(["aplay", "/usr/share/sounds/alarm.wav"])


def _speak_reminder(reminder_text: str):
    """
    Speak the reminder using the configured speech engine.

    Uses the same speech engine configured in settings.json.
    """
    settings = _load_settings()
    speech_engine = settings.get("ttsEngine", "gtts")

    print(f"[Reminder] Speaking reminder with engine: {speech_engine}", flush=True)
    print(f"[Reminder] Text: {reminder_text}", flush=True)

    if speech_engine == "litellm":
        # Use litellm TTS via the common speak function
        try:
            import asyncio

            from common import speak

            # Run async speak function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(speak(f"Reminder: {reminder_text}"))
            finally:
                loop.close()
            return
        except Exception as e:
            print(
                f"[Reminder] LiteLLM TTS failed: {e}, falling back to pyttsx3",
                flush=True,
            )

    elif speech_engine == "gtts":
        # Use Google TTS
        try:
            import tempfile

            from gtts import gTTS
            from pygame import mixer

            tts = gTTS(text=f"Reminder: {reminder_text}", lang="en")
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tts.save(tmp.name)
                mixer.init()
                mixer.music.load(tmp.name)
                mixer.music.play()
                while mixer.music.get_busy():
                    pass
                mixer.quit()
                os.unlink(tmp.name)
            return
        except Exception as e:
            print(f"[Reminder] gTTS failed: {e}, falling back to pyttsx3", flush=True)

    # Default to pyttsx3
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 145)
        engine.say(f"Reminder: {reminder_text}")
        engine.runAndWait()
    except Exception as e:
        print(f"[Reminder] pyttsx3 failed: {e}", flush=True)


@tool
def alarm_tool(command: str) -> str:
    """Set, delete, or snooze alarms and reminders.

    Args:
        command: Alarm command like "set alarm for 7:00 AM", "wake me up in 30 minutes",
                "remind me in 10 minutes to take a break", "delete alarm", "snooze for 5 minutes"

    Returns:
        Confirmation message about the alarm action
    """
    # Trigger timer/alarm animation on display
    try:
        from common import show_tool_animation_sync

        # Extract duration if present for countdown display
        duration = 0
        mins_match = re.search(r"(\d+)\s*(?:minutes?|mins?)", command.lower())
        hrs_match = re.search(r"(\d+)\s*(?:hours?|hrs?)", command.lower())
        if mins_match:
            duration += int(mins_match.group(1)) * 60
        if hrs_match:
            duration += int(hrs_match.group(1)) * 3600

        is_reminder = "remind" in command.lower()
        show_tool_animation_sync(
            "timer",
            {
                "duration": duration if duration > 0 else 0,
                "name": "Reminder" if is_reminder else "Alarm",
            },
        )
    except Exception:
        pass

    command_lower = command.lower()

    # Handle setting alarms
    set_match = re.search(
        r"(?:set|create|schedule|wake\s+me\s+up)\s+(?:an?\s+)?(?:alarm)?\s*"
        r"(?:for|in|at)\s+(.+?)(?:\s+to\s+|$)",
        command_lower,
    )
    if set_match:
        time_expr = set_match.group(1).strip()
        try:
            alarm_time = _parse_time_expression(time_expr)
            now = datetime.now()

            delay = (alarm_time - now).total_seconds()

            # Sanity check - delay should be positive
            if delay <= 0:
                return f"Cannot set alarm for a time in the past. Please specify a future time."

            timer = Timer(delay, _play_alarm)
            timer.start()

            alarm_id = f"alarm_{alarm_time.strftime('%Y%m%d%H%M%S')}"
            _alarms[alarm_id] = timer

            formatted_time = alarm_time.strftime("%I:%M %p").lstrip("0")

            # Calculate human-readable delay
            if delay < 60:
                delay_str = f"{int(delay)} seconds"
            elif delay < 3600:
                delay_str = f"{int(delay / 60)} minutes"
            else:
                hours = int(delay / 3600)
                mins = int((delay % 3600) / 60)
                delay_str = (
                    f"{hours} hours and {mins} minutes" if mins else f"{hours} hours"
                )

            print(
                f"[Alarm] Set for {alarm_time} (in {delay_str}, delay={delay}s)",
                flush=True,
            )
            return f"Alarm set for {formatted_time} (in {delay_str})."

        except ValueError as e:
            return str(e)

    # Handle reminders
    remind_match = re.search(
        r"remind\s+(?:me\s+)?(?:in\s+)?(.+?)\s+to\s+(.+)", command_lower
    )
    if remind_match:
        time_expr = remind_match.group(1).strip()
        reminder_text = remind_match.group(2).strip()

        try:
            reminder_time = _parse_time_expression(time_expr)
            now = datetime.now()

            delay = (reminder_time - now).total_seconds()

            # Sanity check - delay should be positive and reasonable
            if delay <= 0:
                return f"Cannot set reminder for a time in the past. Please specify a future time."

            if delay < 5:
                # If delay is less than 5 seconds, something is wrong
                return f"Reminder time is too soon ({delay:.1f}s). Please specify a longer time, like 'in 1 minute'."

            # Create a closure to capture reminder_text
            def make_reminder_callback(text):
                def callback():
                    _speak_reminder(text)

                return callback

            timer = Timer(delay, make_reminder_callback(reminder_text))
            timer.start()

            reminder_id = f"reminder_{reminder_time.strftime('%Y%m%d%H%M%S')}"
            _alarms[reminder_id] = timer

            # Calculate human-readable delay
            if delay < 60:
                delay_str = f"{int(delay)} seconds"
            elif delay < 3600:
                delay_str = f"{int(delay / 60)} minute{'s' if delay >= 120 else ''}"
            else:
                hours = int(delay / 3600)
                mins = int((delay % 3600) / 60)
                delay_str = f"{hours} hour{'s' if hours > 1 else ''}"
                if mins:
                    delay_str += f" and {mins} minute{'s' if mins > 1 else ''}"

            print(
                f"[Reminder] Set for {reminder_time} (in {delay_str}, delay={delay}s): {reminder_text}",
                flush=True,
            )
            return f"I'll remind you to {reminder_text} in {delay_str}."

        except ValueError as e:
            return str(e)

    # Handle deleting/cancelling alarms
    if any(word in command_lower for word in ["delete", "cancel", "remove"]):
        if _alarms:
            count = len(_alarms)
            for alarm_id, timer in list(_alarms.items()):
                timer.cancel()
            _alarms.clear()
            return f"Cancelled {count} alarm{'s' if count > 1 else ''}."
        return "No alarms to cancel."

    # Handle snoozing
    snooze_match = re.search(r"snooze.*?(\d+)", command_lower)
    if snooze_match:
        snooze_minutes = int(snooze_match.group(1))

        delay = snooze_minutes * 60

        timer = Timer(delay, _play_alarm)
        timer.start()

        snooze_time = datetime.now() + timedelta(minutes=snooze_minutes)
        alarm_id = f"snooze_{snooze_time.strftime('%Y%m%d%H%M%S')}"
        _alarms[alarm_id] = timer

        print(f"[Alarm] Snoozed for {snooze_minutes} minutes", flush=True)
        return f"Alarm snoozed for {snooze_minutes} minutes."

    return "I didn't understand that alarm command. Try 'set alarm for 7:00 AM' or 'remind me in 10 minutes to take a break'."
