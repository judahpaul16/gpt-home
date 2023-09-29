from dotenv import load_dotenv, set_key, unset_key
from fastapi import FastAPI, Request, Response, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from spotipy.oauth2 import SpotifyClientCredentials
from fastapi.exceptions import HTTPException
from datetime import datetime, timedelta
from functions import logger
from typing import Optional
import spotipy.util as util
from pathlib import Path
from phue import Bridge
import subprocess
import traceback
import requests
import spotipy
import hashlib
import openai
import base64
import httpx
import time
import json
import os
import re

ROOT_DIRECTORY = Path(__file__).parent
PARENT_DIRECTORY = ROOT_DIRECTORY.parent
ENV_FILE_PATH = ROOT_DIRECTORY / ".env"
TOKEN_PATH = "spotify_token.json"

load_dotenv(ENV_FILE_PATH)

app = FastAPI()

app.mount("/static", StaticFiles(directory=ROOT_DIRECTORY / "build" / "static"), name="static")

@app.get("/favicon.ico")
def read_favicon():
    return FileResponse(ROOT_DIRECTORY / "build" / "favicon.ico")

@app.get("/robot.gif")
def read_robot():
    return FileResponse(ROOT_DIRECTORY / "build" / "robot.gif")

## React App + API Calls ##

# Catch-all route for React and other specific FastAPI routes
@app.get("/{path:path}")
async def read_root(request: Request, path: str):
    if path == 'api/callback':
        return await handle_callback(request)
    else:
        return FileResponse(ROOT_DIRECTORY / "build" / "index.html")
    
@app.post("/get-local-ip")
def get_local_ip():
    ip = subprocess.run(["hostname", "-I"], capture_output=True).stdout.decode().split()[0]
    return JSONResponse(content={"ip": ip})

## Event Logs ##

@app.post("/logs")
def logs(request: Request):
    log_file_path = PARENT_DIRECTORY / "events.log"

    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("r") as f:
            log_data = f.read()
        return JSONResponse(content={"log_data": log_data})
    else:
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Log file not found")
    
@app.post("/new-logs")
def last_logs(request: Request, last_line_number: Optional[int] = 0):
    log_file_path = PARENT_DIRECTORY / "events.log"

    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("r") as f:
            lines = f.readlines()
            if len(lines) != last_line_number:
                new_logs = lines[last_line_number:]
                return JSONResponse(content={"last_logs": new_logs, "new_last_line_number": len(lines)})
            else:
                return JSONResponse(content={"last_logs": [], "new_last_line_number": len(lines)})
    else:
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Log file not found")

@app.post("/clear-logs")
def clear_logs(request: Request):
    log_file_path = PARENT_DIRECTORY / "events.log"

    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("w") as f:
            f.write("")
        return Response(status_code=status.HTTP_200_OK, content="Logs cleared")
    else:
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Log file not found")

## Settings ##

@app.post("/settings")
async def settings(request: Request):
    settings_path = PARENT_DIRECTORY / "settings.json"
    incoming_data = await request.json()

    if 'action' in incoming_data and incoming_data['action'] == 'read':
        if settings_path.exists() and settings_path.is_file():
            with settings_path.open("r") as f:
                settings = json.load(f)
            return JSONResponse(content=settings)
        else:
            return HTTPException(status_code=404, detail="Settings not found")

    elif 'action' in incoming_data and incoming_data['action'] == 'update':
        new_settings = incoming_data['data']
        with settings_path.open("w") as f:
            json.dump(new_settings, f)
        subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])
        return JSONResponse(content=new_settings)
    else:
        return HTTPException(status_code=400, detail="Invalid action")
    
@app.post("/gptRestart")
async def gpt_restart(request: Request):
    subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])
    return JSONResponse(content={"success": True})

@app.post("/spotifyRestart")
async def spotify_restart(request: Request):
    subprocess.run(["sudo", "systemctl", "restart", "spotifyd"])
    return JSONResponse(content={"success": True})

@app.post("/reboot")
async def reboot(request: Request):
    subprocess.run(["sudo", "reboot"])
    return JSONResponse(content={"success": True})

@app.post("/shutdown")
async def shutdown(request: Request):
    subprocess.run(["sudo", "shutdown", "now"])
    return JSONResponse(content={"success": True})

@app.post("/availableModels")
async def available_models():
    try:
        # Get available models from OpenAI
        openai.api_key = os.getenv("OPENAI_API_KEY")
        model_list = openai.Model.list()
        
        # Filter to only keep supported models.
        supported_models = [model['id'] for model in model_list['data'] if "gpt" in model['id'].lower()]

        return JSONResponse(content={"models": supported_models})
    except Exception as e:
        return HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
@app.post("/updateModel")
async def update_model(request: Request):
    try:
        incoming_data = await request.json()
        model_id = incoming_data['model_id']
        
        # Get available models from OpenAI
        openai.api_key = os.getenv("OPENAI_API_KEY")
        model_list = openai.Model.list()
        
        # Filter to only keep supported models.
        supported_models = [model['id'] for model in model_list['data'] if "gpt" in model['id'].lower()]
        
        # Check if model is supported
        if model_id in supported_models:
            # Update settings.json
            settings_path = PARENT_DIRECTORY / "settings.json"
            with settings_path.open("r") as f:
                settings = json.load(f)
            settings['model'] = model_id
            with settings_path.open("w") as f:
                json.dump(settings, f)
            
            # Restart service
            subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])
            
            return JSONResponse(content={"model": model_id})
        else:
            return HTTPException(status_code=400, detail=f"Model {model_id} not supported")
    except Exception as e:
        return HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


## Password ##

@app.on_event("startup")
async def startup_event():
    password_file_path = PARENT_DIRECTORY / "hashed_password.txt"
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
        password_file_path = PARENT_DIRECTORY / "hashed_password.txt"

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
        password_file_path = PARENT_DIRECTORY / "hashed_password.txt"

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
        password_file_path = PARENT_DIRECTORY / "hashed_password.txt"
        
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
                    await set_philips_hue_username(value)

        if name == "spotify":
            spotify_username = fields.get("USERNAME")
            spotify_password = fields.get("PASSWORD")
            os.environ["SPOTIFY_USERNAME"] = spotify_username
            
            if spotify_username and spotify_password:
                # Update the spotifyd configuration dynamically
                config_path = PARENT_DIRECTORY.parent / ".config/spotifyd/spotifyd.conf"
                with open(config_path, "w") as file:
                    file.write("[global]\n")
                    file.write(f"username = \"{spotify_username}\"\n")
                    file.write(f"password = \"{spotify_password}\"\n")
                    file.write("backend = \"alsa\"\n")
                    file.write("device_name = \"GPT Home\"\n")
                    file.write("bitrate = 320\n")
                    file.write("cache_path = \"/home/ubuntu/.spotifyd/cache\"\n")
                    file.write("discovery = false\n")
                
                # Restart spotifyd to apply changes
                subprocess.run(["sudo", "systemctl", "restart", "spotifyd"], check=True)

            # Setting REDIRECT URI explicitly to local ip
            ip = subprocess.run(["hostname", "-I"], capture_output=True).stdout.decode().split()[0]
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

            sp_oauth = spotipy.oauth2.SpotifyOAuth(
                client_id=spotify_client_id,
                client_secret=spotify_client_secret,
                redirect_uri=redirect_uri,
                scope=scopes,
            )
            auth_url = sp_oauth.get_authorize_url()
             
        # Restarting the service after setting up configurations for any of the services
        subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])

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

        subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])
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
            "PhilipsHue": "PHILIPS_HUE_BRIDGE_IP" in env_config and "PHILIPS_HUE_USERNAME" in env_config and is_matching_scheme
        }
        
        return JSONResponse(content={"statuses": statuses})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

## Spotify ##

# Callback for Spotify OAuth2
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
                raise Exception("Failed to get token info")

            store_token(token_info)

            subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])
            
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
        token_exists = valid_token(token_info) if token_info else False
        return JSONResponse(content={"token_exists": token_exists})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})
    
@app.post("/reauthorize-spotify")
async def reauthorize_spotify(request: Request):
    try:
        sp_oauth = spotipy.oauth2.SpotifyOAuth(
            client_id=os.environ['SPOTIFY_CLIENT_ID'],
            client_secret=os.environ['SPOTIFY_CLIENT_SECRET'],
            redirect_uri=os.environ['SPOTIFY_REDIRECT_URI'],
            scope=os.environ['SPOTIFY_SCOPES'],
        )
        auth_url = sp_oauth.get_authorize_url(show_dialog=True)
        return JSONResponse(content={"redirect_url": auth_url})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/spotify-control")
async def spotify_control(request: Request):
    try:
        token_info = get_stored_token()

        if not token_info:
            raise Exception("No token information available. Please reauthorize with Spotify.")

        if not valid_token(token_info):
            logger.warning("Token expired. Need to reauthorize with Spotify.")
            raise spotipy.exceptions.SpotifyException(401, -1, "The access token expired. Please reauthorize in the web interface.")

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
            raise Exception("GPT Home not found as an available device.")

        if "play" in text:
            song = re.sub(r'(play\s+)', '', text, count=1).strip()
            if song:
                spotify_uris = await spotify_get_track_uris(song, sp)
                sp.start_playback(device_id=device_id, uris=spotify_uris)
                logger.success(f"Playing radio based on {song}.")
                return JSONResponse(content={"message": f"Playing radio based on {song}."})
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
        if e.http_status == 401 and e.http_error_msg == "The access token expired":
            logger.warning("Token expired. Need to reauthorize with Spotify.")
            raise Exception("Token expired. Need to reauthorize with Spotify.")
        else:
            logger.error(f"Error: {traceback.format_exc()}")
            raise Exception(f"Something went wrong: {e}")
    except Exception as e:
        logger.critical(f"Error: {traceback.format_exc()}")
        raise Exception(f"Something went wrong: {e}")

async def spotify_get_track_uris(song: str, sp):
    # Search for an album
    result = sp.search(q=song, type='album', limit=1)
    if result['albums']['items']:
        album_id = result['albums']['items'][0]['id']
        tracks = sp.album_tracks(album_id)
        if tracks['items']:
            return [track['uri'] for track in tracks['items']]  # Return all tracks of the album

    # If no album is found, search for an artist
    result = sp.search(q=song, type='artist', limit=1)
    if result['artists']['items']:
        artist_id = result['artists']['items'][0]['id']

        # Get top tracks or recommendations based on the artist
        top_tracks = sp.artist_top_tracks(artist_id)
        if top_tracks and top_tracks['tracks']:
            return [track['uri'] for track in top_tracks['tracks']]  # Return top tracks of the artist

    # If no artist is found, search for a track
    result = sp.search(q=song, type='track', limit=1)
    if result['tracks']['items']:
        track_uri = result['tracks']['items'][0]['uri']

        # Get recommendations based on the track to emulate a radio experience
        recommended_tracks = sp.recommendations(seed_tracks=[track_uri], limit=9)  # fetching top 9 recommended tracks
        if recommended_tracks and recommended_tracks['tracks']:
            recommended_uris = [track['uri'] for track in recommended_tracks['tracks']]
            return [track_uri] + recommended_uris

    # If nothing matches, raise an exception or handle accordingly
    raise Exception(f"No match found for: {song}")


## Philips Hue ##

async def set_philips_hue_username(bridge_ip: str):
    try:
        b = Bridge(bridge_ip)
        b.connect()
        b.get_api()
        logger.success("Successfully connected to Philips Hue bridge.")
        username = b.username
        set_key(ENV_FILE_PATH, "PHILIPS_HUE_USERNAME", username)
        logger.success(f"Successfully set Philips Hue username to {username}.")
    except Exception as e:
        logger.error(f"Error: {traceback.format_exc()}")
        raise Exception(f"Something went wrong: {e}")
