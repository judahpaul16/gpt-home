from fastapi import FastAPI, Request, Response, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

ROOT_DIRECTORY = Path(__file__).parent
PARENT_DIRECTORY = ROOT_DIRECTORY.parent

app = FastAPI()

app.mount("/static", StaticFiles(directory=ROOT_DIRECTORY / "build" / "static"), name="static")

last_line_number = 0  # Keep track of the last sent line number

@app.get("/favicon.ico")
def read_favicon():
    return FileResponse(ROOT_DIRECTORY / "build" / "favicon.ico")

@app.get("/{path:path}")
def read_root(path: str):
    return FileResponse(ROOT_DIRECTORY / "build" / "index.html")

@app.post("/logs")
def logs(request: Request):
    global last_line_number  # Declare the global variable

    log_file_path = PARENT_DIRECTORY / "events.log"

    if log_file_path.exists() and log_file_path.is_file():
        with log_file_path.open("r") as f:
            lines = f.readlines()

        new_logs = lines[last_line_number:]  # Only take the logs that have not been sent yet
        last_line_number = len(lines)  # Update the last line number

        log_data = "".join(new_logs)
        return JSONResponse(content={"log_data": log_data})
    else:
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Log file not found")
