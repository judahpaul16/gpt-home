import asyncio
import fcntl
import hashlib
import json
import logging
import os
import pty
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import termios
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import litellm
import psutil
import psycopg
import psycopg_pool
import requests
import spotipy
from dotenv import load_dotenv, set_key, unset_key
from fastapi import (
    FastAPI,
    File,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from phue import Bridge, PhueRequestTimeout
from spotipy.oauth2 import SpotifyClientCredentials
from sse_starlette.sse import EventSourceResponse

from src.common import SOURCE_DIR, load_integration_statuses, log_file_path, logger


class AccessLogFilter(logging.Filter):
    """Filter out noisy polling endpoint logs from uvicorn access log."""

    FILTERED_PATHS = [
        "/api/display/waveform/",
        "/api/display/activity",
        "/api/system/stats",
        "/api/system/processes",
        "/api/system/info",
        "/api/terminal/ws",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for path in self.FILTERED_PATHS:
            if path in msg:
                return False
        return True


logging.getLogger("uvicorn.access").addFilter(AccessLogFilter())

# Database configuration for gallery storage
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gpt_home:gpt_home_secret@db:5432/gpt_home",
)

_db_pool: Optional[psycopg_pool.AsyncConnectionPool] = None


async def get_db_pool() -> psycopg_pool.AsyncConnectionPool:
    """Get or create database connection pool."""
    global _db_pool
    if _db_pool is None:
        _db_pool = psycopg_pool.AsyncConnectionPool(
            DATABASE_URL, min_size=1, max_size=5, open=False
        )
        await _db_pool.open()
    return _db_pool


async def _init_tables():
    """Initialize gallery_images table if it doesn't exist."""
    pool = await get_db_pool()
    async with pool.connection() as conn:
        await conn.execute("""
                    CREATE TABLE IF NOT EXISTS gallery_images (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) UNIQUE NOT NULL,
                        data BYTEA NOT NULL,
                        mime_type VARCHAR(100) NOT NULL,
                        size INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

        await conn.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

        await conn.execute("""
                    CREATE TABLE IF NOT EXISTS integrations (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        fields JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        await conn.commit()


init = _init_tables()

# Suppress verbose LiteLLM callback logging (success_handler spam)
litellm.suppress_debug_info = True
litellm.set_verbose = False
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("LiteLLM Proxy").setLevel(logging.ERROR)
logging.getLogger("litellm").setLevel(logging.ERROR)

# Suppress sse_starlette debug logging (noisy SSE protocol messages)
logging.getLogger("sse_starlette").setLevel(logging.WARNING)
logging.getLogger("sse_starlette.sse").setLevel(logging.WARNING)

ROOT_DIR = SOURCE_DIR.parent
ENV_FILE_PATH = ROOT_DIR / ".env"
FRONTEND_ENV_PATH = SOURCE_DIR / "frontend" / ".env"

SPOTIFYD_DBUS_DEST = "org.mpris.MediaPlayer2.spotifyd"
SPOTIFYD_DBUS_PATH = "/org/mpris/MediaPlayer2"
SPOTIFYD_DBUS_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"


app = FastAPI()


# Docker container restart helpers (replaces legacy supervisorctl)
def restart_app_container():
    """Restart the GPT Home backend container via Docker."""
    try:
        # Try with -1 suffix first (docker-compose v2 naming)
        result = subprocess.run(
            ["docker", "restart", "gpt-home-backend-1"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Fallback to without suffix
            subprocess.run(
                ["docker", "restart", "gpt-home-backend-1"],
                capture_output=True,
                text=True,
                timeout=30,
            )
    except Exception as e:
        logger.warning(f"Failed to restart backend container: {e}")


def _update_spotifyd_config(username: str, password: str):
    """Update spotifyd configuration with Spotify credentials."""
    config_content = f"""[global]
backend = "alsa"
device_name = "GPT Home"
bitrate = 320
cache_path = "/root/.spotifyd/cache"
disable_discovery = false
zeroconf_port = 1234
use_mpris = true
dbus_type = "system"
initial_volume = 90
volume_controller = "softvol"
autoplay = true
enable_volume_normalisation = false
username = "{username}"
password = "{password}"
"""
    subprocess.run(
        [
            "sh",
            "-c",
            f"echo '{config_content}' > /root/.config/spotifyd/spotifyd.conf",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )


def restart_spotifyd_container():
    """Restart the spotifyd container via Docker."""
    try:
        result = subprocess.run(
            ["docker", "restart", "gpt-home-spotifyd-1"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            subprocess.run(
                ["docker", "restart", "gpt-home-spotifyd-1"],
                capture_output=True,
                text=True,
                timeout=30,
            )
    except Exception as e:
        logger.warning(f"Failed to restart spotifyd container: {e}")


def stop_spotifyd_container():
    """Stop the spotifyd container via Docker."""
    try:
        subprocess.run(
            ["docker", "stop", "gpt-home-spotifyd-1"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        try:
            subprocess.run(
                ["docker", "stop", "gpt-home-spotifyd-1"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            logger.warning(f"Failed to stop spotifyd container: {e}")


def start_spotifyd_container():
    """Start the spotifyd container via Docker."""
    try:
        subprocess.run(
            ["docker", "start", "gpt-home-spotifyd-1"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        try:
            subprocess.run(
                ["docker", "start", "gpt-home-spotifyd-1"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            logger.warning(f"Failed to start spotifyd container: {e}")


@app.post("/get-local-ip")
def get_local_ip():
    ip = "gpt-home.local"
    try:
        result = subprocess.run(
            ["docker", "exec", "gpt-home-spotifyd-1", "hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            ip = result.stdout.strip().split()[0]
    except Exception:
        pass
    return JSONResponse(content={"ip": ip})


@app.post("/api/settings/dark-mode")
async def toggle_dark_mode(request: Request):
    try:
        settings_path = SOURCE_DIR / "settings.json"

        with open(settings_path, "r") as f:
            settings = json.load(f)

        try:
            incoming_data = await request.json()
        except Exception:
            incoming_data = {}

        if "darkMode" in incoming_data:
            dark_mode = bool(incoming_data["darkMode"])
            settings["dark_mode"] = dark_mode

            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=2)

            return JSONResponse(content={"success": True, "darkMode": dark_mode})

        current_mode = settings.get("dark_mode", False)
        if isinstance(current_mode, str):
            current_mode = current_mode.lower() == "true"
        return JSONResponse(content={"darkMode": current_mode})

    except Exception as e:
        return JSONResponse(
            content={"error": str(e), "traceback": traceback.format_exc()},
            status_code=500,
        )


## Event Logs ##


@app.post("/logs")
def logs(request: Request):
    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("r") as f:
            log_data = f.read()
        return JSONResponse(content={"log_data": log_data.replace("`", "")})
    else:
        return Response(
            status_code=status.HTTP_404_NOT_FOUND, content="Log file not found"
        )


def is_start_of_new_log(line):
    return re.match(r"^(INFO|SUCCESS|DEBUG|ERROR|WARNING|CRITICAL):", line)


@app.post("/new-logs")
def last_logs(request: Request, last_line_number: Optional[int] = 0):
    if log_file_path.exists() and log_file_path.is_file():
        new_logs = []
        current_entry = []
        total_lines = 0
        with log_file_path.open("r") as f:
            for line in f:
                line = line.replace("`", "")
                if is_start_of_new_log(line):
                    if (
                        current_entry
                    ):  # If there's an accumulated entry, add it to new_logs
                        new_logs.append("".join(current_entry))
                        current_entry = []  # Reset for the next entry
                current_entry.append(line)
                total_lines += 1

            # Append the last accumulated entry if present
            if current_entry:
                new_logs.append("".join(current_entry))

        # Slice new_logs to only include entries after the last checked line number
        # Calculate where to start based on entries, not lines
        if last_line_number < len(new_logs):
            return JSONResponse(
                content={
                    "last_logs": new_logs[last_line_number:],
                    "new_last_line_number": len(new_logs),
                }
            )
        else:
            return JSONResponse(
                content={"last_logs": [], "new_last_line_number": len(new_logs)}
            )
    else:
        return Response(
            status_code=status.HTTP_404_NOT_FOUND, content="Log file not found"
        )


@app.post("/clear-logs")
def clear_logs(request: Request):
    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("w") as f:
            f.write("")
        return Response(status_code=status.HTTP_200_OK, content="Logs cleared")
    else:
        return Response(
            status_code=status.HTTP_404_NOT_FOUND, content="Log file not found"
        )


@app.get("/logs/stream")
async def stream_logs(request: Request, last_line_number: int = 0):
    """Stream new log entries via SSE."""

    async def generate():
        current_line = last_line_number

        while True:
            if await request.is_disconnected():
                break

            if log_file_path.exists() and log_file_path.is_file():
                all_entries = []
                current_entry = []

                with log_file_path.open("r") as f:
                    for line in f:
                        line = line.replace("`", "")
                        if is_start_of_new_log(line):
                            if current_entry:
                                all_entries.append("".join(current_entry))
                                current_entry = []
                            current_entry.append(line)
                        else:
                            current_entry.append(line)

                    if current_entry:
                        all_entries.append("".join(current_entry))

                while current_line < len(all_entries):
                    entry = all_entries[current_line]
                    log_type = entry.split(":")[0].lower() if ":" in entry else "info"
                    yield {
                        "event": "message",
                        "data": json.dumps({"content": entry, "type": log_type}),
                    }
                    current_line += 1

            await asyncio.sleep(1)

    # SSE best practice headers:
    # - X-Accel-Buffering: no - Prevents nginx from buffering the response
    # - Cache-Control: no-cache - Prevents caching of the stream
    return EventSourceResponse(
        generate(),
        ping=15,  # Send keepalive comment every 15 seconds (per W3C recommendation)
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


## Settings ##


@app.post("/api/settings")
async def settings(request: Request):
    settings_path = SOURCE_DIR / "settings.json"
    try:
        incoming_data = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse settings request JSON: {e}")
        return JSONResponse(
            content={"error": f"Invalid JSON in request: {e}"},
            status_code=400,
        )

    try:
        if "action" in incoming_data and incoming_data["action"] == "read":
            if settings_path.exists() and settings_path.is_file():
                with settings_path.open("r") as f:
                    file_settings = json.load(f)
                file_settings["litellm_api_key"] = os.getenv("LITELLM_API_KEY", "")
                return JSONResponse(content=file_settings)
            else:
                return JSONResponse(
                    content={"error": "Settings file not found"},
                    status_code=404,
                )

        elif "action" in incoming_data and incoming_data["action"] == "update":
            new_settings = incoming_data.get("data", {})
            if not isinstance(new_settings, dict):
                return JSONResponse(
                    content={"error": "Invalid data format - expected object"},
                    status_code=400,
                )

            if "litellm_api_key" in new_settings:
                val = new_settings.pop("litellm_api_key")
                try:
                    if val:
                        set_key(str(ENV_FILE_PATH), "LITELLM_API_KEY", val)
                    else:
                        unset_key(str(ENV_FILE_PATH), "LITELLM_API_KEY")
                except Exception as e:
                    logger.warning(f"Failed to update LITELLM_API_KEY env var: {e}")

            if "embedding_model" in new_settings:
                val = new_settings.get("embedding_model")
                if val:
                    try:
                        set_key(str(ENV_FILE_PATH), "EMBEDDING_MODEL", val)
                    except Exception as e:
                        logger.warning(f"Failed to update EMBEDDING_MODEL env var: {e}")

            boolean_fields = ["dark_mode", "sayHeard", "screensaver_enabled"]
            for field in boolean_fields:
                if field in new_settings:
                    val = new_settings[field]
                    if isinstance(val, str):
                        new_settings[field] = val.lower() == "true"

            existing_settings = {}
            if settings_path.exists() and settings_path.is_file():
                with settings_path.open("r") as f:
                    existing_settings = json.load(f)

            merged_settings = {**existing_settings, **new_settings}

            with settings_path.open("w") as f:
                json.dump(merged_settings, f, indent=2)

            # Apply runtime reloads for audio/speech after settings change
            try:
                from src.common import reload_speech_timing_settings

                reload_speech_timing_settings()
            except Exception as e:
                logger.warning(f"Failed to reload speech timing: {e}")

            # Reconfigure audio activity detector thresholds if provided in settings
            try:
                from src.audio_activity import get_audio_activity_detector

                detector = get_audio_activity_detector()
                vad_db = merged_settings.get("vadThresholdDb")
                show_th = merged_settings.get("waveformShowThreshold")
                hide_th = merged_settings.get("waveformHideThreshold")
                silence_rms = merged_settings.get("silenceRmsThreshold")
                grace = merged_settings.get("graceFrames")
                detector.configure(
                    vad_threshold_db=vad_db
                    if isinstance(vad_db, (int, float))
                    else None,
                    waveform_show_threshold=show_th
                    if isinstance(show_th, (int, float))
                    else None,
                    waveform_hide_threshold=hide_th
                    if isinstance(hide_th, (int, float))
                    else None,
                    silence_rms_threshold=int(silence_rms)
                    if isinstance(silence_rms, (int, float))
                    else None,
                    grace_frames=int(grace)
                    if isinstance(grace, (int, float))
                    else None,
                )
            except Exception as e:
                logger.debug(f"Audio detector reconfigure skipped: {e}")

            merged_settings["litellm_api_key"] = os.getenv("LITELLM_API_KEY", "")

            return JSONResponse(content=merged_settings)

        else:
            return JSONResponse(
                content={"error": "Invalid action - expected 'read' or 'update'"},
                status_code=400,
            )
    except PermissionError as e:
        logger.error(f"Permission denied saving settings: {e}")
        return JSONResponse(
            content={"error": f"Permission denied writing settings file: {e}"},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Failed to process settings: {e}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to save settings: {e}"},
            status_code=500,
        )


@app.post("/gptRestart")
async def gpt_restart(request: Request):
    """Restart the GPT Home backend container."""

    async def do_restart():
        await asyncio.sleep(0.5)
        restart_app_container()

    asyncio.create_task(do_restart())
    return JSONResponse(content={"success": True})


@app.post("/spotifyRestart")
async def spotify_restart(request: Request):
    """Restart the spotifyd container."""
    try:
        restart_spotifyd_container()
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Failed to restart spotifyd: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/reboot")
async def reboot(request: Request):
    # Reboot the host system (requires privileged container or host access)
    try:
        subprocess.run(
            [
                "nsenter",
                "--target",
                "1",
                "--mount",
                "--uts",
                "--ipc",
                "--net",
                "--pid",
                "--",
                "reboot",
            ]
        )
    except Exception:
        # Fallback for when nsenter isn't available
        subprocess.run(["reboot"])
    return JSONResponse(content={"success": True})


@app.post("/shutdown")
async def shutdown(request: Request):
    # Shutdown the host system (requires privileged container or host access)
    try:
        subprocess.run(
            [
                "nsenter",
                "--target",
                "1",
                "--mount",
                "--uts",
                "--ipc",
                "--net",
                "--pid",
                "--",
                "shutdown",
                "now",
            ]
        )
    except Exception:
        # Fallback for when nsenter isn't available
        subprocess.run(["shutdown", "now"])
    return JSONResponse(content={"success": True})


@app.post("/clearMemory")
async def clear_memory(request: Request):
    """Clear all conversation history and memories from the database."""
    try:
        import psycopg

        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://gpt_home:gpt_home_secret@localhost:5432/gpt_home",
        )

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                # Clear checkpoints (conversation history)
                cur.execute("TRUNCATE TABLE checkpoints CASCADE")
                # Clear checkpoint_blobs
                cur.execute("TRUNCATE TABLE checkpoint_blobs CASCADE")
                # Clear checkpoint_writes
                cur.execute("TRUNCATE TABLE checkpoint_writes CASCADE")
                # Clear store (memories)
                cur.execute("TRUNCATE TABLE store CASCADE")
            conn.commit()

        logger.info("Cleared all conversation history and memories")
        return JSONResponse(
            content={"success": True, "message": "Memory cleared successfully"}
        )
    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")
        return JSONResponse(
            status_code=500, content={"success": False, "message": str(e)}
        )


@app.get("/speechCapabilities")
async def speech_capabilities():
    """Return TTS/STT capabilities based on current API key."""
    try:
        from common import (
            get_litellm_provider,
            litellm_stt_available,
            litellm_tts_available,
        )

        return JSONResponse(
            content={
                "provider": get_litellm_provider(),
                "tts_available": litellm_tts_available(),
                "stt_available": litellm_stt_available(),
            }
        )
    except Exception as e:
        return JSONResponse(
            content={
                "provider": None,
                "tts_available": False,
                "stt_available": False,
            }
        )


@app.post("/availableModels")
async def available_models():
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    model_list = await response.json(content_type=None)
                    supported_models = [model for model in model_list.keys()]
                    return JSONResponse(content={"models": supported_models})
                else:
                    return JSONResponse(content={"models": []})
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching available models from LiteLLM")
        return JSONResponse(content={"models": []})
    except Exception as e:
        logger.warning(f"Error fetching available models: {e}")
        return JSONResponse(content={"models": []})


@app.post("/updateModel")
async def update_model(request: Request):
    try:
        import aiohttp

        incoming_data = await request.json()
        model_id = incoming_data["model_id"]

        # API key is now read from environment
        litellm.api_key = os.getenv("LITELLM_API_KEY", "")

        supported_models = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        model_list = await response.json(content_type=None)
                        supported_models = list(model_list.keys())
        except Exception as fetch_err:
            logger.warning(f"Could not fetch model list: {fetch_err}")
            # Allow setting any model if we can't verify
            supported_models = [model_id]

        if model_id in supported_models:
            settings_path = SOURCE_DIR / "settings.json"
            with settings_path.open("r") as f:
                settings = json.load(f)
            settings["model"] = model_id
            with settings_path.open("w") as f:
                json.dump(settings, f)

            # Settings are read from JSON at runtime - no restart needed

            return JSONResponse(content={"model": model_id})
        else:
            return HTTPException(
                status_code=400, detail=f"Model {model_id} not supported"
            )
    except Exception as e:
        return HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


## Password ##


# Background task for display auto-detection
_display_monitor_task = None
_last_display_state = None


async def _monitor_display_changes():
    """Background task to monitor for display connection changes."""
    global _last_display_state, _display_manager, _display_manager_initialized

    logger.debug("Display monitor started - checking for display changes")

    # Try to use udev for instant hotplug detection
    udev_monitor = None
    try:
        import pyudev

        context = pyudev.Context()
        udev_monitor = pyudev.Monitor.from_netlink(context)
        udev_monitor.filter_by(subsystem="drm")
        udev_monitor.start()
        logger.info("Display monitor: Using udev for instant hotplug detection")
    except ImportError:
        logger.debug("Display monitor: pyudev not available, using polling")
    except Exception as e:
        logger.debug(f"Display monitor: Could not initialize udev: {e}")

    async def check_and_reinit():
        """Check display state and reinitialize if needed."""
        global _last_display_state, _display_manager

        if _display_manager and _display_manager._screensaver_active:
            return

        from src.display.base import ScreenType
        from src.display.detection import detect_displays

        displays = detect_displays()
        full_displays = [d for d in displays if d.screen_type != ScreenType.I2C]

        # Create a hashable state representation
        current_state = tuple(
            (d.screen_type.value, d.width, d.height, d.device_path)
            for d in full_displays
        )

        # Only log and act if state actually changed
        if current_state != _last_display_state:
            old_count = len(_last_display_state) if _last_display_state else 0
            new_count = len(full_displays)

            if old_count != new_count:
                logger.info(
                    f"Display state changed: {new_count} full display(s) detected"
                )

            _last_display_state = current_state

            # If we now have full displays and didn't before, reinitialize
            if full_displays and _display_manager is not None and old_count == 0:
                try:
                    success = await _display_manager.reinitialize()
                    if success:
                        logger.info("Display auto-initialized after hotplug")
                        # Auto-select HDMI audio when display is connected
                        await _auto_select_hdmi_audio()
                except Exception as e:
                    logger.warning(f"Auto-reinitialize failed: {e}")
            elif old_count > 0 and new_count == 0:
                # Display was disconnected - reset HDMI audio state
                _reset_hdmi_audio_state()

    while True:
        try:
            if _display_manager and _display_manager._screensaver_active:
                await asyncio.sleep(1)
                continue

            if udev_monitor:
                import select

                loop = asyncio.get_event_loop()
                fd = udev_monitor.fileno()
                readable = await loop.run_in_executor(
                    None, lambda: select.select([fd], [], [], 0.5)[0]
                )
                if readable:
                    device = udev_monitor.poll(timeout=0)
                    if device:
                        logger.debug(
                            f"Display hotplug event: {device.action} {device.device_path}"
                        )
                        await asyncio.sleep(0.5)
                        await check_and_reinit()
                else:
                    await asyncio.sleep(4)
                    await check_and_reinit()
            else:
                await asyncio.sleep(5)
                await check_and_reinit()

        except asyncio.CancelledError:
            logger.debug("Display monitor stopped")
            break
        except Exception as e:
            logger.debug(f"Display monitor error: {e}")
            await asyncio.sleep(5)


async def _initialize_mic_gain():
    """Set mic gain to value from settings.json (default 18%)."""
    try:
        settings_path = SOURCE_DIR / "settings.json"
        target_gain = 18
        if settings_path.exists():
            with settings_path.open("r") as f:
                settings = json.load(f)
                target_gain = settings.get("micGain", 18)

        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        mic_card = None
        for line in result.stdout.split("\n"):
            if "card" in line.lower() and "usb" in line.lower():
                match = re.search(r"card\s+(\d+)", line)
                if match:
                    mic_card = match.group(1)
                    break

        if mic_card is None:
            for line in result.stdout.split("\n"):
                if "card" in line.lower():
                    match = re.search(r"card\s+(\d+)", line)
                    if match:
                        mic_card = match.group(1)
                        break

        if mic_card is None:
            return

        capture_controls = ["Capture", "Mic", "Input", "Digital"]

        for control in capture_controls:
            result = subprocess.run(
                ["amixer", "-c", mic_card, "sset", control, f"{target_gain}%"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info(f"Mic gain set to {target_gain}% on card {mic_card}")
                break
    except Exception as e:
        logger.debug(f"Could not initialize mic gain: {e}")


_voice_assistant_task = None


def ensure_dbus_policy():
    """Inject D-Bus policy into the host to fix ServiceUnknown errors."""
    policy_path = "/etc/dbus-1/system.d/spotifyd.conf"
    # Use a heredoc to prevent shell mangling of the XML
    policy_content = """<busconfig>
  <policy user="root">
    <allow own="org.mpris.MediaPlayer2.spotifyd"/>
    <allow send_destination="org.mpris.MediaPlayer2.spotifyd"/>
  </policy>
  <policy context="default">
    <allow send_destination="org.mpris.MediaPlayer2.spotifyd"/>
  </policy>
</busconfig>"""

    try:
        # Write the policy file to the host filesystem
        subprocess.run(
            [
                "nsenter",
                "--target",
                "1",
                "--mount",
                "--",
                "sh",
                "-c",
                f"cat <<EOF > {policy_path}\n{policy_content}\nEOF",
            ],
            check=True,
        )

        # Force the host D-Bus to reload its configuration
        subprocess.run(
            [
                "nsenter",
                "--target",
                "1",
                "--mount",
                "--",
                "dbus-send",
                "--system",
                "--type=method_call",
                "--dest=org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus.ReloadConfig",
            ],
            check=True,
        )

        logger.info("Successfully injected D-Bus policy for spotifyd")
        return True
    except Exception as e:
        logger.error(f"Failed to inject D-Bus policy: {e}")
        return False


@app.on_event("startup")
async def startup_event():
    ensure_dbus_policy()

    global _display_monitor_task, _voice_assistant_task

    # hashed password is now stored in the database (app_settings table).
    # No file should be created on startup.

    # Initialize database and migrate gallery images
    try:
        await get_db_pool()
        logger.info("Gallery database initialized")
    except Exception as e:
        logger.warning(f"Gallery database initialization failed: {e}")

    # Initialize display manager immediately on startup
    try:
        manager = await get_display_manager()
        if manager and manager.is_available:
            logger.info("Display manager initialized on startup")

            # Register display manager with common.py for direct access
            from src.common import set_display_manager

            set_display_manager(manager)

            # Auto-select HDMI audio when display is available on startup
            await _auto_select_hdmi_audio()

            # Start Spotify playback monitor
            start_spotify_monitor()
        else:
            logger.info("No display available on startup")
    except Exception as e:
        logger.warning(f"Display manager startup initialization failed: {e}")

    # Initialize _last_display_state so the monitor doesn't see a spurious "change"
    # on its first check and trigger a redundant reinitialize
    global _last_display_state
    try:
        from src.display.base import ScreenType
        from src.display.detection import detect_displays

        displays = detect_displays()
        full_displays = [d for d in displays if d.screen_type != ScreenType.I2C]
        _last_display_state = tuple(
            (d.screen_type.value, d.width, d.height, d.device_path)
            for d in full_displays
        )
    except Exception as e:
        logger.debug(f"Could not initialize _last_display_state: {e}")

    # Start display monitor background task
    _display_monitor_task = asyncio.create_task(_monitor_display_changes())

    # Initialize mic gain to recommended value if too low
    await _initialize_mic_gain()

    # Start voice assistant as background task (same process = shared display manager)
    from src.app import startup as voice_assistant_startup

    _voice_assistant_task = asyncio.create_task(voice_assistant_startup())


@app.on_event("shutdown")
async def shutdown_event():
    global _display_monitor_task, _voice_assistant_task

    if _voice_assistant_task:
        _voice_assistant_task.cancel()
        try:
            await _voice_assistant_task
        except asyncio.CancelledError:
            pass

    if _display_monitor_task:
        _display_monitor_task.cancel()
        try:
            await _display_monitor_task
        except asyncio.CancelledError:
            pass


def generate_hashed_password(password: str) -> str:
    sha256 = hashlib.sha256()
    sha256.update(password.encode("utf-8"))
    return sha256.hexdigest()


@app.post("/hashPassword")
async def hash_password_route(request: Request):
    try:
        incoming_data = await request.json()
        password = incoming_data["password"]
        hashed_password = generate_hashed_password(password)

        # Persist hashed password in the database
        try:
            pool = await get_db_pool()
            async with pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                    """,
                    ("hashed_password", hashed_password),
                )
                await conn.commit()
        except Exception:
            pass

        return JSONResponse(
            content={"success": True, "hashedPassword": hashed_password}
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e), "traceback": traceback.format_exc()}
        )


@app.post("/getHashedPassword")
async def get_hashed_password():
    try:
        # Fetch hashed password from the database (no file usage)
        pool = await get_db_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT value FROM app_settings WHERE key = %s",
                ("hashed_password",),
            )
            row = await cur.fetchone()
        hashed_password = row[0] if row else ""
        return JSONResponse(
            content={"success": True, "hashedPassword": hashed_password}
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e), "traceback": traceback.format_exc()}
        )


@app.post("/setHashedPassword")
async def set_hashed_password(request: Request):
    try:
        incoming_data = await request.json()
        new_hashed_password = incoming_data["hashedPassword"]

        # Store hashed password in the database
        pool = await get_db_pool()
        async with pool.connection() as conn:
            await conn.execute(
                """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                """,
                ("hashed_password", new_hashed_password),
            )
            await conn.commit()

        incoming_data = await request.json()

        old_password = incoming_data["oldPassword"]

        new_password = incoming_data["newPassword"]

        # Fetch stored hashed password from database
        pool = await get_db_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT value FROM app_settings WHERE key = %s",
                ("hashed_password",),
            )
            row = await cur.fetchone()
            stored_hashed_password = row[0] if row else ""

        provided_hashed_password = generate_hashed_password(old_password)

        if provided_hashed_password == stored_hashed_password:
            new_hashed_password = generate_hashed_password(new_password)

            # Store the new hashed password in database

            pool = await get_db_pool()
            async with pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                    """,
                    ("hashed_password", new_hashed_password),
                )
                await conn.commit()

            return JSONResponse(content={"success": True})
        else:
            return HTTPException(status_code=401, detail="Incorrect password")
    except Exception as e:
        return JSONResponse(
            content={"error": str(e), "traceback": traceback.format_exc()}
        )


## Integrations ##


@app.post("/connect-service")
async def connect_service(request: Request):
    try:
        incoming_data = await request.json()
        name = incoming_data["name"].lower().strip()
        fields = incoming_data["fields"]

        # Persist all integration fields in DB (JSONB)
        pool = await get_db_pool()
        async with pool.connection() as conn:
            await conn.execute(
                """
                    INSERT INTO integrations (name, fields, updated_at)
                    VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
                    ON CONFLICT (name)
                    DO UPDATE SET fields = EXCLUDED.fields, updated_at = CURRENT_TIMESTAMP
                """,
                (name, json.dumps(fields)),
            )
            await conn.commit()

        # Validate Spotify client credentials if provided
        if name == "spotify":
            spotify_client_id = fields.get("CLIENT ID")
            spotify_client_secret = fields.get("CLIENT SECRET")
            spotify_username = fields.get("USERNAME")
            spotify_password = fields.get("PASSWORD")

            if spotify_client_id and spotify_client_secret:
                try:
                    from spotipy.oauth2 import SpotifyClientCredentials

                    client_credentials_manager = SpotifyClientCredentials(
                        client_id=spotify_client_id, client_secret=spotify_client_secret
                    )
                    sp_test = spotipy.Spotify(
                        client_credentials_manager=client_credentials_manager
                    )
                    sp_test.search("test", limit=1, type="track")
                    logger.success("Spotify Client Credentials verified")
                except Exception as e:
                    logger.error(f"Spotify Client Credentials failed: {e}")
                    return JSONResponse(
                        content={"error": f"Invalid Spotify credentials: {e}"},
                        status_code=400,
                    )

            # Configure spotifyd if username/password present
            if spotify_username and spotify_password:
                try:
                    _update_spotifyd_config(spotify_username, spotify_password)
                    restart_spotifyd_container()
                    logger.success("Spotifyd configured with credentials")
                except Exception as e:
                    logger.warning(f"Failed to configure spotifyd: {e}")

        # If Philips Hue bridge IP was provided, attempt to establish username
        if name == "philipshue" and "BRIDGE IP ADDRESS" in fields:
            hue_result = await set_philips_hue_username(fields["BRIDGE IP ADDRESS"])
            if hue_result.status_code != 200:
                return hue_result

        logger.success(f"Successfully connected to {name}.")
        return JSONResponse(content={"success": True})

    except Exception as e:
        logger.error(f"Error: {traceback.format_exc()}")
        return JSONResponse(
            content={"error": str(e), "traceback": traceback.format_exc()}
        )


@app.post("/disconnect-service")
async def disconnect_service(request: Request):
    try:
        incoming_data = await request.json()
        name = incoming_data["name"].lower().strip()

        pool = await get_db_pool()
        async with pool.connection() as conn:
            await conn.execute("DELETE FROM integrations WHERE name = %s", (name,))
            await conn.commit()

        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(
            content={"error": str(e), "traceback": traceback.format_exc()}
        )


@app.post("/get-service-statuses")
async def get_service_statuses(_: Request):
    statuses = await load_integration_statuses()
    logger.debug(f"[get_service_statuses]: {statuses}")
    return JSONResponse(content={"statuses": statuses})


async def get_client_credentials_token():
    """Get a Spotify client using Client Credentials flow (for search only)."""
    client_id = None
    client_secret = None
    try:
        pool = await get_db_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT fields::text FROM integrations WHERE name = %s", ("spotify",)
            )
            row = await cur.fetchone()
        if row and row[0]:
            data = json.loads(row[0])
            client_id = data.get("CLIENT ID")
            client_secret = data.get("CLIENT SECRET")
    except Exception as e:
        logger.debug(f"Error loading Spotify credentials: {e}")

    if not client_id or not client_secret:
        return None

    try:
        client_credentials_manager = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret
        )
        sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
        return sp
    except Exception as e:
        logger.error(f"Error getting client credentials token: {e}")
        return None


def _run_dbus_command(
    method: str, args: list = None, retry_on_fail: bool = True
) -> tuple[bool, str]:
    """Run a D-Bus command to control spotifyd via MPRIS.

    If the command fails due to spotifyd not being available and retry_on_fail is True,
    attempts to restart spotifyd and retry once.
    """

    def _exec_dbus():
        cmd = [
            "dbus-send",
            "--system",
            "--print-reply",
            f"--dest={SPOTIFYD_DBUS_DEST}",
            SPOTIFYD_DBUS_PATH,
            f"{SPOTIFYD_DBUS_PLAYER_IFACE}.{method}",
        ]
        if args:
            cmd.extend(args)
        env = os.environ.copy()
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)

    try:
        result = _exec_dbus()
        if result.returncode == 0:
            return True, result.stdout

        error_msg = result.stderr

        if retry_on_fail and "ServiceUnknown" in error_msg:
            logger.warning("spotifyd not available on D-Bus, attempting restart...")
            try:
                restart_spotifyd_container()
                import time

                for attempt, delay in enumerate([3, 5, 7], 1):
                    time.sleep(delay)
                    result = _exec_dbus()
                    if result.returncode == 0:
                        logger.info(f"spotifyd ready after {attempt} attempt(s)")
                        return True, result.stdout

                logger.warning(f"D-Bus command failed after retries: {result.stderr}")
            except Exception as e:
                logger.error(f"Failed to restart spotifyd: {e}")

        logger.warning(f"D-Bus command failed: {error_msg}")
        return False, error_msg
    except subprocess.TimeoutExpired:
        return False, "D-Bus command timed out"
    except Exception as e:
        logger.error(f"D-Bus error: {e}")
        return False, str(e)


def mpris_play():
    """Resume playback via D-Bus MPRIS."""
    return _run_dbus_command("Play")


def mpris_pause():
    """Pause playback via D-Bus MPRIS."""
    return _run_dbus_command("Pause")


def mpris_play_pause():
    """Toggle play/pause via D-Bus MPRIS."""
    return _run_dbus_command("PlayPause")


def mpris_next():
    """Skip to next track via D-Bus MPRIS."""
    return _run_dbus_command("Next")


def mpris_previous():
    """Go to previous track via D-Bus MPRIS."""
    return _run_dbus_command("Previous")


def mpris_stop():
    """Stop playback via D-Bus MPRIS."""
    return _run_dbus_command("Stop")


def mpris_open_uri(spotify_uri: str):
    """Open a Spotify URI via D-Bus MPRIS."""
    return _run_dbus_command("OpenUri", [f"string:{spotify_uri}"])


def _run_dbus_command_set_property(prop: str, value: str) -> tuple[bool, str]:
    """Set a D-Bus property on spotifyd via MPRIS."""
    try:
        cmd = [
            "dbus-send",
            "--system",
            "--print-reply",
            f"--dest={SPOTIFYD_DBUS_DEST}",
            SPOTIFYD_DBUS_PATH,
            "org.freedesktop.DBus.Properties.Set",
            f"string:{SPOTIFYD_DBUS_PLAYER_IFACE}",
            f"string:{prop}",
            f"variant:{value}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return True, result.stdout
        else:
            logger.warning(f"D-Bus set property failed: {result.stderr}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "D-Bus command timed out"
    except Exception as e:
        logger.error(f"D-Bus error: {e}")
        return False, str(e)


# Spotify playback state cache
_spotify_playback_cache: Dict[str, Any] = {}
_spotify_last_check: float = 0
_spotify_monitor_task: Optional[asyncio.Task] = None


def _get_mpris_metadata() -> Optional[Dict[str, Any]]:
    """Get playback metadata from spotifyd via D-Bus MPRIS."""
    try:
        # Get Metadata property
        cmd = [
            "dbus-send",
            "--system",
            "--print-reply",
            f"--dest={SPOTIFYD_DBUS_DEST}",
            SPOTIFYD_DBUS_PATH,
            "org.freedesktop.DBus.Properties.Get",
            f"string:{SPOTIFYD_DBUS_PLAYER_IFACE}",
            "string:Metadata",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return None

        metadata_output = result.stdout

        # Get PlaybackStatus property
        cmd_status = [
            "dbus-send",
            "--system",
            "--print-reply",
            f"--dest={SPOTIFYD_DBUS_DEST}",
            SPOTIFYD_DBUS_PATH,
            "org.freedesktop.DBus.Properties.Get",
            f"string:{SPOTIFYD_DBUS_PLAYER_IFACE}",
            "string:PlaybackStatus",
        ]
        status_result = subprocess.run(
            cmd_status, capture_output=True, text=True, timeout=5
        )

        is_playing = False
        if status_result.returncode == 0 and "Playing" in status_result.stdout:
            is_playing = True

        if not is_playing:
            return None

        # Parse metadata from D-Bus output (basic parsing)
        track_name = "Unknown Track"
        artist_name = "Unknown Artist"
        album_name = "Unknown Album"
        album_art_url = None
        duration_ms = 0

        # Extract xesam:title
        if "xesam:title" in metadata_output:
            title_match = metadata_output.split("xesam:title")
            if len(title_match) > 1:
                # Look for string value after the key
                import re

                title_search = re.search(r'string\s+"([^"]*)"', title_match[1][:200])
                if title_search:
                    track_name = title_search.group(1)

        # Extract xesam:artist
        if "xesam:artist" in metadata_output:
            artist_match = metadata_output.split("xesam:artist")
            if len(artist_match) > 1:
                import re

                artist_search = re.search(r'string\s+"([^"]*)"', artist_match[1][:200])
                if artist_search:
                    artist_name = artist_search.group(1)

        # Extract xesam:album
        if "xesam:album" in metadata_output:
            album_match = metadata_output.split("xesam:album")
            if len(album_match) > 1:
                import re

                album_search = re.search(r'string\s+"([^"]*)"', album_match[1][:200])
                if album_search:
                    album_name = album_search.group(1)

        # Extract mpris:artUrl
        if "mpris:artUrl" in metadata_output:
            art_match = metadata_output.split("mpris:artUrl")
            if len(art_match) > 1:
                import re

                art_search = re.search(r'string\s+"([^"]*)"', art_match[1][:500])
                if art_search:
                    album_art_url = art_search.group(1)

        # Extract mpris:length (in microseconds)
        if "mpris:length" in metadata_output:
            length_match = metadata_output.split("mpris:length")
            if len(length_match) > 1:
                import re

                length_search = re.search(r"int64\s+(\d+)", length_match[1][:100])
                if length_search:
                    duration_ms = int(length_search.group(1)) // 1000

        return {
            "is_playing": True,
            "track": track_name,
            "artist": artist_name,
            "album": album_name,
            "album_art_url": album_art_url,
            "progress_ms": 0,  # Position requires separate D-Bus call
            "duration_ms": duration_ms,
            "progress_pct": 0,
        }
    except Exception as e:
        logger.debug(f"Error getting MPRIS metadata: {e}")
        return None


async def get_spotify_playback() -> Optional[Dict[str, Any]]:
    """Get current Spotify playback state via D-Bus MPRIS."""
    try:
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_mpris_metadata)
    except Exception as e:
        logger.debug(f"Error getting Spotify playback: {e}")
        return None


async def _spotify_monitor_loop():
    """Background task to monitor Spotify playback and update display."""
    global _spotify_playback_cache, _spotify_last_check

    logger.info("Spotify monitor started")
    last_playing = False

    while True:
        try:
            await asyncio.sleep(2)

            manager = _display_manager
            if manager and manager._screensaver_active:
                last_playing = False
                continue

            playback = await get_spotify_playback()
            _spotify_playback_cache = playback or {}
            _spotify_last_check = time.time()

            is_playing = playback is not None and playback.get("is_playing", False)

            if not manager or not manager.is_available:
                last_playing = is_playing
                continue

            if is_playing and playback:
                # Spotify is playing - show now playing display
                await manager.show_spotify_now_playing(
                    track=playback.get("track", "Unknown"),
                    artist=playback.get("artist", "Unknown"),
                    album=playback.get("album", ""),
                    album_art_url=playback.get("album_art_url"),
                    progress_pct=playback.get("progress_pct", 0),
                )
                last_playing = True
            elif last_playing and not is_playing:
                # Spotify stopped - return to idle
                await manager.stop_spotify_now_playing()
                last_playing = False

        except asyncio.CancelledError:
            logger.info("Spotify monitor cancelled")
            break
        except Exception as e:
            logger.debug(f"Spotify monitor error: {e}")
            await asyncio.sleep(5)


def start_spotify_monitor():
    """Start the Spotify playback monitor background task."""
    global _spotify_monitor_task
    if _spotify_monitor_task is None or _spotify_monitor_task.done():
        _spotify_monitor_task = asyncio.create_task(_spotify_monitor_loop())
        logger.info("Spotify monitor task created")


@app.get("/api/spotify/playback")
async def get_spotify_playback_state():
    """Get current Spotify playback state."""
    playback = await get_spotify_playback()
    if playback:
        return JSONResponse(content=playback)
    return JSONResponse(content={"is_playing": False})


@app.post("/spotify-control")
async def spotify_control(request: Request):
    """Control Spotify playback."""
    try:
        incoming_data = await request.json()
        text = incoming_data.get("text", "").lower().strip()

        sp_search = await get_client_credentials_token()

        if not sp_search:
            return JSONResponse(
                content={
                    "message": "Spotify not configured. Please add Client ID and Client Secret in the web interface."
                },
                status_code=400,
            )

        if "play" in text:
            song = re.sub(r"^play\s+", "", text)
            song = re.sub(r"\s+on\s+spotify$", "", song)
            song = song.strip()

            if song:
                spotify_uris, message = await spotify_get_track_uris(song, sp_search)

                if isinstance(spotify_uris, JSONResponse):
                    return spotify_uris

                if spotify_uris:
                    success, _ = mpris_open_uri(spotify_uris[0])
                    if success:
                        return JSONResponse(content={"message": message})
                    return JSONResponse(
                        content={
                            "message": f"Found: {message} - Could not start playback."
                        }
                    )
            else:
                success, _ = mpris_play()
                if success:
                    return JSONResponse(content={"message": "Resumed playback."})
                return JSONResponse(content={"message": "No active playback."})

        elif "next" in text or "skip" in text:
            success, _ = mpris_next()
            if success:
                return JSONResponse(content={"message": "Playing next track."})
            return JSONResponse(content={"message": "Could not skip track."})

        elif "previous" in text or "go back" in text:
            success, _ = mpris_previous()
            if success:
                return JSONResponse(content={"message": "Playing previous track."})
            return JSONResponse(content={"message": "Could not go back."})

        elif "pause" in text or "stop" in text:
            success, _ = mpris_pause()
            if success:
                return JSONResponse(content={"message": "Paused playback."})
            return JSONResponse(content={"message": "Could not pause."})

        elif "volume" in text:
            try:
                volume = int(re.search(r"\d+", text.split("volume", 1)[1]).group())
                volume = max(0, min(100, volume))
                mpris_volume = volume / 100.0
                success, _ = _run_dbus_command_set_property(
                    "Volume", f"double:{mpris_volume}"
                )
                if success:
                    return JSONResponse(
                        content={"message": f"Set volume to {volume}%."}
                    )
            except Exception as e:
                logger.error(f"Volume control error: {e}")
            return JSONResponse(content={"message": "Could not set volume."})

        elif "shuffle" in text:
            success, _ = _run_dbus_command_set_property("Shuffle", "boolean:true")
            if success:
                return JSONResponse(content={"message": "Shuffle enabled."})
            return JSONResponse(content={"message": "Could not enable shuffle."})

        elif "repeat" in text:
            success, _ = _run_dbus_command_set_property("LoopStatus", "string:Track")
            if success:
                return JSONResponse(content={"message": "Repeat track enabled."})
            return JSONResponse(content={"message": "Could not enable repeat."})

        elif "search" in text:
            # Pure search without playback
            query = re.sub(r"^search\s+(for\s+)?", "", text).strip()
            if query:
                results = sp_search.search(query, limit=5, type="track")
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    track_list = [
                        f"{t['name']} by {t['artists'][0]['name']}" for t in tracks[:5]
                    ]
                    return JSONResponse(
                        content={
                            "message": f"Found: {', '.join(track_list)}. Say 'play [song name]' to listen."
                        }
                    )
            return JSONResponse(content={"message": "No results found."})

        else:
            logger.warning(f"Invalid command: {text}")
            return JSONResponse(
                content={
                    "message": "Invalid command. Try: play [song], pause, next, previous, or search [query]."
                },
                status_code=400,
            )

    except Exception as e:
        logger.critical(f"Spotify control error: {traceback.format_exc()}")
        return JSONResponse(content={"message": f"Something went wrong: {e}"})


async def search_spotify(song: str, search_type: str, limit: int, sp):
    return sp.search(song, limit=limit, type=search_type)


async def get_podcast_episodes(show_id: str, sp):
    episodes = sp.show_episodes(show_id)
    return [episode["uri"] for episode in episodes["items"]]


async def get_album_tracks(album_id: str, sp):
    tracks = sp.album_tracks(album_id)
    return [track["uri"] for track in tracks["items"]]


async def get_artist_top_tracks(artist_id: str, sp):
    tracks = sp.artist_top_tracks(artist_id)
    return [track["uri"] for track in tracks["tracks"]]


async def get_track_recommendations(track_id: str, sp):
    recommendations = sp.recommendations(seed_tracks=[track_id])
    return [track["uri"] for track in recommendations["tracks"]]


async def spotify_get_track_uris(
    song: str, sp, search_types=["album", "artist", "track", "show"], limit=1
):
    for search_type in search_types:
        result = await search_spotify(song, search_type, limit, sp)

        if result[search_type + "s"]["items"]:
            item_id = result[search_type + "s"]["items"][0]["id"]
            item_name = result[search_type + "s"]["items"][0]["name"]

            if search_type == "album":
                message = f"Playing album '{item_name} by {result[search_type + 's']['items'][0]['artists'][0]['name']}'..."
                return (await get_album_tracks(item_id, sp), message)

            elif search_type == "artist":
                message = f"Playing top tracks based on artist '{item_name}'..."
                return (await get_artist_top_tracks(item_id, sp), message)

            elif search_type == "track":
                message = f"Playing radio based on track '{item_name}'..."
                recommended_uris = await get_track_recommendations(item_id, sp)
                return ([item_id] + recommended_uris, message)

            elif search_type == "show":
                message = f"Playing episodes from the show '{item_name}'..."
                return (await get_podcast_episodes(item_id, sp), message)

    return JSONResponse(content={"message": f"No match found for: {song}"})


## Philips Hue ##


def check_host_reachable(
    host: str, port: int = 80, timeout: float = 3.0
) -> tuple[bool, str]:
    """Check if a host is reachable on the network.

    Returns:
        Tuple of (is_reachable, error_message)
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            return True, ""
        else:
            return False, f"Connection refused (error code: {result})"
    except socket.timeout:
        return False, "Connection timed out"
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"
    except OSError as e:
        # Check for network unreachable errors
        if e.errno == 101:  # Network is unreachable
            return (
                False,
                "Network is unreachable - the bridge may be on a different subnet",
            )
        elif e.errno == 113:  # No route to host
            return (
                False,
                "No route to host - check if the IP address is correct and the bridge is on your network",
            )
        return False, f"Network error: {e}"


async def set_philips_hue_username(bridge_ip: str):
    """Connect to Philips Hue bridge and retrieve username.

    First checks network reachability before attempting phue connection
    to provide faster feedback on network issues.
    """
    # Quick network reachability check (3 second timeout)
    is_reachable, error_msg = check_host_reachable(bridge_ip, port=80, timeout=3.0)

    if not is_reachable:
        logger.warning(
            f"Philips Hue bridge at {bridge_ip} is not reachable: {error_msg}"
        )
        return JSONResponse(
            content={
                "message": f"Cannot reach Philips Hue bridge at {bridge_ip}. {error_msg}. "
                f"Please verify the IP address is correct and the bridge is on the same network.",
                "success": False,
            },
            status_code=408,
        )

    try:
        # Set a shorter socket timeout for the phue library
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(10.0)  # 10 second timeout for phue operations

        try:
            b = Bridge(bridge_ip)
            b.connect()
            b.get_api()
        finally:
            socket.setdefaulttimeout(original_timeout)

        logger.success("Successfully connected to Philips Hue bridge.")
        username = b.username

        # Persist bridge username to DB (do not write to .env)
        try:
            pool = await get_db_pool()
            async with pool.connection() as conn:
                # Merge existing fields (at least bridge IP) with username
                fields = {"BRIDGE IP ADDRESS": bridge_ip, "USERNAME": username}
                await conn.execute(
                    """
                    INSERT INTO integrations (name, fields, updated_at)
                    VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
                    ON CONFLICT (name)
                    DO UPDATE SET fields = EXCLUDED.fields, updated_at = CURRENT_TIMESTAMP
                    """,
                    ("philipshue", json.dumps(fields)),
                )
                await conn.commit()
        except Exception as db_err:
            logger.warning(f"Failed to persist Philips Hue username in DB: {db_err}")

        logger.success(f"Successfully set Philips Hue username to {username}.")
        return JSONResponse(
            content={
                "message": "Successfully connected to Philips Hue bridge.",
                "success": True,
            }
        )
    except PhueRequestTimeout:
        logger.warning(
            f"Philips Hue bridge at {bridge_ip} timed out during connection."
        )
        return JSONResponse(
            content={
                "message": f"Connection to Philips Hue bridge at {bridge_ip} timed out. "
                f"The bridge is reachable but not responding. Please try again.",
                "success": False,
            },
            status_code=408,
        )
    except Exception as e:
        error_msg = str(e)
        if "link button" in error_msg.lower():
            logger.info("Philips Hue bridge requires link button press.")
            return JSONResponse(
                content={
                    "message": "Please press the link button on your Philips Hue bridge and try again within 30 seconds.",
                    "success": False,
                },
                status_code=401,
            )
        logger.error(f"Philips Hue error: {error_msg}")
        return JSONResponse(
            content={
                "message": f"Failed to connect to Philips Hue: {error_msg}",
                "success": False,
            },
            status_code=500,
        )


## Display ##

_display_manager = None
_display_manager_initialized = False
_display_manager_lock = asyncio.Lock()


async def get_display_manager(force_refresh: bool = False):
    """Get or initialize the display manager.

    Args:
        force_refresh: If True, reinitialize to detect newly connected displays

    Returns:
        DisplayManager instance or None if no full display is available
    """
    global _display_manager, _display_manager_initialized

    # Fast path - already initialized
    if _display_manager_initialized and not force_refresh:
        return _display_manager

    # Use lock to prevent multiple concurrent initializations
    async with _display_manager_lock:
        # Double-check after acquiring lock
        if _display_manager_initialized and not force_refresh:
            return _display_manager

        if force_refresh:
            _display_manager_initialized = False
            if _display_manager is not None:
                try:
                    await _display_manager.reinitialize()
                    if _display_manager.is_available:
                        logger.info("Display manager reinitialized successfully")
                        return _display_manager
                    else:
                        logger.info("No full display found after refresh")
                        return _display_manager  # Return it anyway for status checks
                except Exception as e:
                    logger.error(f"Display manager reinitialization failed: {e}")
                    _display_manager = None

        if not _display_manager_initialized:
            try:
                from src.display import DisplayManager

                _display_manager = DisplayManager.get_instance()
                try:
                    success = await asyncio.wait_for(
                        _display_manager.initialize(), timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Display manager initialize() timed out after 10s")
                    success = False
                _display_manager_initialized = True
                if success:
                    logger.info("Display manager initialized successfully")
                else:
                    logger.warning(
                        "Display manager initialization returned False (no full display)"
                    )
                    # Don't set to None - keep it for status checks
            except Exception as e:
                logger.error(f"Display manager not available: {e}")
                logger.debug(traceback.format_exc())
                _display_manager_initialized = True  # Prevent repeated failures
                return None

        return _display_manager


@app.post("/api/display/refresh")
async def refresh_display():
    """Refresh display detection - call this after connecting/disconnecting displays.

    This endpoint triggers a rescan of connected displays and reinitializes
    the display manager if a new full display is found. Use this for hotswap
    support instead of restarting the entire service.
    """
    try:
        from src.display.base import ScreenType
        from src.display.detection import check_drm_status, detect_displays

        drm_status = check_drm_status()
        logger.info(f"DRM status: {drm_status}")

        displays = detect_displays()
        full_displays = [d for d in displays if d.screen_type != ScreenType.I2C]

        # Reinitialize display manager
        manager = await get_display_manager(force_refresh=True)

        if manager and manager.is_available and manager.display:
            display = manager.display
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"Display initialized: {display.info.screen_type.value} "
                    f"{display.width}x{display.height}",
                    "displays_found": len(displays),
                    "full_displays": len(full_displays),
                    "supports_modes": True,
                }
            )
        else:
            return JSONResponse(
                content={
                    "success": True,
                    "message": "No DRM display found. Check /dev/dri device permissions.",
                    "displays_found": len(displays),
                    "full_displays": len(full_displays),
                    "supports_modes": False,
                    "drm_status": drm_status,
                }
            )
    except Exception as e:
        logger.error(f"Display refresh failed: {e}")
        import traceback

        logger.debug(traceback.format_exc())
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@app.get("/api/display/debug")
async def display_debug():
    """Get DRM display debug information."""
    import subprocess
    from pathlib import Path

    from src.display.detection import check_drm_status

    debug_info = {
        "drm": check_drm_status(),
        "environment": {
            "SDL_VIDEODRIVER": os.environ.get("SDL_VIDEODRIVER"),
            "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR"),
        },
        "i2c": {},
    }

    if Path("/dev/i2c-1").exists():
        debug_info["i2c"]["bus_1_exists"] = True
        try:
            result = subprocess.run(
                ["i2cdetect", "-y", "1"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            debug_info["i2c"]["devices"] = (
                result.stdout if result.returncode == 0 else result.stderr
            )
        except Exception as e:
            debug_info["i2c"]["error"] = str(e)
    else:
        debug_info["i2c"]["bus_1_exists"] = False

    return JSONResponse(content=debug_info)


@app.post("/api/display/power-on")
async def display_power_on():
    """Check DRM display availability and reinitialize if needed."""
    try:
        from src.display.detection import check_drm_status

        status = check_drm_status()

        if status["available"]:
            manager = await get_display_manager(force_refresh=True)
            if manager and manager.is_available:
                return JSONResponse(
                    content={
                        "success": True,
                        "message": "DRM display available and initialized",
                        "drm_status": status,
                    }
                )
            return JSONResponse(
                content={
                    "success": True,
                    "message": "DRM devices found but display initialization failed",
                    "drm_status": status,
                }
            )

        return JSONResponse(
            content={
                "success": False,
                "message": "No DRM devices available. Check /dev/dri permissions.",
                "drm_status": status,
            },
            status_code=404,
        )
    except Exception as e:
        logger.exception("Display power-on failed")
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@app.get("/api/display/status")
async def display_status():
    """Get display status and capabilities.

    Returns information about connected displays, distinguishing between:
    - Full displays (TFT, HDMI): Support all display modes (SMART, CLOCK, etc.)
    - Simple displays (I2C): Text-only output for responses, no mode support

    The `supports_modes` field indicates if display mode controls should be shown.
    """
    try:
        from src.display.base import ScreenType
        from src.display.detection import (
            check_drm_status,
            detect_displays,
            get_display_info_string,
        )

        drm_status = check_drm_status()
        displays = detect_displays()
        manager = await get_display_manager()

        # Categorize displays
        full_displays = [d for d in displays if d.screen_type != ScreenType.I2C]
        simple_displays = [d for d in displays if d.screen_type == ScreenType.I2C]

        # Check if we have a full display that supports modes
        has_full_display = len(full_displays) > 0
        supports_modes = manager is not None and manager.supports_modes

        return JSONResponse(
            content={
                "available": len(displays) > 0,
                "displays": [
                    {
                        "type": d.screen_type.value,
                        "width": d.width,
                        "height": d.height,
                        "driver": d.driver,
                        "supports_modes": d.screen_type != ScreenType.I2C,
                    }
                    for d in displays
                ],
                "has_full_display": has_full_display,
                "has_simple_display": len(simple_displays) > 0,
                "supports_modes": supports_modes,
                "active": manager is not None and manager.is_available,
                "current_mode": manager.mode.name.lower()
                if manager and manager.is_available
                else None,
                "info": get_display_info_string(displays),
                "drm_status": drm_status,
                "note": "I2C displays are text-only and do not support display modes. "
                "If you connected an HDMI display, click 'Refresh Display' to detect it."
                if simple_displays and not full_displays
                else None,
            }
        )
    except Exception as e:
        return JSONResponse(
            content={
                "available": False,
                "displays": [],
                "has_full_display": False,
                "has_simple_display": False,
                "supports_modes": False,
                "active": False,
                "current_mode": None,
                "error": str(e),
            }
        )


@app.post("/api/display/mode")
async def set_display_mode(request: Request):
    """Set display mode (only for full displays).

    Display modes (SMART, CLOCK, WEATHER, GALLERY, WAVEFORM, OFF) are only
    supported on full displays (TFT, HDMI). I2C displays are simple
    text-only displays and do not support modes.
    """
    try:
        data = await request.json()
        mode_name = data.get("mode", "smart").lower()

        from src.display.base import DisplayMode

        mode_map = {
            "smart": DisplayMode.SMART,
            "clock": DisplayMode.CLOCK,
            "weather": DisplayMode.WEATHER,
            "gallery": DisplayMode.GALLERY,
            "waveform": DisplayMode.WAVEFORM,
            "off": DisplayMode.OFF,
        }

        mode = mode_map.get(mode_name)
        if not mode:
            return JSONResponse(
                content={"success": False, "message": f"Invalid mode: {mode_name}"},
                status_code=400,
            )

        # Check if we have a display that supports modes
        manager = await get_display_manager()
        if manager and not manager.supports_modes:
            return JSONResponse(
                content={
                    "success": False,
                    "message": "Display modes not supported - I2C display is text-only",
                },
                status_code=400,
            )

        # Save settings first (even without display)
        settings_path = SOURCE_DIR / "settings.json"
        try:
            if settings_path.exists():
                with settings_path.open("r") as f:
                    settings = json.load(f)
            else:
                settings = {}
            settings["display_mode"] = mode_name
            with settings_path.open("w") as f:
                json.dump(settings, f, indent=2)
        except Exception as settings_err:
            logger.warning(f"Could not save display mode to settings: {settings_err}")

        # Try to apply to display if available
        manager = await get_display_manager()
        if manager and manager.is_available:
            # If switching to weather mode, fetch current weather data
            if mode == DisplayMode.WEATHER:
                try:
                    await _fetch_and_set_weather_data(manager)
                except Exception as weather_err:
                    logger.warning(
                        f"Could not fetch weather for display: {weather_err}"
                    )

            await manager.set_mode(mode)
            return JSONResponse(content={"success": True, "mode": mode_name})
        else:
            # Settings saved but no display to apply to
            return JSONResponse(
                content={
                    "success": True,
                    "mode": mode_name,
                    "warning": "Settings saved but no display connected",
                }
            )
    except Exception as e:
        logger.error(f"Failed to set display mode: {e}")
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


async def _fetch_and_set_weather_data(manager):
    """Fetch weather data and update the display manager.

    Uses OpenWeatherMap if API key is set, otherwise falls back to Open-Meteo (free, no key required).
    """
    import aiohttp

    from src.common import load_settings

    settings = load_settings()
    lat = settings.get("lat")
    lon = settings.get("lon")
    city = settings.get("city", "")

    # Try IP geolocation if lat/lon not set
    if not lat or not lon:
        try:
            async with aiohttp.ClientSession() as session:
                geo_response = await session.get(
                    "http://ip-api.com/json/?fields=lat,lon,city", timeout=5
                )
                if geo_response.status == 200:
                    geo_data = await geo_response.json()
                    lat = geo_data.get("lat")
                    lon = geo_data.get("lon")
                    if not city:
                        city = geo_data.get("city", "")
                    logger.debug(
                        f"Weather: Got location from IP: {city} ({lat}, {lon})"
                    )
        except Exception as geo_err:
            logger.warning(f"Weather: IP geolocation failed: {geo_err}")

    if not lat or not lon:
        logger.warning("Weather: Could not determine location")
        return

    # Read OpenWeather API key from database integrations table (not env)
    api_key = None
    try:
        pool = await get_db_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT fields::text FROM integrations WHERE name = %s",
                ("openweather",),
            )
            row = await cur.fetchone()
            if row and row[0]:
                data = json.loads(row[0])
                api_key = data.get("API KEY")
    except Exception:
        api_key = None

    async with aiohttp.ClientSession() as session:
        # Try OpenWeatherMap first if API key is set
        if api_key:
            try:
                response = await session.get(
                    f"https://api.openweathermap.org/data/3.0/onecall?"
                    f"lat={lat}&lon={lon}&appid={api_key}&units=imperial",
                    timeout=10,
                )
                if response.status == 200:
                    data = await response.json()
                    current = data.get("current", {})
                    weather_info = current.get("weather", [{}])[0]
                    daily = data.get("daily", [])

                    forecast = []
                    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
                    for i, day_data in enumerate(daily[:7]):
                        from datetime import datetime

                        dt = datetime.fromtimestamp(day_data.get("dt", 0))
                        day_weather = day_data.get("weather", [{}])[0]
                        forecast.append(
                            {
                                "day": day_names[dt.weekday()] if i > 0 else "Today",
                                "high": round(day_data.get("temp", {}).get("max", 0)),
                                "low": round(day_data.get("temp", {}).get("min", 0)),
                                "condition": day_weather.get("main", "Clear"),
                            }
                        )

                    today = daily[0] if daily else {}
                    manager.set_weather_data(
                        {
                            "temperature": round(current.get("temp", 0)),
                            "condition": weather_info.get("main", "Clear"),
                            "location": city,
                            "high": round(today.get("temp", {}).get("max", 0))
                            if today
                            else None,
                            "low": round(today.get("temp", {}).get("min", 0))
                            if today
                            else None,
                            "forecast": forecast,
                        }
                    )
                    return
                else:
                    logger.warning(
                        f"Weather: OpenWeatherMap returned {response.status}, falling back to Open-Meteo"
                    )
            except Exception as owm_err:
                logger.warning(
                    f"Weather: OpenWeatherMap failed: {owm_err}, falling back to Open-Meteo"
                )

        # Fallback to Open-Meteo (free, no API key required)
        try:
            response = await session.get(
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,weather_code"
                f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
                f"&temperature_unit=fahrenheit"
                f"&timezone=auto",
                timeout=10,
            )
            if response.status == 200:
                data = await response.json()
                current = data.get("current", {})
                temp = current.get("temperature_2m")
                weather_code = current.get("weather_code", 0)
                condition = _wmo_code_to_condition(weather_code)

                daily = data.get("daily", {})
                dates = daily.get("time", [])
                highs = daily.get("temperature_2m_max", [])
                lows = daily.get("temperature_2m_min", [])
                codes = daily.get("weather_code", [])

                forecast = []
                day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                for i in range(min(7, len(dates))):
                    try:
                        from datetime import datetime

                        dt = datetime.strptime(dates[i], "%Y-%m-%d")
                        day_name = "Today" if i == 0 else day_names[dt.weekday()]
                        forecast.append(
                            {
                                "day": day_name,
                                "high": round(highs[i]) if i < len(highs) else None,
                                "low": round(lows[i]) if i < len(lows) else None,
                                "condition": _wmo_code_to_condition(
                                    codes[i] if i < len(codes) else 0
                                ),
                            }
                        )
                    except (ValueError, IndexError):
                        continue

                today_high = round(highs[0]) if highs else None
                today_low = round(lows[0]) if lows else None

                manager.set_weather_data(
                    {
                        "temperature": round(temp) if temp is not None else None,
                        "condition": condition,
                        "location": city,
                        "high": today_high,
                        "low": today_low,
                        "forecast": forecast,
                    }
                )
            else:
                logger.warning(f"Weather: Open-Meteo returned {response.status}")
        except Exception as om_err:
            logger.warning(f"Weather: Open-Meteo failed: {om_err}")


def _wmo_code_to_condition(code: int) -> str:
    """Convert WMO weather code to simple condition string."""
    # https://open-meteo.com/en/docs - WMO Weather interpretation codes
    if code == 0:
        return "Clear"
    elif code in (1, 2, 3):
        return "Cloudy"
    elif code in (45, 48):
        return "Fog"
    elif code in (51, 53, 55, 56, 57):
        return "Drizzle"
    elif code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    elif code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    elif code in (95, 96, 99):
        return "Thunderstorm"
    else:
        return "Clear"


@app.post("/api/display/test")
async def test_display():
    try:
        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(
                content={"success": False, "message": "No display available"},
                status_code=404,
            )

        await manager.show_user_message("GPT Home Display Test!", duration=5)
        return JSONResponse(
            content={"success": True, "message": "Test message displayed"}
        )
    except Exception as e:
        logger.error(f"Display test failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@app.post("/api/display/user-message")
async def display_user_message(request: Request):
    """Show a user message bubble on the display (SMART mode only)."""
    try:
        data = await request.json()
        message = data.get("message", "")
        duration = data.get("duration", 1.2)
        print(
            f"[API] /api/display/user-message: message='{message[:50]}...' duration={duration}",
            flush=True,
        )

        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        print(
            f"[API] user-message: mode={manager.mode}, calling show_user_message()",
            flush=True,
        )
        await manager.show_user_message(message, duration=duration)
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Display user message failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/tool-animation")
async def display_tool_animation(request: Request):
    """Show a tool-specific animation on the display (SMART mode only)."""
    try:
        data = await request.json()
        tool_name = data.get("tool_name", "")
        context = data.get("context", {})
        user_message = data.get("user_message")
        print(
            f"[API] /api/display/tool-animation: tool={tool_name} context={context}",
            flush=True,
        )

        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        print(
            f"[API] tool-animation: mode={manager.mode}, calling show_tool_animation()",
            flush=True,
        )
        await manager.show_tool_animation(tool_name, context, user_message)
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Display tool animation failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/waveform/start")
async def display_waveform_start(request: Request):
    """Start waveform visualization for microphone input.

    Note: Waveform will not start if a tool animation is currently active.
    """
    try:
        source = "microphone"

        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        if manager.has_tool_animation:
            return JSONResponse(
                content={
                    "success": True,
                    "skipped": True,
                    "reason": "tool_animation_active",
                }
            )

        await manager.start_waveform(source=source)
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Start waveform failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


# Rate limiting for waveform updates to reduce log spam and load
_last_waveform_update = 0.0
_waveform_update_min_interval = 0.05  # 20fps max


@app.post("/api/display/waveform/update")
async def display_waveform_update(request: Request):
    """Update waveform amplitude during TTS playback.

    Note: This endpoint is rate-limited to reduce load. When real-time audio
    capture is active, the display manager receives amplitude data directly.
    """
    global _last_waveform_update

    try:
        # Rate limit to reduce load and log spam
        current_time = time.time()
        if current_time - _last_waveform_update < _waveform_update_min_interval:
            return JSONResponse(content={"success": True, "throttled": True})
        _last_waveform_update = current_time

        data = await request.json()
        amplitude = data.get("amplitude", 0.0)

        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        await manager.update_waveform(amplitude)
        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/waveform/amplitude")
async def display_waveform_amplitude(request: Request):
    """Receive 32 waveform amplitude values from app.py during listening."""
    try:
        data = await request.json()
        values = data.get("values", [])

        if not values or len(values) != 32:
            return JSONResponse(
                content={"success": False, "error": "Expected 32 values"},
                status_code=400,
            )

        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        manager.set_waveform_values(values)
        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/waveform/stop")
async def display_waveform_stop():
    """Stop waveform visualization and return to idle."""
    try:
        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        await manager.stop_waveform()
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Stop waveform failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/activity")
async def display_register_activity():
    """Register user activity to reset screensaver timer."""
    try:
        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        await manager.register_activity_async()
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Register activity failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/response")
async def display_response_animation(request: Request):
    """Show response animation on the display (SMART mode only)."""
    try:
        data = await request.json()
        response = data.get("response", "")

        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        await manager.show_response_animation(response)
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Display response animation failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/resume-idle")
async def display_resume_idle():
    """Resume idle state (clock display in SMART mode)."""
    try:
        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(content={"success": False}, status_code=404)

        await manager.resume_idle()
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Resume idle failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


# -------------------------------------------------------------------------
# Screensaver Endpoints
# -------------------------------------------------------------------------


@app.get("/api/display/screensaver/status")
async def screensaver_status():
    """Get screensaver status and settings.

    The screensaver is a protection layer that works across all display modes.
    When active, it pauses the current mode and shows the screensaver animation.
    User activity (speech, interactions) deactivates it and resumes the previous mode.
    """
    try:
        from src.common import load_settings

        settings = load_settings()

        manager = await get_display_manager()
        is_active = False
        time_until_activation = None
        current_mode = None

        if manager and manager.is_available:
            is_active = manager._screensaver_active
            current_mode = manager.mode.name if manager.mode else None
            if not is_active and settings.get("screensaver_enabled", True):
                elapsed = time.time() - manager._last_activity_time
                timeout = float(settings.get("screensaver_timeout", 300))
                time_until_activation = max(0, timeout - elapsed)

        return JSONResponse(
            content={
                "success": True,
                "enabled": settings.get("screensaver_enabled", True),
                "timeout": settings.get("screensaver_timeout", 300),
                "style": settings.get("screensaver_style", "starfield"),
                "is_active": is_active,
                "current_mode": current_mode,
                "time_until_activation": time_until_activation,
                "available_styles": ["starfield", "matrix", "bounce", "fade"],
            }
        )
    except Exception as e:
        logger.error(f"Screensaver status failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/screensaver/settings")
async def set_screensaver_settings(request: Request):
    """Update screensaver settings."""
    try:
        from src.common import load_settings, save_settings

        data = await request.json()
        settings = load_settings()

        if "enabled" in data:
            settings["screensaver_enabled"] = bool(data["enabled"])
        if "timeout" in data:
            settings["screensaver_timeout"] = int(data["timeout"])
        if "style" in data:
            valid_styles = ["starfield", "matrix", "bounce", "fade"]
            style = data["style"].lower()
            if style in valid_styles:
                settings["screensaver_style"] = style

        save_settings(settings)

        manager = await get_display_manager()
        if manager and manager.is_available:
            old_enabled = manager._screensaver_enabled
            manager._load_screensaver_settings()

            if manager._screensaver_enabled and not old_enabled:
                if (
                    manager._screensaver_task is None
                    or manager._screensaver_task.done()
                ):
                    import asyncio

                    manager._screensaver_task = asyncio.create_task(
                        manager._screensaver_monitor_loop()
                    )
            elif not manager._screensaver_enabled and old_enabled:
                if manager._screensaver_task and not manager._screensaver_task.done():
                    manager._screensaver_task.cancel()

        return JSONResponse(
            content={
                "success": True,
                "message": "Screensaver settings updated",
                "settings": {
                    "enabled": settings.get("screensaver_enabled", True),
                    "timeout": settings.get("screensaver_timeout", 300),
                    "style": settings.get("screensaver_style", "starfield"),
                },
            }
        )
    except Exception as e:
        logger.error(f"Set screensaver settings failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/screensaver/activate")
async def activate_screensaver():
    """Manually activate the screensaver.

    The screensaver will pause the current display mode and show the
    screensaver animation. The previous mode will resume when the user
    interacts (speech, etc.) or when deactivate is called.
    """
    try:
        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(
                content={"success": False, "message": "No display available"},
                status_code=404,
            )

        # Activate screensaver (pauses current mode)
        if not manager._screensaver_active:
            await manager._activate_screensaver()

        return JSONResponse(
            content={
                "success": True,
                "message": "Screensaver activated",
                "paused_mode": manager.mode.name if manager.mode else None,
            }
        )
    except Exception as e:
        logger.error(f"Activate screensaver failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/screensaver/deactivate")
async def deactivate_screensaver():
    """Manually deactivate the screensaver and return to previous mode.

    This resumes whatever display mode was active before the screensaver
    started (SMART, CLOCK, WEATHER, GALLERY, WAVEFORM, etc.)
    """
    try:
        manager = await get_display_manager()
        if not manager or not manager.is_available:
            return JSONResponse(
                content={"success": False, "message": "No display available"},
                status_code=404,
            )

        resumed_mode = manager.mode.name if manager.mode else None

        if manager._screensaver_active:
            # Register activity to reset timer and deactivate screensaver
            manager.register_activity()

        return JSONResponse(
            content={
                "success": True,
                "message": "Screensaver deactivated",
                "resumed_mode": resumed_mode,
            }
        )
    except Exception as e:
        logger.error(f"Deactivate screensaver failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.post("/api/display/screensaver/poke")
async def poke_screensaver():
    """Reset the screensaver inactivity timer without deactivating screensaver."""
    try:
        manager = await get_display_manager()
        if manager and manager.is_available:
            # Only reset the timer, don't deactivate screensaver
            manager._last_activity_time = time.time()
            return JSONResponse(content={"success": True, "message": "Timer reset"})
        return JSONResponse(content={"success": True, "message": "No display manager"})
    except Exception as e:
        logger.error(f"Poke screensaver failed: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )


@app.get("/api/gallery/images")
async def list_gallery_images():
    try:
        pool = await get_db_pool()
        async with pool.connection() as conn:
            result = await conn.execute(
                """SELECT filename, size, updated_at FROM gallery_images
                   ORDER BY updated_at DESC"""
            )
            rows = await result.fetchall()

        return JSONResponse(
            content={
                "success": True,
                "images": [
                    {
                        "name": row[0],
                        "path": f"/api/gallery/{row[0]}",
                        "size": row[1],
                    }
                    for row in rows
                ],
            }
        )
    except Exception as e:
        logger.error(f"Failed to list gallery images: {e}")
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@app.post("/api/gallery/upload")
async def upload_gallery_image(file: UploadFile = File(...)):
    try:
        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        ext = Path(file.filename).suffix.lower()

        if ext not in allowed_extensions:
            return JSONResponse(
                content={"success": False, "message": f"Invalid file type: {ext}"},
                status_code=400,
            )

        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename)
        data = await file.read()

        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(ext, "image/jpeg")

        pool = await get_db_pool()
        async with pool.connection() as conn:
            # Check if filename exists and generate unique name
            base_name = Path(safe_name).stem
            final_name = safe_name
            counter = 1
            while True:
                result = await conn.execute(
                    "SELECT id FROM gallery_images WHERE filename = %s", (final_name,)
                )
                if not await result.fetchone():
                    break
                final_name = f"{base_name}_{counter}{ext}"
                counter += 1

            await conn.execute(
                """INSERT INTO gallery_images (filename, data, mime_type, size)
                   VALUES (%s, %s, %s, %s)""",
                (final_name, data, mime_type, len(data)),
            )
            await conn.commit()

        return JSONResponse(
            content={
                "success": True,
                "name": final_name,
                "path": f"/api/gallery/{final_name}",
            }
        )
    except Exception as e:
        logger.error(f"Failed to upload gallery image: {e}")
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@app.delete("/api/gallery/{filename}")
async def delete_gallery_image(filename: str):
    try:
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

        pool = await get_db_pool()
        async with pool.connection() as conn:
            result = await conn.execute(
                "DELETE FROM gallery_images WHERE filename = %s RETURNING id",
                (safe_name,),
            )
            deleted = await result.fetchone()
            await conn.commit()

        if not deleted:
            return JSONResponse(
                content={"success": False, "message": "File not found"}, status_code=404
            )

        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@app.get("/api/gallery/{filename}")
async def get_gallery_image(filename: str):
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

    try:
        pool = await get_db_pool()
        async with pool.connection() as conn:
            result = await conn.execute(
                "SELECT data, mime_type FROM gallery_images WHERE filename = %s",
                (safe_name,),
            )
            row = await result.fetchone()

        if not row:
            return Response(status_code=404)

        return Response(
            content=row[0],
            media_type=row[1],
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logger.error(f"Failed to get gallery image: {e}")
        return Response(status_code=500)


@app.post("/api/gallery/save")
async def save_gallery_image(path: str, file: UploadFile = File(...)):
    """Save edited image back to the gallery, overwriting original."""
    try:
        # Extract filename from the path (e.g., /api/gallery/image.png -> image.png)
        filename = path.split("/")[-1]
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

        content = await file.read()

        # Determine mime type from content or filename
        ext = Path(safe_name).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(ext, "image/png")

        pool = await get_db_pool()
        async with pool.connection() as conn:
            # Update existing or insert new
            result = await conn.execute(
                """UPDATE gallery_images
                   SET data = %s, mime_type = %s, size = %s, updated_at = CURRENT_TIMESTAMP
                   WHERE filename = %s
                   RETURNING id""",
                (content, mime_type, len(content), safe_name),
            )
            updated = await result.fetchone()

            if not updated:
                # Image doesn't exist, create it
                await conn.execute(
                    """INSERT INTO gallery_images (filename, data, mime_type, size)
                       VALUES (%s, %s, %s, %s)""",
                    (safe_name, content, mime_type, len(content)),
                )

            await conn.commit()

        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Failed to save gallery image: {e}")
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


# =============================================================================
# Audio Device Configuration
# =============================================================================

# Track HDMI audio state to avoid re-detecting when not needed
_hdmi_audio_detected = False
_hdmi_audio_card = None


def _detect_hdmi_audio_device() -> tuple:
    """Detect HDMI audio device from aplay -l output.

    Returns:
        Tuple of (card_number, card_id, device_name) if HDMI found, (None, None, None) otherwise
        card_id is the ALSA card identifier like "vc4hdmi0" used for named devices
    """
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("card "):
                    # Check if this is an HDMI device
                    line_lower = line.lower()
                    if "hdmi" in line_lower or "vc4" in line_lower:
                        match = re.match(
                            r"card (\d+): (\w+) \[([^\]]+)\]",
                            line,
                        )
                        if match:
                            card_num = match.group(1)
                            card_id = match.group(2)  # e.g., "vc4hdmi0"
                            card_name = match.group(3)
                            logger.info(
                                f"Detected HDMI audio device: card {card_num} ({card_id}: {card_name})"
                            )
                            return card_num, card_id, card_name
    except Exception as e:
        logger.debug(f"Error detecting HDMI audio: {e}")
    return None, None, None


def _find_microphone_card() -> str:
    """Find the ALSA card number for the microphone/capture device."""
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            mic_priorities = [
                ("usb", 100),
                ("microphone", 90),
                ("mic", 80),
                ("audio", 70),
            ]
            best_card = None
            best_priority = -1

            for line in result.stdout.lower().split("\n"):
                if "card" not in line:
                    continue
                card_match = re.search(r"card\s+(\d+):", line)
                if card_match:
                    card_num = card_match.group(1)
                    for keyword, priority in mic_priorities:
                        if keyword in line and priority > best_priority:
                            best_card = card_num
                            best_priority = priority
                            break

            if best_card:
                return best_card

            # Fallback to first card found
            first_match = re.search(r"card\s+(\d+):", result.stdout.lower())
            if first_match:
                return first_match.group(1)
    except Exception as e:
        logger.warning(f"Error finding microphone card: {e}")

    return "0"


async def _auto_select_hdmi_audio() -> bool:
    """Auto-select HDMI audio if an HDMI display is connected.

    This checks if there's an active HDMI display and an HDMI audio device,
    then automatically switches audio output to HDMI.

    NOTE: This only runs if no audio device has been configured yet.
    If the user has already selected an audio device, their choice is respected.

    Returns:
        True if HDMI audio was selected, False otherwise
    """
    global _hdmi_audio_detected, _hdmi_audio_card

    # Check if we already detected and configured HDMI audio
    if _hdmi_audio_detected and _hdmi_audio_card is not None:
        logger.debug("HDMI audio already configured")
        return True

    # Check if user has already configured an audio device - respect their choice
    try:
        asound_path = Path("/etc/asound.conf")
        if asound_path.exists():
            content = asound_path.read_text()
            match = re.search(r"card\s+(\w+)", content)
            if match:
                current_card = match.group(1)
                logger.info(
                    f"User has audio device configured (card {current_card}), skipping HDMI auto-select"
                )
                return False
    except Exception:
        pass

    # Check if an HDMI display is connected
    manager = _display_manager
    if not manager or not manager.is_available:
        logger.debug("No HDMI display available, skipping HDMI audio auto-select")
        return False

    # Detect HDMI audio device
    hdmi_card, hdmi_card_id, hdmi_name = _detect_hdmi_audio_device()
    if hdmi_card is None:
        logger.debug("No HDMI audio device found")
        return False

    # Configure HDMI audio (only reaches here if no asound.conf exists)
    logger.info(
        f"Auto-selecting HDMI audio: card {hdmi_card} ({hdmi_card_id}: {hdmi_name})"
    )

    # Find the microphone card for capture
    mic_card = _find_microphone_card()

    # Use hdmi:CARD=xxx for HDMI devices - this uses /usr/share/alsa/cards/vc4-hdmi.conf
    # which handles IEC958_SUBFRAME_LE conversion automatically
    playback_device = f"hdmi:CARD={hdmi_card_id},DEV=0"

    asound_config = f"""pcm.!default {{
    type asym
    playback.pcm {{
        type plug
        slave.pcm "{playback_device}"
    }}
    capture.pcm {{
        type plug
        slave.pcm "hw:{mic_card},0"
    }}
}}
ctl.!default {{
    type hw
    card {hdmi_card}
}}
"""

    try:
        asound_path = Path("/etc/asound.conf")
        asound_path.write_text(asound_config)

        # Set environment variables for pygame/SDL
        # Use the named HDMI device for proper format conversion
        os.environ["AUDIODEV"] = playback_device
        os.environ["SDL_AUDIODRIVER"] = "alsa"

        _hdmi_audio_detected = True
        _hdmi_audio_card = hdmi_card

        logger.info(f"HDMI audio configured successfully: {playback_device}")
        return True
    except Exception as e:
        logger.warning(f"Failed to configure HDMI audio: {e}")
        return False


def _reset_hdmi_audio_state():
    """Reset HDMI audio detection state when display is disconnected."""
    global _hdmi_audio_detected, _hdmi_audio_card
    _hdmi_audio_detected = False
    _hdmi_audio_card = None
    logger.debug("HDMI audio state reset")


@app.get("/api/audio/devices")
async def list_audio_devices():
    """List available audio output devices."""
    devices = []
    seen_cards = set()

    # Check which HDMI ports are connected via DRM
    # DRM names like "card1-HDMI-A-1" -> we extract the HDMI port number (1, 2, etc.)
    connected_hdmi_ports = set()  # Set of 1-indexed port numbers (1, 2, etc.)
    drm_hdmi_count = 0
    try:
        drm_path = Path("/sys/class/drm")
        if drm_path.exists():
            for card_dir in drm_path.glob("card*-HDMI-*"):
                drm_hdmi_count += 1
                status_file = card_dir / "status"
                if status_file.exists():
                    status = status_file.read_text().strip()
                    if status == "connected":
                        # Extract port number from names like "card1-HDMI-A-1" or "card0-HDMI-A-2"
                        port_match = re.search(
                            r"HDMI-[AB]-(\d+)", card_dir.name, re.IGNORECASE
                        )
                        if port_match:
                            connected_hdmi_ports.add(int(port_match.group(1)))
    except Exception:
        pass

    # Only filter if we have DRM info AND at least one HDMI is connected
    # If no HDMI shows as connected but we found DRM entries, don't filter
    # (status detection may not work in container)
    should_filter_hdmi = drm_hdmi_count > 0 and len(connected_hdmi_ports) > 0

    try:
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("card "):
                    match = re.match(
                        r"card (\d+): (\w+) \[([^\]]+)\], device (\d+): ([^\[]+)",
                        line,
                    )
                    if match:
                        card_num = match.group(1)
                        card_id = match.group(2)
                        card_name = match.group(3)
                        device_num = match.group(4)
                        device_name = match.group(5).strip()

                        # Skip disconnected HDMI devices (only if we can reliably detect)
                        if should_filter_hdmi and (
                            "hdmi" in card_id.lower() or "hdmi" in card_name.lower()
                        ):
                            # Extract HDMI index from card ID (e.g., vc4hdmi0 -> 0, vc4hdmi1 -> 1)
                            hdmi_match = re.search(r"hdmi(\d+)", card_id.lower())
                            if hdmi_match:
                                hdmi_idx = int(hdmi_match.group(1))
                                # Audio vc4hdmi0 = DRM HDMI-A-1 (port 1), vc4hdmi1 = HDMI-A-2 (port 2)
                                hdmi_port = hdmi_idx + 1
                                if hdmi_port not in connected_hdmi_ports:
                                    continue

                        if card_num not in seen_cards:
                            seen_cards.add(card_num)
                            devices.append(
                                {
                                    "card": int(card_num),
                                    "device": int(device_num),
                                    "id": card_id,
                                    "name": card_name,
                                    "device_name": device_name,
                                    "alsa_name": f"hw:{card_num},{device_num}",
                                }
                            )
    except Exception as e:
        logger.debug(f"Error listing audio devices: {e}")

    current_device = None
    try:
        asound_path = Path("/etc/asound.conf")
        if asound_path.exists():
            content = asound_path.read_text()
            match = re.search(r"card\s+(\w+)", content)
            if match:
                card_value = match.group(1)
                # Always return as string card number for consistency
                # The value in asound.conf could be a number or a card ID like "Headphones"
                if card_value.isdigit():
                    current_device = card_value
                else:
                    # Look up the card number by ID
                    for device in devices:
                        if device["id"] == card_value:
                            current_device = str(device["card"])
                            break
                    # If not found, return the raw value
                    if current_device is None:
                        current_device = card_value
    except Exception:
        pass

    return {
        "devices": devices,
        "current": current_device,
    }


@app.post("/api/audio/device")
async def set_audio_device(request: Request):
    """Set the audio output device."""
    data = await request.json()
    card = data.get("card")
    card_id = data.get("card_id")  # Optional: card ID like "vc4hdmi0" for named devices
    auto_restart = data.get("auto_restart", False)

    if card is None:
        raise HTTPException(status_code=400, detail="Missing 'card' parameter")

    # Find the microphone card for capture
    mic_card = _find_microphone_card()

    # Determine if this is an HDMI device that needs special handling
    # HDMI devices on Raspberry Pi require IEC958 format conversion which is
    # handled by the named ALSA device (hdmi:CARD=xxx) not raw hw:X,0
    is_hdmi = False
    if card_id:
        is_hdmi = "hdmi" in card_id.lower()
    else:
        # Try to detect from aplay -l if card_id not provided
        try:
            result = subprocess.run(
                ["aplay", "-l"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.startswith(f"card {card}:"):
                        if "hdmi" in line.lower() or "vc4" in line.lower():
                            is_hdmi = True
                            # Extract card_id from line like "card 2: vc4hdmi0 [vc4-hdmi-0], device 0:"
                            match = re.match(r"card \d+: (\w+)", line)
                            if match:
                                card_id = match.group(1)
                        break
        except Exception:
            pass

    # For HDMI devices, use the named device which handles IEC958 conversion
    # For other devices, use plughw which handles format conversion
    if is_hdmi and card_id:
        # Use hdmi:CARD=xxx which uses /usr/share/alsa/cards/vc4-hdmi.conf
        # This handles the IEC958_SUBFRAME_LE conversion automatically
        playback_device = f"hdmi:CARD={card_id},DEV=0"
        audiodev = f"hdmi:CARD={card_id},DEV=0"
        logger.info(f"Using HDMI named device: {playback_device}")
    else:
        playback_device = f"hw:{card},0"
        audiodev = f"plughw:{card},0"

    # Use asymmetric config to separate playback and capture devices (with softvol for HDMI)
    if is_hdmi:
        asound_config = f"""pcm.hdmi_hw {{
    type hw
    card {card}
    device 0
}}

ctl.hdmi_hw {{
    type hw
    card {card}
}}

pcm.hdmi_softvol {{
    type softvol
    slave.pcm "hdmi_hw"
    control {{
        name "SoftMaster"
        card {card}
    }}
    min_dB -51.0
    max_dB 0.0
}}

pcm.!default {{
    type asym
    playback.pcm "hdmi_softvol"
    capture.pcm {{
        type plug
        slave.pcm "hw:{mic_card},0"
    }}
}}
ctl.!default {{
    type hw
    card {card}
}}
"""
    else:
        asound_config = f"""pcm.!default {{
    type asym
    playback.pcm {{
        type plug
        slave.pcm "{playback_device}"
    }}
    capture.pcm {{
        type plug
        slave.pcm "hw:{mic_card},0"
    }}
}}
ctl.!default {{
    type hw
    card {card}
}}
"""

    try:
        asound_path = Path("/etc/asound.conf")
        asound_path.write_text(asound_config)

        # Also set environment variables for pygame/SDL
        os.environ["AUDIODEV"] = audiodev
        os.environ["SDL_AUDIODRIVER"] = "alsa"

        mixer_controls = (
            ["SoftMaster", "PCM", "Master", "Speaker", "Headphone", "HDMI"]
            if is_hdmi
            else ["PCM", "Master", "Speaker", "Headphone", "HDMI"]
        )
        successful_control = None
        for control in mixer_controls:
            result = subprocess.run(
                ["amixer", "-c", str(card), "sset", control, "100%"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                successful_control = control
                logger.info(f"Volume set to 100% via {control} control on card {card}")
                break

        # Read the actual volume from the card using the control that worked
        volume_set = None
        if successful_control:
            try:
                result = subprocess.run(
                    ["amixer", "-c", str(card), "get", successful_control],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Parse output like "Mono: Playback 400 [100%] [4.00dB] [on]"
                    match = re.search(r"\[(\d+)%\]", result.stdout)
                    if match:
                        volume_set = int(match.group(1))
            except Exception as e:
                logger.warning(f"Could not read volume from card {card}: {e}")

        # HDMI devices typically don't have mixer controls - return 100 as default
        if volume_set is None and is_hdmi:
            volume_set = 100
            logger.info(
                f"HDMI device on card {card} has no mixer control, using default volume 100"
            )

        restarting = False
        if auto_restart:
            # Trigger container restart in background
            import threading

            def restart_self():
                import time

                time.sleep(1)  # Brief delay to allow response to be sent
                try:
                    # Try to restart the container
                    subprocess.run(
                        ["docker", "restart", "gpt-home-backend-1"],
                        capture_output=True,
                        timeout=30,
                    )
                except Exception:
                    try:
                        subprocess.run(
                            ["docker", "restart", "gpt-home-backend-1"],
                            capture_output=True,
                            timeout=30,
                        )
                    except Exception as e:
                        logger.warning(f"Could not auto-restart container: {e}")

            threading.Thread(target=restart_self, daemon=True).start()
            restarting = True
            logger.info(f"Audio device set to card {card}, container will restart")

        return {
            "success": True,
            "message": f"Audio device set to card {card}."
            + (
                " Restarting..."
                if restarting
                else " Restart container for changes to take effect."
            ),
            "card": card,
            "volume": volume_set,
            "hdmi": is_hdmi,
            "requires_restart": not restarting,
            "restarting": restarting,
        }
    except PermissionError:
        raise HTTPException(
            status_code=500,
            detail="Permission denied writing to /etc/asound.conf",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audio/volume")
async def get_audio_volume():
    """Get current audio volume."""
    # Get the current card and check if it's HDMI from asound.conf
    current_card = "0"
    is_hdmi = False
    try:
        asound_path = Path("/etc/asound.conf")
        if asound_path.exists():
            content = asound_path.read_text()
            # Check for HDMI device in playback.pcm
            if "hdmi:CARD=" in content:
                is_hdmi = True
            match = re.search(r"card\s+(\w+)", content)
            if match:
                current_card = match.group(1)
    except Exception:
        pass

    try:
        # Try multiple mixer controls - different cards use different names
        mixer_controls = (
            ["SoftMaster", "PCM", "Master", "Speaker", "Headphone", "HDMI"]
            if is_hdmi
            else ["PCM", "Master", "Speaker", "Headphone", "HDMI"]
        )

        for control in mixer_controls:
            result = subprocess.run(
                ["amixer", "-c", current_card, "sget", control],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                match = re.search(r"\[(\d+)%\]", result.stdout)
                if match:
                    return {"volume": int(match.group(1))}

        # HDMI devices often don't have mixer controls accessible via amixer
        # Return 100 as default since HDMI typically uses fixed output level
        if is_hdmi:
            return {
                "volume": 100,
                "hdmi": True,
                "note": "HDMI devices use fixed output level",
            }

        return {"volume": None, "error": "Could not read volume"}
    except Exception as e:
        return {"volume": None, "error": str(e)}


@app.post("/api/audio/volume")
async def set_audio_volume(request: Request):
    """Set audio volume."""
    data = await request.json()
    volume = data.get("volume")

    if volume is None or not (0 <= volume <= 100):
        raise HTTPException(status_code=400, detail="Volume must be 0-100")

    # Get the current card and check if it's HDMI from asound.conf
    current_card = "0"
    is_hdmi = False
    try:
        asound_path = Path("/etc/asound.conf")
        if asound_path.exists():
            content = asound_path.read_text()
            if "hdmi:CARD=" in content:
                is_hdmi = True
            match = re.search(r"card\s+(\w+)", content)
            if match:
                current_card = match.group(1)
    except Exception:
        pass

    try:
        # Try multiple mixer controls - different cards use different names
        mixer_controls = (
            ["SoftMaster", "PCM", "Master", "Speaker", "Headphone", "HDMI"]
            if is_hdmi
            else ["PCM", "Master", "Speaker", "Headphone", "HDMI"]
        )
        success = False

        for control in mixer_controls:
            result = subprocess.run(
                ["amixer", "-c", current_card, "sset", control, f"{volume}%"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                success = True
                logger.debug(f"Volume set via {control} control on card {current_card}")
                break

        if not success:
            # HDMI devices often don't have mixer controls
            if is_hdmi:
                logger.info(
                    f"HDMI device on card {current_card} has no mixer control (normal)"
                )
                return {
                    "success": True,
                    "volume": volume,
                    "hdmi": True,
                    "note": "HDMI uses fixed output",
                }
            logger.warning(f"Could not set volume on card {current_card}")

        return {"success": True, "volume": volume}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audio/mic-gain")
async def get_mic_gain():
    """Get current microphone capture gain."""
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        mic_card = None
        for line in result.stdout.split("\n"):
            if "card" in line.lower() and "usb" in line.lower():
                match = re.search(r"card\s+(\d+)", line)
                if match:
                    mic_card = match.group(1)
                    break

        if mic_card is None:
            for line in result.stdout.split("\n"):
                if "card" in line.lower():
                    match = re.search(r"card\s+(\d+)", line)
                    if match:
                        mic_card = match.group(1)
                        break

        if mic_card is None:
            return {"gain": None, "card": None, "error": "No capture device found"}

        capture_controls = ["Capture", "Mic", "Input", "Digital"]

        for control in capture_controls:
            result = subprocess.run(
                ["amixer", "-c", mic_card, "sget", control],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                match = re.search(r"\[(\d+)%\]", result.stdout)
                if match:
                    return {
                        "gain": int(match.group(1)),
                        "card": mic_card,
                        "control": control,
                    }

        return {"gain": None, "card": mic_card, "error": "Could not read capture gain"}
    except Exception as e:
        return {"gain": None, "error": str(e)}


@app.post("/api/audio/mic-gain")
async def set_mic_gain(request: Request):
    """Set microphone capture gain and persist to settings."""
    data = await request.json()
    gain = data.get("gain")

    if gain is None or not (0 <= gain <= 100):
        raise HTTPException(status_code=400, detail="Gain must be 0-100")

    try:
        settings_path = SOURCE_DIR / "settings.json"
        settings = {}
        if settings_path.exists():
            with settings_path.open("r") as f:
                settings = json.load(f)
        settings["micGain"] = int(gain)
        with settings_path.open("w") as f:
            json.dump(settings, f, indent=4)

        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        mic_card = None
        for line in result.stdout.split("\n"):
            if "card" in line.lower() and "usb" in line.lower():
                match = re.search(r"card\s+(\d+)", line)
                if match:
                    mic_card = match.group(1)
                    break

        if mic_card is None:
            for line in result.stdout.split("\n"):
                if "card" in line.lower():
                    match = re.search(r"card\s+(\d+)", line)
                    if match:
                        mic_card = match.group(1)
                        break

        if mic_card is None:
            raise HTTPException(status_code=404, detail="No capture device found")

        capture_controls = ["Capture", "Mic", "Input", "Digital"]
        success = False

        for control in capture_controls:
            result = subprocess.run(
                ["amixer", "-c", mic_card, "sset", control, f"{gain}%"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                success = True
                logger.debug(f"Mic gain set via {control} control on card {mic_card}")
                break

        if not success:
            logger.warning(f"Could not set mic gain on card {mic_card}")

        return {"success": True, "gain": gain, "card": mic_card}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audio/input-devices")
async def list_input_devices():
    """List available audio input (capture) devices."""
    devices = []
    seen_cards = set()

    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("card "):
                    match = re.match(
                        r"card (\d+): (\w+) \[([^\]]+)\], device (\d+): ([^\[]+)",
                        line,
                    )
                    if match:
                        card_num = match.group(1)
                        card_id = match.group(2)
                        card_name = match.group(3)
                        device_num = match.group(4)
                        device_name = match.group(5).strip()

                        if card_num not in seen_cards:
                            seen_cards.add(card_num)
                            devices.append(
                                {
                                    "card": int(card_num),
                                    "device": int(device_num),
                                    "id": card_id,
                                    "name": card_name,
                                    "device_name": device_name,
                                    "alsa_name": f"hw:{card_num},{device_num}",
                                }
                            )
    except Exception as e:
        logger.debug(f"Error listing input devices: {e}")

    # Get current input device from settings
    current_device = None
    try:
        settings_path = SOURCE_DIR / "settings.json"
        if settings_path.exists():
            with settings_path.open("r") as f:
                settings = json.load(f)
            current_device = settings.get("inputDevice")
    except Exception:
        pass

    return {
        "devices": devices,
        "current": current_device,
    }


@app.post("/api/audio/input-device")
async def set_input_device(request: Request):
    """Set the audio input device."""
    data = await request.json()
    card = data.get("card")

    if card is None:
        raise HTTPException(status_code=400, detail="Card number required")

    try:
        # Save to settings.json
        settings_path = SOURCE_DIR / "settings.json"
        settings = {}
        if settings_path.exists():
            with settings_path.open("r") as f:
                settings = json.load(f)

        settings["inputDevice"] = str(card)

        with settings_path.open("w") as f:
            json.dump(settings, f, indent=4)

        # Signal the app to use the new microphone
        # The app.py will need to be restarted to pick up the new device
        return {
            "success": True,
            "card": card,
            "message": "Input device saved. Restart required to apply.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audio/vad-threshold")
async def get_vad_threshold():
    """Get current VAD threshold from settings."""
    try:
        settings_path = SOURCE_DIR / "settings.json"
        if settings_path.exists():
            with settings_path.open("r") as f:
                settings = json.load(f)
            return {"threshold": settings.get("vadThresholdDb", -50.0)}
        return {"threshold": -50.0}
    except Exception as e:
        return {"threshold": -50.0, "error": str(e)}


@app.post("/api/audio/vad-threshold")
async def set_vad_threshold(request: Request):
    """Set VAD threshold in settings."""
    data = await request.json()
    threshold = data.get("threshold")

    if threshold is None or not (-80 <= threshold <= 0):
        raise HTTPException(
            status_code=400, detail="Threshold must be between -80 and 0 dB"
        )

    try:
        settings_path = SOURCE_DIR / "settings.json"
        settings = {}
        if settings_path.exists():
            with settings_path.open("r") as f:
                settings = json.load(f)

        settings["vadThresholdDb"] = float(threshold)

        with settings_path.open("w") as f:
            json.dump(settings, f, indent=4)

        return {"success": True, "threshold": threshold}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audio/speech-timing")
async def get_speech_timing():
    """Get speech recognition timing settings."""
    try:
        settings_path = SOURCE_DIR / "settings.json"
        if settings_path.exists():
            with settings_path.open("r") as f:
                settings = json.load(f)
            return {
                "pauseThreshold": settings.get("pauseThreshold", 1.2),
                "phraseTimeLimit": settings.get("phraseTimeLimit", 30),
                "nonSpeakingDuration": settings.get("nonSpeakingDuration", 0.8),
            }
        return {
            "pauseThreshold": 1.2,
            "phraseTimeLimit": 30,
            "nonSpeakingDuration": 0.8,
        }
    except Exception as e:
        return {
            "pauseThreshold": 1.2,
            "phraseTimeLimit": 30,
            "nonSpeakingDuration": 0.8,
            "error": str(e),
        }


@app.post("/api/audio/speech-timing")
async def set_speech_timing(request: Request):
    """Set speech recognition timing settings."""
    data = await request.json()

    pause_threshold = data.get("pauseThreshold")
    phrase_time_limit = data.get("phraseTimeLimit")
    non_speaking_duration = data.get("nonSpeakingDuration")

    try:
        settings_path = SOURCE_DIR / "settings.json"
        settings = {}
        if settings_path.exists():
            with settings_path.open("r") as f:
                settings = json.load(f)

        if pause_threshold is not None:
            if not (0.3 <= pause_threshold <= 5.0):
                raise HTTPException(
                    status_code=400, detail="pauseThreshold must be between 0.3 and 5.0"
                )
            settings["pauseThreshold"] = float(pause_threshold)

        if phrase_time_limit is not None:
            if not (5 <= phrase_time_limit <= 120):
                raise HTTPException(
                    status_code=400, detail="phraseTimeLimit must be between 5 and 120"
                )
            settings["phraseTimeLimit"] = int(phrase_time_limit)

        if non_speaking_duration is not None:
            if not (0.1 <= non_speaking_duration <= 3.0):
                raise HTTPException(
                    status_code=400,
                    detail="nonSpeakingDuration must be between 0.1 and 3.0",
                )
            settings["nonSpeakingDuration"] = float(non_speaking_duration)

        with settings_path.open("w") as f:
            json.dump(settings, f, indent=4)

        try:
            from src.common import reload_speech_timing_settings

            reload_speech_timing_settings()
        except Exception:
            pass

        return {
            "success": True,
            "pauseThreshold": settings.get("pauseThreshold", 1.2),
            "phraseTimeLimit": settings.get("phraseTimeLimit", 30),
            "nonSpeakingDuration": settings.get("nonSpeakingDuration", 0.8),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_host_command(cmd: list, timeout: int = 5) -> str:
    """Run a command on the host system via nsenter."""
    try:
        full_cmd = [
            "nsenter",
            "--target",
            "1",
            "--mount",
            "--uts",
            "--ipc",
            "--net",
            "--pid",
            "--",
        ] + cmd
        result = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _get_host_stats() -> dict:
    """Get system stats from the host via /proc and /sys."""
    stats = {
        "cpu": {
            "percent": [],
            "percent_total": 0,
            "count": 0,
            "count_logical": 0,
            "freq_current": 0,
            "freq_max": 0,
            "load_avg": [0, 0, 0],
        },
        "memory": {
            "total": 0,
            "available": 0,
            "used": 0,
            "percent": 0,
            "swap_total": 0,
            "swap_used": 0,
            "swap_percent": 0,
        },
        "disk": {
            "total": 0,
            "used": 0,
            "free": 0,
            "percent": 0,
            "read_bytes": 0,
            "write_bytes": 0,
        },
        "network": {
            "bytes_sent": 0,
            "bytes_recv": 0,
            "packets_sent": 0,
            "packets_recv": 0,
        },
        "temperatures": {},
        "boot_time": 0,
        "timestamp": time.time(),
    }

    try:
        # CPU info via host's /proc
        loadavg = _run_host_command(["cat", "/proc/loadavg"])
        if loadavg:
            parts = loadavg.split()
            stats["cpu"]["load_avg"] = [
                float(parts[0]),
                float(parts[1]),
                float(parts[2]),
            ]

        cpuinfo = _run_host_command(["nproc"])
        if cpuinfo:
            stats["cpu"]["count"] = int(cpuinfo)
            stats["cpu"]["count_logical"] = int(cpuinfo)

        # CPU frequency
        freq = _run_host_command(
            ["cat", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"]
        )
        if freq:
            stats["cpu"]["freq_current"] = int(freq) / 1000  # kHz to MHz

        freq_max = _run_host_command(
            ["cat", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"]
        )
        if freq_max:
            stats["cpu"]["freq_max"] = int(freq_max) / 1000

        # CPU usage from /proc/stat
        stat1 = _run_host_command(["cat", "/proc/stat"])
        time.sleep(0.1)
        stat2 = _run_host_command(["cat", "/proc/stat"])
        if stat1 and stat2:

            def parse_cpu_line(line):
                parts = line.split()
                return [int(x) for x in parts[1:8]]

            lines1 = [
                l
                for l in stat1.split("\n")
                if l.startswith("cpu") and not l.startswith("cpu ")
            ]
            lines2 = [
                l
                for l in stat2.split("\n")
                if l.startswith("cpu") and not l.startswith("cpu ")
            ]

            percents = []
            for l1, l2 in zip(lines1, lines2):
                v1, v2 = parse_cpu_line(l1), parse_cpu_line(l2)
                idle1, idle2 = v1[3] + v1[4], v2[3] + v2[4]
                total1, total2 = sum(v1), sum(v2)
                idle_delta = idle2 - idle1
                total_delta = total2 - total1
                if total_delta > 0:
                    percents.append(round(100 * (1 - idle_delta / total_delta), 1))
            stats["cpu"]["percent"] = percents
            stats["cpu"]["percent_total"] = (
                round(sum(percents) / len(percents), 1) if percents else 0
            )

        # Memory from /proc/meminfo
        meminfo = _run_host_command(["cat", "/proc/meminfo"])
        if meminfo:
            mem = {}
            for line in meminfo.split("\n"):
                if ":" in line:
                    key, val = line.split(":")
                    mem[key.strip()] = int(val.strip().split()[0]) * 1024  # kB to bytes

            stats["memory"]["total"] = mem.get("MemTotal", 0)
            stats["memory"]["available"] = mem.get("MemAvailable", 0)
            stats["memory"]["used"] = (
                stats["memory"]["total"] - stats["memory"]["available"]
            )
            if stats["memory"]["total"] > 0:
                stats["memory"]["percent"] = round(
                    100 * stats["memory"]["used"] / stats["memory"]["total"], 1
                )
            stats["memory"]["swap_total"] = mem.get("SwapTotal", 0)
            stats["memory"]["swap_used"] = stats["memory"]["swap_total"] - mem.get(
                "SwapFree", 0
            )
            if stats["memory"]["swap_total"] > 0:
                stats["memory"]["swap_percent"] = round(
                    100 * stats["memory"]["swap_used"] / stats["memory"]["swap_total"],
                    1,
                )

        # Disk usage
        df_out = _run_host_command(["df", "-B1", "/"])
        if df_out:
            lines = df_out.split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    stats["disk"]["total"] = int(parts[1])
                    stats["disk"]["used"] = int(parts[2])
                    stats["disk"]["free"] = int(parts[3])
                    if stats["disk"]["total"] > 0:
                        stats["disk"]["percent"] = round(
                            100 * stats["disk"]["used"] / stats["disk"]["total"], 1
                        )

        # Disk I/O from /proc/diskstats
        diskstats = _run_host_command(["cat", "/proc/diskstats"])
        if diskstats:
            for line in diskstats.split("\n"):
                parts = line.split()
                if len(parts) >= 14:
                    device = parts[2]
                    if device in ("mmcblk0", "sda", "nvme0n1"):
                        stats["disk"]["read_bytes"] += int(parts[5]) * 512
                        stats["disk"]["write_bytes"] += int(parts[9]) * 512

        # Network stats
        netdev = _run_host_command(["cat", "/proc/net/dev"])
        if netdev:
            for line in netdev.split("\n"):
                if ":" in line and not line.strip().startswith("lo:"):
                    parts = line.split(":")[1].split()
                    if len(parts) >= 10:
                        stats["network"]["bytes_recv"] += int(parts[0])
                        stats["network"]["packets_recv"] += int(parts[1])
                        stats["network"]["bytes_sent"] += int(parts[8])
                        stats["network"]["packets_sent"] += int(parts[9])

        # Temperature (Raspberry Pi)
        temp = _run_host_command(["cat", "/sys/class/thermal/thermal_zone0/temp"])
        if temp:
            stats["temperatures"]["cpu_thermal"] = int(temp) / 1000.0

        # Boot time
        uptime = _run_host_command(["cat", "/proc/uptime"])
        if uptime:
            uptime_secs = float(uptime.split()[0])
            stats["boot_time"] = time.time() - uptime_secs

    except Exception as e:
        logger.debug(f"Error getting host stats: {e}")

    return stats


@app.get("/api/system/stats")
async def get_system_stats():
    """Get current system resource usage statistics from the host."""
    try:
        return _get_host_stats()
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system/processes")
async def get_system_processes():
    """Get list of running processes from the host."""
    try:
        processes: List[Dict[str, Any]] = []

        # Get process list from host via ps
        ps_out = _run_host_command(["ps", "aux", "--sort=-%cpu"], timeout=10)
        if ps_out:
            lines = ps_out.split("\n")[1:]  # Skip header
            for line in lines[:50]:  # Limit to top 50
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    try:
                        processes.append(
                            {
                                "pid": int(parts[1]),
                                "name": parts[10][:50]
                                if len(parts[10]) > 50
                                else parts[10],
                                "cpu_percent": float(parts[2]),
                                "memory_percent": float(parts[3]),
                                "status": parts[7],
                                "username": parts[0],
                                "create_time": 0,
                            }
                        )
                    except (ValueError, IndexError):
                        pass

        processes.sort(
            key=lambda x: x["cpu_percent"] + x["memory_percent"], reverse=True
        )
        return {"processes": processes[:50], "total": len(processes)}
    except Exception as e:
        logger.error(f"Error getting processes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system/info")
async def get_system_info():
    """Get static system information from the host."""
    try:
        # Get host info via uname
        uname_out = _run_host_command(["uname", "-a"])
        hostname = _run_host_command(["hostname"])
        uptime_out = _run_host_command(["cat", "/proc/uptime"])

        # Parse uname output
        system = "Linux"
        release = ""
        version = ""
        machine = ""

        if uname_out:
            parts = uname_out.split()
            if len(parts) >= 1:
                system = parts[0]
            if len(parts) >= 3:
                release = parts[2]
            if len(parts) >= 4:
                version = " ".join(parts[3:])
            machine = _run_host_command(["uname", "-m"]) or ""

        boot_time = 0
        uptime_secs = 0
        if uptime_out:
            uptime_secs = float(uptime_out.split()[0])
            boot_time = time.time() - uptime_secs

        return {
            "system": system,
            "node": hostname or "gpt-home",
            "release": release,
            "version": version,
            "machine": machine,
            "processor": machine,
            "python_version": "3.11",
            "boot_time": boot_time,
            "uptime": uptime_secs,
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_terminal_sessions: Dict[str, Dict[str, Any]] = {}


def _set_pty_size(fd: int, rows: int, cols: int):
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


@app.websocket("/api/terminal/ws")
async def terminal_websocket(websocket: WebSocket):
    await websocket.accept()

    master_fd = None
    slave_fd = None
    proc = None
    session_id = str(id(websocket))
    rows, cols = 24, 80

    try:
        # Wait for initial resize from frontend before starting shell
        try:
            message = await asyncio.wait_for(websocket.receive(), timeout=2.0)
            if "text" in message and message["text"].startswith('{"type":"resize"'):
                resize_data = json.loads(message["text"])
                rows = resize_data.get("rows", 24)
                cols = resize_data.get("cols", 80)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            pass

        master_fd, slave_fd = pty.openpty()
        _set_pty_size(master_fd, rows, cols)

        env = os.environ.copy()
        env.update(
            {
                "TERM": "xterm-256color",
                "COLORTERM": "truecolor",
                "SHELL": "/bin/bash",
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "HOME": "/root",
                "COLUMNS": str(cols),
                "LINES": str(rows),
            }
        )

        proc = subprocess.Popen(
            [
                "nsenter",
                "-t",
                "1",
                "-m",
                "-u",
                "-i",
                "-n",
                "-p",
                "setsid",
                "--ctty",
                "--wait",
                "/bin/bash",
                "--login",
            ],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            start_new_session=False,
        )

        os.close(slave_fd)
        slave_fd = None

        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        _terminal_sessions[session_id] = {
            "pid": proc.pid,
            "master_fd": master_fd,
        }

        async def read_from_pty():
            while proc.poll() is None:
                try:
                    readable, _, _ = select.select([master_fd], [], [], 0.1)
                    if readable:
                        try:
                            data = os.read(master_fd, 4096)
                            if data:
                                await websocket.send_bytes(data)
                        except OSError as e:
                            if e.errno in (5, 9):
                                break
                            raise
                except (OSError, ValueError):
                    break
                await asyncio.sleep(0.01)

        read_task = asyncio.create_task(read_from_pty())

        try:
            while True:
                message = await websocket.receive()

                if message["type"] == "websocket.disconnect":
                    break

                if "bytes" in message:
                    os.write(master_fd, message["bytes"])
                elif "text" in message:
                    text = message["text"]
                    if text.startswith('{"type":"resize"'):
                        try:
                            resize_data = json.loads(text)
                            if resize_data.get("type") == "resize":
                                _set_pty_size(
                                    master_fd,
                                    resize_data.get("rows", 24),
                                    resize_data.get("cols", 80),
                                )
                        except json.JSONDecodeError:
                            pass
                    else:
                        os.write(master_fd, text.encode())

        except WebSocketDisconnect:
            pass
        finally:
            read_task.cancel()
            try:
                await read_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"Terminal WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
    finally:
        if session_id in _terminal_sessions:
            del _terminal_sessions[session_id]

        if slave_fd is not None:
            try:
                os.close(slave_fd)
            except OSError:
                pass

        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass

        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=1)
                except Exception:
                    pass
