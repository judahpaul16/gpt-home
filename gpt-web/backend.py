from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI()

app.mount("/static", StaticFiles(directory="build/static"), name="static")

@app.get("/favicon.ico")
def read_favicon():
    return FileResponse(Path("build/favicon.ico"))

@app.get("/")
def read_root():
    return FileResponse(Path("build/index.html"))