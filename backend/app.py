from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import shutil
import os
from model_utils import analyze_with_heuristics

app = FastAPI()

@app.post("/analyze")
async def analyze_scan(file: UploadFile = File(...)):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = analyze_with_heuristics(temp_path)
    os.remove(temp_path)

    return JSONResponse(content={"heuristic": result})
