from fastapi.responses import JSONResponse, RedirectResponse
from src.common import logger, SOURCE_DIR, log_file_path
from fastapi import FastAPI, Request, Response, status
from dotenv import load_dotenv, set_key, unset_key
from sse_starlette.sse import EventSourceResponse
from fastapi.exceptions import HTTPException
from typing import Optional
from phue import Bridge, PhueRequestTimeout
import subprocess
import traceback
import requests
import litellm
import asyncio
import spotipy
import hashlib
import logging
import socket
import time
import json
import os
import re

# Suppress verbose LiteLLM callback logging (success_handler spam)
litellm.suppress_debug_info = True
litellm.set_verbose = False
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("LiteLLM Proxy").setLevel(logging.ERROR)
logging.getLogger("litellm").setLevel(logging.ERROR)

ROOT_DIR = SOURCE_DIR.parent
ENV_FILE_PATH = ROOT_DIR / ".env"
FRONTEND_ENV_PATH = SOURCE_DIR / "frontend" / ".env"
TOKEN_PATH = "spotify_token.json"

# Load main .env for API keys
load_dotenv(ENV_FILE_PATH)
# Also load frontend .env if exists
if FRONTEND_ENV_PATH.exists():
    load_dotenv(FRONTEND_ENV_PATH, override=False)

app = FastAPI()

@app.post("/get-local-ip")
def get_local_ip():
    ip = subprocess.run(["hostname", "-I"], capture_output=True).stdout.decode().split()[0]
    return JSONResponse(content={"ip": ip})

@app.post("/api/settings/dark-mode")
async def toggle_dark_mode(request: Request):
    try:
        settings_path = SOURCE_DIR / "settings.json"

        # Read existing settings
        with open(settings_path, 'r') as f:
            settings = json.load(f)

        # Try to read incoming JSON, handle if empty
        try:
            incoming_data = await request.json()
        except Exception:
            incoming_data = {}

        if 'darkMode' in incoming_data:
            dark_mode = str(incoming_data['darkMode']).lower()

            # Update settings
            settings['dark_mode'] = dark_mode

            # Write updated settings back to file
            with open(settings_path, 'w') as f:
                json.dump(settings, f)

            return JSONResponse(content={"success": True, "darkMode": dark_mode})

        # Fallback to returning the current mode
        mode = settings.get('dark_mode', 'false').lower()
        return JSONResponse(content={"darkMode": mode == "true"})

    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()}, status_code=500)

## Event Logs ##

@app.post("/logs")
def logs(request: Request):
    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("r") as f:
            log_data = f.read()
        return JSONResponse(content={"log_data": log_data.replace("`", "")})
    else:
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Log file not found")
    
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
                    if current_entry:  # If there's an accumulated entry, add it to new_logs
                        new_logs.append(''.join(current_entry))
                        current_entry = []  # Reset for the next entry
                current_entry.append(line)
                total_lines += 1

            # Append the last accumulated entry if present
            if current_entry:
                new_logs.append(''.join(current_entry))

        # Slice new_logs to only include entries after the last checked line number
        # Calculate where to start based on entries, not lines
        if last_line_number < len(new_logs):
            return JSONResponse(content={
                "last_logs": new_logs[last_line_number:],
                "new_last_line_number": len(new_logs)
            })
        else:
            return JSONResponse(content={"last_logs": [], "new_last_line_number": len(new_logs)})
    else:
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Log file not found")

@app.post("/clear-logs")
def clear_logs(request: Request):
    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("w") as f:
            f.write("")
        return Response(status_code=status.HTTP_200_OK, content="Logs cleared")
    else:
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Log file not found")

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
                                all_entries.append(''.join(current_entry))
                                current_entry = []
                            current_entry.append(line)
                        else:
                            current_entry.append(line)
                    
                    if current_entry:
                        all_entries.append(''.join(current_entry))
                
                while current_line < len(all_entries):
                    entry = all_entries[current_line]
                    log_type = entry.split(":")[0].lower() if ":" in entry else "info"
                    yield {
                        "event": "message",
                        "data": json.dumps({"content": entry, "type": log_type})
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
    incoming_data = await request.json()

    if 'action' in incoming_data and incoming_data['action'] == 'read':
        if settings_path.exists() and settings_path.is_file():
            with settings_path.open("r") as f:
                file_settings = json.load(f)
            file_settings['litellm_api_key'] = os.getenv('LITELLM_API_KEY', '')
            return JSONResponse(content=file_settings)
        else:
            return HTTPException(status_code=404, detail="Settings not found")

    elif 'action' in incoming_data and incoming_data['action'] == 'update':
        new_settings = incoming_data['data']
                
        if 'litellm_api_key' in new_settings:
            val = new_settings.pop('litellm_api_key')
            if val:
                set_key(str(ENV_FILE_PATH), 'LITELLM_API_KEY', val)
            else:
                unset_key(str(ENV_FILE_PATH), 'LITELLM_API_KEY')
        
        # Also update EMBEDDING_MODEL env var if provided
        if 'embedding_model' in new_settings:
            val = new_settings.get('embedding_model')
            if val:
                set_key(str(ENV_FILE_PATH), 'EMBEDDING_MODEL', val)
        
        with settings_path.open("w") as f:
            json.dump(new_settings, f, indent=2)
        
        subprocess.run(["supervisorctl", "restart", "app"])
        
        new_settings['litellm_api_key'] = os.getenv('LITELLM_API_KEY', '')
        return JSONResponse(content=new_settings)
    else:
        return HTTPException(status_code=400, detail="Invalid action")
    
@app.post("/gptRestart")
async def gpt_restart(request: Request):
    # In Docker environment, we can trigger a self-restart by exiting
    # The container will restart due to restart: unless-stopped policy
    import os
    import signal
    os.kill(os.getpid(), signal.SIGTERM)
    return JSONResponse(content={"success": True})

@app.post("/spotifyRestart")
async def spotify_restart(request: Request):
    # In Docker environment, restart spotifyd container via Docker socket
    try:
        result = subprocess.run(
            ["docker", "restart", "gpt-home-spotifyd-1"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            # Fallback: try without the -1 suffix
            subprocess.run(["docker", "restart", "gpt-home-spotifyd"], capture_output=True)
        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Failed to restart spotifyd: {e}")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

@app.post("/reboot")
async def reboot(request: Request):
    # Reboot the host system (requires privileged container or host access)
    try:
        subprocess.run(["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "--", "reboot"])
    except Exception:
        # Fallback for when nsenter isn't available
        subprocess.run(["reboot"])
    return JSONResponse(content={"success": True})

@app.post("/shutdown")
async def shutdown(request: Request):
    # Shutdown the host system (requires privileged container or host access)
    try:
        subprocess.run(["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "--", "shutdown", "now"])
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
            "postgresql://gpt_home:gpt_home_secret@localhost:5432/gpt_home"
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
        return JSONResponse(content={"success": True, "message": "Memory cleared successfully"})
    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

@app.get("/speechCapabilities")
async def speech_capabilities():
    """Return TTS/STT capabilities based on current API key."""
    try:
        from common import litellm_tts_available, litellm_stt_available, get_litellm_provider
        return JSONResponse(content={
            "provider": get_litellm_provider(),
            "tts_available": litellm_tts_available(),
            "stt_available": litellm_stt_available(),
        })
    except Exception as e:
        return JSONResponse(content={
            "provider": None,
            "tts_available": False,
            "stt_available": False,
        })

@app.post("/availableModels")
async def available_models():
    try:
        response = requests.get("https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json")
        model_list = response.json()
        supported_models = [model for model in model_list.keys()]

        return JSONResponse(content={"models": supported_models})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
@app.post("/updateModel")
async def update_model(request: Request):
    try:
        incoming_data = await request.json()
        model_id = incoming_data['model_id']
        
        # API key is now read from environment
        litellm.api_key = os.getenv("LITELLM_API_KEY", "")
        
        response = requests.get("https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json")
        model_list = response.json()
        supported_models = [model for model in model_list.keys()]
        
        if model_id in supported_models:
            settings_path = SOURCE_DIR / "settings.json"
            with settings_path.open("r") as f:
                settings = json.load(f)
            settings['model'] = model_id
            with settings_path.open("w") as f:
                json.dump(settings, f)
            
            # Restart service
            subprocess.run(["supervisorctl", "restart", "app"])
            
            return JSONResponse(content={"model": model_id})
        else:
            return HTTPException(status_code=400, detail=f"Model {model_id} not supported")
    except Exception as e:
        return HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


## Password ##

@app.on_event("startup")
async def startup_event():
    password_file_path = SOURCE_DIR / "hashed_password.txt"
    if not password_file_path.exists():
        with password_file_path.open("w") as f:
            f.write("")

def generate_hashed_password(password: str) -> str:
    sha256 = hashlib.sha256()
    sha256.update(password.encode('utf-8'))
    return sha256.hexdigest()

@app.post("/hashPassword")
async def hash_password_route(request: Request):
    try:
        incoming_data = await request.json()
        password = incoming_data["password"]
        hashed_password = generate_hashed_password(password)
        return JSONResponse(content={"success": True, "hashedPassword": hashed_password})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/getHashedPassword")
def get_hashed_password():
    try:
        password_file_path = SOURCE_DIR / "hashed_password.txt"

        if password_file_path.exists() and password_file_path.is_file():
            with password_file_path.open("r") as f:
                hashed_password = f.read().strip()
            return JSONResponse(content={"success": True, "hashedPassword": hashed_password})
        else:
            return HTTPException(status_code=404, detail="Hashed password not found")
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/setHashedPassword")
async def set_hashed_password(request: Request):
    try:
        incoming_data = await request.json()
        new_hashed_password = incoming_data["hashedPassword"]
        password_file_path = SOURCE_DIR / "hashed_password.txt"

        with password_file_path.open("w") as f:
            f.write(new_hashed_password)
        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/changePassword")
async def change_password(request: Request):
    try:
        incoming_data = await request.json()
        old_password = incoming_data["oldPassword"]
        new_password = incoming_data["newPassword"]
        password_file_path = SOURCE_DIR / "hashed_password.txt"
        
        if password_file_path.exists() and password_file_path.is_file():
            with password_file_path.open("r") as f:
                stored_hashed_password = f.read().strip()

            provided_hashed_password = generate_hashed_password(old_password)

            if provided_hashed_password == stored_hashed_password:
                
                new_hashed_password = generate_hashed_password(new_password)

                # Store the new hashed password
                with password_file_path.open("w") as f:
                    f.write(new_hashed_password)
                
                return JSONResponse(content={"success": True})
            else:
                return HTTPException(status_code=401, detail="Incorrect password")
        else:
            return HTTPException(status_code=404, detail="Hashed password not found")
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})


## Integrations ##

@app.post("/connect-service")
async def connect_service(request: Request):
    try:
        incoming_data = await request.json()
        name = incoming_data["name"].lower().strip()
        fields = incoming_data["fields"]
        requesting_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or request.client.host
        ip = subprocess.run(["hostname", "-I"], capture_output=True).stdout.decode().strip().split()[0]

        # Initialize variables for Spotify
        spotify_client_id = None
        spotify_client_secret = None
        redirect_uri = None
        auth_url = None

        for key, value in fields.items():
            if name == "spotify":
                if key == "CLIENT ID":
                    set_key(ENV_FILE_PATH, "SPOTIFY_CLIENT_ID", value)
                    os.environ["SPOTIFY_CLIENT_ID"] = value
                    spotify_client_id = value
                elif key == "CLIENT SECRET":
                    set_key(ENV_FILE_PATH, "SPOTIFY_CLIENT_SECRET", value)
                    os.environ["SPOTIFY_CLIENT_SECRET"] = value
                    spotify_client_secret = value
            elif name == "openweather":
                if key == "API KEY":
                    set_key(ENV_FILE_PATH, "OPEN_WEATHER_API_KEY", value)
                    os.environ["OPEN_WEATHER_API_KEY"] = value
            elif name == "philipshue":
                if key == "BRIDGE IP ADDRESS":
                    set_key(ENV_FILE_PATH, "PHILIPS_HUE_BRIDGE_IP", value)
                    os.environ["PHILIPS_HUE_BRIDGE_IP"] = value
                    # Try to connect and get username - return early if it fails
                    hue_result = await set_philips_hue_username(value)
                    if hue_result.status_code != 200:
                        return hue_result
            elif name == "caldav":
                if key == "URL":
                    set_key(ENV_FILE_PATH, "CALDAV_URL", value)
                    os.environ["CALDAV_URL"] = value
                elif key == "USERNAME":
                    set_key(ENV_FILE_PATH, "CALDAV_USERNAME", value)
                    os.environ["CALDAV_USERNAME"] = value
                elif key == "PASSWORD":
                    set_key(ENV_FILE_PATH, "CALDAV_PASSWORD", value)
                    os.environ["CALDAV_PASSWORD"] = value

        if name == "spotify":
            spotify_username = fields.get("USERNAME")
            spotify_password = fields.get("PASSWORD")
            os.environ["SPOTIFY_USERNAME"] = spotify_username
            
            if spotify_username and spotify_password:
                # Update the spotifyd configuration dynamically
                config_path = "/root/.config/spotifyd/spotifyd.conf"
                with open(config_path, "w") as file:
                    file.write("[global]\n")
                    file.write(f"username = \"{spotify_username}\"\n")
                    file.write(f"password = \"{spotify_password}\"\n")
                    file.write("backend = \"alsa\"\n")
                    file.write("device_name = \"GPT Home\"\n")
                    file.write("bitrate = 320\n")
                    file.write(f"cache_path = \"/root/.spotifyd/cache\"\n")
                    file.write("disable_discovery = false\n")
                    file.write("zeroconf_port = 1234\n")
                    file.write("use_mpris = false\n")
                
                # Restart spotifyd to apply changes
                subprocess.run(["supervisorctl", "restart", "spotifyd"], check=True)

            # Setting REDIRECT URI explicitly to gpt-home.local
            redirect_uri = "http://gpt-home.local/api/callback"
            # check if the IP is on the same vlan as the requesting device
            ip_vlan = ".".join(ip.split(".")[:3])
            requesting_ip_vlan = ".".join(requesting_ip.split(".")[:3])
            if ip_vlan != requesting_ip_vlan:
                redirect_uri = f"http://{ip}/api/callback"
            set_key(ENV_FILE_PATH, "SPOTIFY_REDIRECT_URI", redirect_uri)
            os.environ["SPOTIFY_REDIRECT_URI"] = redirect_uri
            scopes = ",".join([
                "app-remote-control",
                "user-modify-playback-state",
                "user-read-playback-state",
                "user-read-currently-playing",
                "user-read-playback-position",
                "user-read-recently-played",
                "user-top-read",
                "user-read-email",
                "user-read-private",
                "playlist-read-private",
                "playlist-read-collaborative",
                "streaming",
                "user-library-read"
            ])
            os.environ["SPOTIFY_SCOPES"] = scopes
            set_key(ENV_FILE_PATH, "SPOTIFY_SCOPES", scopes)

            sp_oauth = spotipy.oauth2.SpotifyOAuth(
                client_id=spotify_client_id,
                client_secret=spotify_client_secret,
                redirect_uri=redirect_uri,
                scope=scopes,
            )
            auth_url = sp_oauth.get_authorize_url()
             
        # Restarting the service after setting up configurations for any of the services
        subprocess.run(["supervisorctl", "restart", "app"])

        logger.success(f"Successfully connected to {name}.")
        content = {"success": True}
        if auth_url:  # Only include auth_url if it has been set
            content["redirect_url"] = auth_url

        return JSONResponse(content=content)

    except Exception as e:
        logger.error(f"Error: {traceback.format_exc()}")
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/disconnect-service")
async def disconnect_service(request: Request):
    try:
        incoming_data = await request.json()
        name = incoming_data["name"].lower().strip()

        if name == "spotify":
            unset_key(ENV_FILE_PATH, "SPOTIFY_CLIENT_ID")
            unset_key(ENV_FILE_PATH, "SPOTIFY_CLIENT_SECRET")
            if os.path.exists(TOKEN_PATH):
                os.remove(TOKEN_PATH)
        elif name == "openweather":
            unset_key(ENV_FILE_PATH, "OPEN_WEATHER_API_KEY")
        elif name == "philipshue":
            unset_key(ENV_FILE_PATH, "PHILIPS_HUE_BRIDGE_IP")
            unset_key(ENV_FILE_PATH, "PHILIPS_HUE_USERNAME")
        elif name == "caldav":
            unset_key(ENV_FILE_PATH, "CALDAV_URL")
            unset_key(ENV_FILE_PATH, "CALDAV_USERNAME")
            unset_key(ENV_FILE_PATH, "CALDAV_PASSWORD")

        subprocess.run(["supervisorctl", "restart", "app"])
        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/get-service-statuses")
async def get_service_statuses(request: Request):
    try:
        env_config = None
        with open(ENV_FILE_PATH, "r") as f:
            env_config = f.read()

        if not env_config:
            return HTTPException(status_code=404, detail="Environment file not found")
        
        # Check if the bridge IP is on the same network as the local IP
        ip = subprocess.run(["hostname", "-I"], capture_output=True).stdout.decode().strip().split()[0]
        bridge_ip_match = re.search(r"PHILIPS_HUE_BRIDGE_IP=\'(\d+\.\d+\.\d+\.\d+)\'", env_config)
        bridge_ip = bridge_ip_match.group(1) if bridge_ip_match else None

        is_matching_scheme = True
        if bridge_ip:
            # Extract and compare the network parts of the IPs
            local_network = ".".join(ip.split(".")[:3])
            bridge_network = ".".join(bridge_ip.split(".")[:3])
            logger.debug(f"Local network: {local_network}")
            logger.debug(f"Bridge network: {bridge_network}")
            if local_network != bridge_network:
                is_matching_scheme = False

        # Check token expiry for Spotify
        token_info = get_stored_token()
        token_is_valid = valid_token(token_info) if token_info else False

        statuses = {
            "Spotify": "SPOTIFY_CLIENT_ID" in env_config and "SPOTIFY_CLIENT_SECRET" in env_config and token_is_valid,
            "OpenWeather": "OPEN_WEATHER_API_KEY" in env_config,
            "PhilipsHue": "PHILIPS_HUE_BRIDGE_IP" in env_config and "PHILIPS_HUE_USERNAME" in env_config and is_matching_scheme,
            "CalDAV": "CALDAV_URL" in env_config and "CALDAV_USERNAME" in env_config and "CALDAV_PASSWORD" in env_config
        }
        
        return JSONResponse(content={"statuses": statuses})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

## Spotify ##

# Callback for Spotify OAuth2
@app.get("/api/callback")
async def handle_callback(request: Request):
    try:
        code = request.query_params.get("code")
        scopes = os.environ['SPOTIFY_SCOPES']

        sp_oauth = spotipy.oauth2.SpotifyOAuth(
            client_id=os.environ['SPOTIFY_CLIENT_ID'],
            client_secret=os.environ['SPOTIFY_CLIENT_SECRET'],
            redirect_uri=os.environ['SPOTIFY_REDIRECT_URI'],
            scope=scopes,
        )

        if code:
            token_info = sp_oauth.get_access_token(code)
            
            if not token_info:
                return JSONResponse(content={"message": "Failed to get token info"}) 

            store_token(token_info)

            subprocess.run(["supervisorctl", "restart", "app"])
            
            return RedirectResponse(url="/", status_code=302)
        else:
            auth_url = sp_oauth.get_authorize_url(show_dialog=True)  # force reauthorization
            logger.error("No code provided.")
            return RedirectResponse(url=auth_url)

    except Exception as e:
        auth_url = sp_oauth.get_authorize_url(show_dialog=True)  # force reauthorization
        logger.error(f"Error: {traceback.format_exc()}")
        return RedirectResponse(url=auth_url)
    
def get_stored_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return json.load(f)
    except:
        return None

def store_token(token_info):
    with open(TOKEN_PATH, 'w') as f:
        json.dump(token_info, f)

def valid_token(token_info):
    now = time.time()
    return token_info and token_info["expires_at"] > now


@app.post("/spotify-token-exists")
async def spotify_token_exists(request: Request):
    try:
        token_info = get_stored_token()
        token_exists = True if token_info else False
        return JSONResponse(content={"token_exists": token_exists})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})
    
@app.post("/reauthorize-spotify")
async def reauthorize_spotify(request: Request):
    try:
        ip = subprocess.run(["hostname", "-I"], capture_output=True).stdout.decode().strip().split()[0]
        requesting_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or request.client.host
        # Setting REDIRECT URI explicitly to gpt-home.local
        redirect_uri = "http://gpt-home.local/api/callback"
        # check if the IP is on the same vlan as the requesting device
        ip_vlan = ".".join(ip.split(".")[:3])
        requesting_ip_vlan = ".".join(requesting_ip.split(".")[:3])
        if ip_vlan != requesting_ip_vlan:
            redirect_uri = f"http://{ip}/api/callback"
        set_key(ENV_FILE_PATH, "SPOTIFY_REDIRECT_URI", redirect_uri)
        os.environ["SPOTIFY_REDIRECT_URI"] = redirect_uri
        sp_oauth = spotipy.oauth2.SpotifyOAuth(
            client_id=os.environ['SPOTIFY_CLIENT_ID'],
            client_secret=os.environ['SPOTIFY_CLIENT_SECRET'],
            redirect_uri=redirect_uri,
            scope=os.environ['SPOTIFY_SCOPES'],
        )
        auth_url = sp_oauth.get_authorize_url()
        return JSONResponse(content={"redirect_url": auth_url})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/spotify-control")
async def spotify_control(request: Request):
    try:
        token_info = get_stored_token()

        if not token_info:
            return JSONResponse(content={"message": "No token information available. Please reauthorize with Spotify."}) 

        if not valid_token(token_info):
            # Try to refresh token
            sp_oauth = spotipy.oauth2.SpotifyOAuth(
                client_id=os.environ['SPOTIFY_CLIENT_ID'],
                client_secret=os.environ['SPOTIFY_CLIENT_SECRET'],
                redirect_uri=os.environ['SPOTIFY_REDIRECT_URI'],
                scope=os.environ['SPOTIFY_SCOPES'],
            )
            token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
            store_token(token_info)
            if not valid_token(token_info):
                logger.warning("Token expired. Need to reauthorize with Spotify.")
                return JSONResponse(content={"message": "Token expired. Need to reauthorize Spotify in the web interface."}, status_code=200)

        sp = spotipy.Spotify(auth=token_info['access_token'])

        incoming_data = await request.json()
        text = incoming_data.get("text", "").lower().strip()

        devices = sp.devices()
        logger.debug(f"Devices: {devices}")
        device_id = None
        for device in devices['devices']:

            if "GPT Home" in device['name']:
                device_id = device['id']
                break

        if not device_id:
            # restart spotifyd and try again
            subprocess.run(["supervisorctl", "stop", "spotifyd"])
            time.sleep(3)
            subprocess.run(["supervisorctl", "start", "spotifyd"])
            time.sleep(3)
            devices = sp.devices()
            logger.debug(f"Devices: {devices}")
            found = False
            for device in devices['devices']:
                if "GPT Home" in device['name']:
                    device_id = device['id']
                    found = True
                    break

            if not found:
                return JSONResponse(content={"message": "GPT Home not found as an available device."}) 

        if "play" in text:
            song = re.sub(r'^play\s+', '', text)  # Remove "play" at the beginning
            song = re.sub(r'\s+on\s+spotify$', '', song)  # Remove "on Spotify" at the end
            song = song.strip()
            if song:
                spotify_uris, message = await spotify_get_track_uris(song, sp)
                sp.start_playback(device_id=device_id, uris=spotify_uris)
                return JSONResponse(content={"message": message})
            else:
                sp.start_playback(device_id=device_id)
                return JSONResponse(content={"message": "Resumed playback."})

        elif "next" in text or "skip" in text:
            sp.next_track(device_id=device_id)
            return JSONResponse(content={"message": "Playing next track."})

        elif "previous" in text or "go back" in text:
            sp.previous_track(device_id=device_id)
            return JSONResponse(content={"message": "Playing previous track."})

        elif "pause" in text or "stop" in text:
            sp.pause_playback(device_id=device_id)
            return JSONResponse(content={"message": "Paused playback."})

        elif "volume" in text:
            volume = int(text.split('volume', 1)[1].strip())
            sp.volume(volume_percent=volume, device_id=device_id)
            return JSONResponse(content={"message": f"Set volume to {text.split('volume', 1)[1].strip()}."})
        
        elif "shuffle" in text:
            sp.shuffle(state=True, device_id=device_id)
            return JSONResponse(content={"message": "Shuffled playback."})
        
        elif "repeat" in text:
            sp.repeat(state="track", device_id=device_id)
            return JSONResponse(content={"message": "Repeating track."})

        else:
            logger.warning(f"Invalid command: {text}")
            return JSONResponse(content={"message": "Invalid command."}, status_code=400)

    except spotipy.exceptions.SpotifyException as e:
        # If the token has been revoked
        if e.http_status == 401:
            # Try to refresh token
            sp_oauth = spotipy.oauth2.SpotifyOAuth(
                client_id=os.environ['SPOTIFY_CLIENT_ID'],
                client_secret=os.environ['SPOTIFY_CLIENT_SECRET'],
                redirect_uri=os.environ['SPOTIFY_REDIRECT_URI'],
                scope=os.environ['SPOTIFY_SCOPES'],
            )
            token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
            store_token(token_info)
            if not valid_token(token_info):
                logger.warning("Token expired. Need to reauthorize with Spotify.")
                return JSONResponse(content={"message": "Token expired. Need to reauthorize Spotify in the web interface."}, status_code=200)
            else:
                return await spotify_control(request)
        else:
            logger.error(f"Error: {traceback.format_exc()}")
            return JSONResponse(content={"message": f"Something went wrong: Try to reauthorize Spotify in the web interface."}) 
    except Exception as e:
        logger.critical(f"Error: {traceback.format_exc()}")
        return JSONResponse(content={"message": f"Something went wrong: {e}"}) 

async def search_spotify(song: str, search_type: str, limit: int, sp):
    return sp.search(song, limit=limit, type=search_type)

async def get_podcast_episodes(show_id: str, sp):
    episodes = sp.show_episodes(show_id)
    return [episode['uri'] for episode in episodes['items']]

async def get_album_tracks(album_id: str, sp):
    tracks = sp.album_tracks(album_id)
    return [track['uri'] for track in tracks['items']]

async def get_artist_top_tracks(artist_id: str, sp):
    tracks = sp.artist_top_tracks(artist_id)
    return [track['uri'] for track in tracks['tracks']]

async def get_track_recommendations(track_id: str, sp):
    recommendations = sp.recommendations(seed_tracks=[track_id])
    return [track['uri'] for track in recommendations['tracks']]

async def spotify_get_track_uris(song: str, sp, search_types=['album', 'artist', 'track', 'show'], limit=1):
    for search_type in search_types:
        result = await search_spotify(song, search_type, limit, sp)
        
        if result[search_type+'s']['items']:
            item_id = result[search_type+'s']['items'][0]['id']
            item_name = result[search_type+'s']['items'][0]['name']

            if search_type == 'album':
                message = f"Playing album '{item_name} by {result[search_type+'s']['items'][0]['artists'][0]['name']}'..."
                return (await get_album_tracks(item_id, sp), message)
                
            elif search_type == 'artist':
                message = f"Playing top tracks based on artist '{item_name}'..."
                return (await get_artist_top_tracks(item_id, sp), message)
                
            elif search_type == 'track':
                message = f"Playing radio based on track '{item_name}'..."
                recommended_uris = await get_track_recommendations(item_id, sp)
                return ([item_id] + recommended_uris, message)
                
            elif search_type == 'show':
                message = f"Playing episodes from the show '{item_name}'..."
                return (await get_podcast_episodes(item_id, sp), message)
                
    return JSONResponse(content={"message": f"No match found for: {song}"}) 


## Philips Hue ##

def check_host_reachable(host: str, port: int = 80, timeout: float = 3.0) -> tuple[bool, str]:
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
            return False, "Network is unreachable - the bridge may be on a different subnet"
        elif e.errno == 113:  # No route to host
            return False, "No route to host - check if the IP address is correct and the bridge is on your network"
        return False, f"Network error: {e}"


async def set_philips_hue_username(bridge_ip: str):
    """Connect to Philips Hue bridge and retrieve username.
    
    First checks network reachability before attempting phue connection
    to provide faster feedback on network issues.
    """
    # Quick network reachability check (3 second timeout)
    is_reachable, error_msg = check_host_reachable(bridge_ip, port=80, timeout=3.0)
    
    if not is_reachable:
        logger.warning(f"Philips Hue bridge at {bridge_ip} is not reachable: {error_msg}")
        return JSONResponse(
            content={
                "message": f"Cannot reach Philips Hue bridge at {bridge_ip}. {error_msg}. "
                           f"Please verify the IP address is correct and the bridge is on the same network.",
                "success": False
            }, 
            status_code=408
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
        set_key(ENV_FILE_PATH, "PHILIPS_HUE_USERNAME", username)
        os.environ["PHILIPS_HUE_USERNAME"] = username  # Also set in environment
        logger.success(f"Successfully set Philips Hue username to {username}.")
        return JSONResponse(content={"message": "Successfully connected to Philips Hue bridge.", "success": True})
    except PhueRequestTimeout:
        logger.warning(f"Philips Hue bridge at {bridge_ip} timed out during connection.")
        return JSONResponse(
            content={
                "message": f"Connection to Philips Hue bridge at {bridge_ip} timed out. "
                           f"The bridge is reachable but not responding. Please try again.",
                "success": False
            }, 
            status_code=408
        )
    except Exception as e:
        error_msg = str(e)
        if "link button" in error_msg.lower():
            logger.info("Philips Hue bridge requires link button press.")
            return JSONResponse(
                content={
                    "message": "Please press the link button on your Philips Hue bridge and try again within 30 seconds.",
                    "success": False
                }, 
                status_code=401
            )
        logger.error(f"Philips Hue error: {error_msg}")
        return JSONResponse(
            content={
                "message": f"Failed to connect to Philips Hue: {error_msg}",
                "success": False
            }, 
            status_code=500
        ) 
