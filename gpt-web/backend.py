from fastapi import FastAPI, Request, Response, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
from pathlib import Path

ROOT_DIRECTORY = Path(__file__).parent
PARENT_DIRECTORY = ROOT_DIRECTORY.parent

app = FastAPI()

app.mount("/static", StaticFiles(directory=ROOT_DIRECTORY / "build" / "static"), name="static")

@app.get("/favicon.ico")
def read_favicon():
    return FileResponse(ROOT_DIRECTORY / "build" / "favicon.ico")

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