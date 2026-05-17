"""
YouTube → WAV converter
Run with: uvicorn server:app --reload
Then open http://localhost:8000
"""
import os
import uuid
import re
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

app = FastAPI()

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "downloads"
OUTPUT_DIR.mkdir(exist_ok=True)


class ConvertRequest(BaseModel):
    url: str


def _safe_filename(title: str) -> str:
    """Strip characters that break Windows filenames."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:80] or "audio").rstrip(". ")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (BASE_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/convert")
async def convert(req: ConvertRequest, bg: BackgroundTasks):
    job_id = str(uuid.uuid4())

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(OUTPUT_DIR / f"{job_id}.%(ext)s"),
        "restrictfilenames": True,
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }],
        # Match YouTube's native 48kHz Opus → no resampling artifacts.
        "postprocessor_args": [
            "-ar", "48000",
            "-ac", "2",
            "-sample_fmt", "s16",
        ],
        "quiet": False,
        "no_warnings": False,
        "progress" : True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            title = info.get("title", "audio")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Conversion failed: {e}")

    wav_path = OUTPUT_DIR / f"{job_id}.wav"
    if not wav_path.exists():
        raise HTTPException(status_code=500, detail="WAV file was not produced")

    # Delete the file after it's been sent.
    bg.add_task(lambda p: os.path.exists(p) and os.unlink(p), str(wav_path))

    return FileResponse(
        wav_path,
        media_type="audio/wav",
        filename=f"{_safe_filename(title)}.wav",
    )