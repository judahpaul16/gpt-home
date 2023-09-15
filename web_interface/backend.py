from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/static", StaticFiles(directory="build"), name="static")

@app.get("/")
def read_root():
    return FileResponse("build/index.html")
