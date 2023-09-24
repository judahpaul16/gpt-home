from dotenv import load_dotenv, set_key, unset_key, find_dotenv
from fastapi import FastAPI, Request, Response, status, redirect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from functions import logger
from typing import Optional
from pathlib import Path
from phue import Bridge
import subprocess
import traceback
import requests
import hashlib
import openai
import base64
import httpx
import json
import os
import re

ROOT_DIRECTORY = Path(__file__).parent
PARENT_DIRECTORY = ROOT_DIRECTORY.parent
ENV_FILE_PATH = ROOT_DIRECTORY / ".env"

load_dotenv(ENV_FILE_PATH)

app = FastAPI()

app.mount("/static", StaticFiles(directory=ROOT_DIRECTORY / "build" / "static"), name="static")

@app.get("/favicon.ico")
def read_favicon():
    return FileResponse(ROOT_DIRECTORY / "build" / "favicon.ico")

@app.get("/robot.gif")
def read_robot():
    return FileResponse(ROOT_DIRECTORY / "build" / "robot.gif")

## (NOTE: React route at the bottom of this file)

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
    
@app.post("/last-logs")
def last_logs(request: Request, last_line_number: Optional[int] = 0):
    log_file_path = PARENT_DIRECTORY / "events.log"

    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("r") as f:
            lines = f.readlines()
            if last_line_number < len(lines):
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

# Utility function to read environment config from .env file
def read_env_config():
    with open(ENV_FILE_PATH, "r") as f:
        env_config = f.read()
    return env_config

@app.post("/connect-service")
async def connect_service(request: Request):
    try:
        incoming_data = await request.json()
        name = incoming_data["name"].lower().strip()
        fields = incoming_data["fields"]

        # Initialize variables for Spotify
        client_id = None
        client_secret = None
        redirect_uri = None

        for key, value in fields.items():
            if name == "spotify":
                if key == "CLIENT ID":
                    set_key(ENV_FILE_PATH, "SPOTIFY_CLIENT_ID", value)
                    client_id = value
                elif key == "CLIENT SECRET":
                    set_key(ENV_FILE_PATH, "SPOTIFY_CLIENT_SECRET", value)
                    client_secret = value
                elif key == "REDIRECT URI":
                    # Setting REDIRECT URI explicitly to localhost
                    set_key(ENV_FILE_PATH, "SPOTIFY_REDIRECT_URI", "http://localhost/callback")
                    redirect_uri = "http://localhost/callback"
            elif name == "googlecalendar":
                if key == "ACCESS TOKEN":
                    set_key(ENV_FILE_PATH, "GOOGLE_CALENDAR_ACCESS_TOKEN", value)
            elif name == "philipshue":
                if key == "BRIDGE IP":
                    set_key(ENV_FILE_PATH, "PHILIPS_HUE_BRIDGE_IP", value)
                    await set_philips_hue_username(value)

        if name == "spotify" and client_id and client_secret and redirect_uri:
            auth_params = {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": "user-library-read"
            }
            # Construct the authorization URL
            auth_query = "&".join([f"{key}={value}" for key, value in auth_params.items()])
            auth_url = f"https://accounts.spotify.com/authorize?{auth_query}"

            return RedirectResponse(url=auth_url)

        # No further action specified for Google Calendar and Philips Hue as per original logic
        # Restarting the service after setting up configurations for any of the services
        subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])

        return JSONResponse(content={"success": True})

    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/disconnect-service")
async def disconnect_service(request: Request):
    try:
        incoming_data = await request.json()
        name = incoming_data["name"].lower().strip()

        if name == "spotify":
            unset_key(ENV_FILE_PATH, "SPOTIFY_CLIENT_ID")
            unset_key(ENV_FILE_PATH, "SPOTIFY_CLIENT_SECRET")
            unset_key(ENV_FILE_PATH, "SPOTIFY_REDIRECT_URI")
            unset_key(ENV_FILE_PATH, "SPOTIFY_ACCESS_TOKEN")
        elif name == "googlecalendar":
            unset_key(ENV_FILE_PATH, "GOOGLE_CALENDAR_ACCESS_TOKEN")
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
        env_config = read_env_config()

        statuses = {
            "Spotify": "SPOTIFY_ACCESS_TOKEN" in env_config,
            "GoogleCalendar": "GOOGLE_CALENDAR_ACCESS_TOKEN" in env_config,
            "PhilipsHue": "PHILIPS_HUE_BRIDGE_IP" in env_config and "PHILIPS_HUE_USERNAME" in env_config
        }

        return JSONResponse(content={"statuses": statuses})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})


## Spotify ##

# Callback for Spotify
@app.get("/callback")
async def callback(request: Request):
    try:
        # Fetch the code from query parameters instead of JSON payload
        code = request.query_params.get("code")
        if not code:
            raise Exception("Authorization code not found in query parameters")

        load_dotenv(ENV_FILE_PATH)

        # Get auth headers
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

        # Base64 encode the client ID and secret
        base64_encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        # Prepare the data and headers for the post request
        auth_data = {
            "redirect_uri": redirect_uri,
            "code": code,
            "grant_type": "authorization_code"
        }
        auth_headers = {'Authorization': f"Basic {base64_encoded}"}

        # Asynchronously make the request
        async with httpx.AsyncClient() as client:
            response = await client.post("https://accounts.spotify.com/api/token", data=auth_data, headers=auth_headers)

        if response.status_code == 200:
            json_response = response.json()
            access_token = json_response.get("access_token", None)
            refresh_token = json_response.get("refresh_token", None)
            if access_token and refresh_token:
                set_key(ENV_FILE_PATH, "SPOTIFY_ACCESS_TOKEN", access_token)
                set_key(ENV_FILE_PATH, "SPOTIFY_REFRESH_TOKEN", refresh_token)
                print("Successfully connected to Spotify.")
                subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])
                return JSONResponse(content={"success": True})
            else:
                raise Exception(f"Something went wrong: {response.text}")
        else:
            raise Exception(f"Something went wrong: {response.text}")

    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

def search_song_get_uri(song_name: str):
    access_token = os.getenv('SPOTIFY_ACCESS_TOKEN')
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"q": song_name, "type": "track", "limit": 1}
    response = requests.get("https://api.spotify.com/v1/search", headers=headers, params=params)
    
    if response.status_code == 200:
        json_response = response.json()
        tracks = json_response.get("tracks", {}).get("items", [])
        if tracks:
            return tracks[0].get("uri", None)
    else:
        logger.error(f"Error: {response.text}")
        raise Exception(f"Something went wrong: {response.text}")
    
@app.post("/spotify-control")
async def spotify_control(request: Request):
    try:
        incoming_data = await request.json()
        text = incoming_data.get("text", "").lower().strip()

        if "play" in text:
            song = re.sub(r'(play\s+)', '', text, count=1).strip()
            if song:
                spotify_uri = await search_song_get_uri(song)
                if spotify_uri:
                    subprocess.run(["playerctl", "open", spotify_uri])
                    return JSONResponse(content={"success": True, "message": f"Playing {song} on Spotify."})
            else:
                subprocess.run(["playerctl", "play"])
                return JSONResponse(content={"success": True, "message": "Resumed playback."})

        elif "next" in text or "skip" in text:
            subprocess.run(["playerctl", "next"])
            return JSONResponse(content={"success": True, "message": "Playing next track."})

        elif "previous" in text or "go back" in text:
            subprocess.run(["playerctl", "previous"])
            return JSONResponse(content={"success": True, "message": "Playing previous track."})

        elif "pause" in text or "stop" in text:
            subprocess.run(["playerctl", "pause"])
            return JSONResponse(content={"success": True, "message": "Paused playback."})

        else:
            return JSONResponse(content={"success": False, "message": "Invalid command."})

    except Exception as e:
        return JSONResponse(content={"success": False, "message": str(e), "traceback": traceback.format_exc()})


## Google Calendar ##

# ...


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


## React App ##

# pass all get requests to the react app except for the ones above
@app.get("/{path:path}")
def read_root(path: str):
    return FileResponse(ROOT_DIRECTORY / "build" / "index.html")