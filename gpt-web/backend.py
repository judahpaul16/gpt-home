from dotenv import load_dotenv, set_key, unset_key, find_dotenv
from fastapi import FastAPI, Request, Response, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import HTTPException
from typing import Optional
from pathlib import Path
import subprocess
import traceback
import hashlib
import openai
import json
import os

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

@app.get("/{path:path}")
def read_root(path: str):
    return FileResponse(ROOT_DIRECTORY / "build" / "index.html")

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

# Utility function to read environment config from .env file
def read_env_config():
    load_dotenv(ENV_FILE_PATH)
    return {key: os.getenv(key) for key in os.environ if not key.startswith('_')}

@app.post("/connect-service")
async def connect_service(request: Request):
    try:
        incoming_data = await request.json()
        name = incoming_data["name"].lower().strip()
        fields = incoming_data["fields"]

        for key, value in fields.items():
            if name == "spotify":
                set_key(ENV_FILE_PATH, "SPOTIFY_ACCESS_TOKEN", value)
            elif name == "googlecalendar":
                set_key(ENV_FILE_PATH, "GOOGLE_CALENDAR_ACCESS_TOKEN", value)
            elif name == "phillipshue":
                if 'Bridge IP Address' in key:
                    set_key(ENV_FILE_PATH, "HUE_BRIDGE_IP", value)
                elif 'Username' in key:
                    set_key(ENV_FILE_PATH, "HUE_BRIDGE_USERNAME", value)

        subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])

        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/disconnect-service")
async def disconnect_service(request: Request):
    try:
        incoming_data = await request.json()
        fields = incoming_data["fields"]

        for field in fields:
            unset_key(ENV_FILE_PATH, field)
            # remove line from .env file
            with open(ENV_FILE_PATH, "r") as f:
                lines = f.readlines()
            with open(ENV_FILE_PATH, "w") as f:
                for line in lines:
                    if not line.startswith(field):
                        f.write(line)

        subprocess.run(["sudo", "systemctl", "restart", "gpt-home.service"])

        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})

@app.post("/is-service-connected")
async def is_service_connected(request: Request):
    try:
        incoming_data = await request.json()
        fields = incoming_data["fields"]
        env_config = read_env_config()
        
        for field in fields:
            if field not in env_config:
                return JSONResponse(content={"status": False})

        return JSONResponse(content={"status": True})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "traceback": traceback.format_exc()})