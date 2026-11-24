"""Upload the freshly built video using output/latest_video.json.

Shape matches the Velocity uploaders, so the same OAuth credentials work:
YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN in .env or Actions secrets.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from PIL import Image

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

META_PATH = Path("output") / "latest_video.json"
RESULT_PATH = Path("output") / "upload_result.json"

CLIENT_ID = os.getenv("YT_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN", "")


def service():
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        raise ValueError("Missing YouTube credentials")
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def thumbnail_buffer(path: str, max_size: int = 2 * 1024 * 1024):
    img = Image.open(path).convert("RGB")
    quality = 92
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= max_size or quality <= 20:
            buf.seek(0)
            return buf
        quality -= 6


def upload() -> bool:
    if not META_PATH.exists():
        print("[youtube] latest_video.json missing - skipping")
        return False

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    video_path = Path(meta["video_path"])
    if not video_path.exists():
        print(f"[youtube] video not found: {video_path}")
        return False

    privacy = str(meta.get("privacy", "private"))
    body = {
        "snippet": {
            "title": str(meta.get("title", ""))[:100],
            "description": str(meta.get("description", ""))[:4900],
            "tags": meta.get("tags", [])[:30],
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"[youtube] {body['snippet']['title']}")
    print(f"[youtube] {video_path.name} "
          f"({video_path.stat().st_size // (1024 * 1024)} MB, {privacy})")

    yt = service()

    def new_request():
        media = MediaFileUpload(str(video_path), chunksize=16 * 1024 * 1024,
                                resumable=True)
        return yt.videos().insert(part="snippet,status", body=body, media_body=media)

    request = new_request()
    response = None
    rejected = 0
    attempts = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"[youtube] upload {int(status.progress() * 100)}%")
        except HttpError as exc:
            if exc.resp.status == 400:
                rejected += 1
                if rejected > 1:
                    raise
                print(f"[youtube] rejected, retrying once: {exc}")
                request = new_request()
            elif "dailyLimitExceeded" in str(exc) or "Uploads per day" in str(exc):
                print(f"[youtube] daily upload limit reached: {exc}")
                raise
            else:
                attempts += 1
                if attempts > 3:
                    raise
                print(f"[youtube] chunk failed ({attempts}/3): {exc}")
                time.sleep(15)

    video_id = response["id"]
    url = f"https://youtube.com/watch?v={video_id}"
    print(f"[youtube] published {url}")

    thumb = Path(meta.get("thumbnail_path", ""))
    if thumb.exists():
        try:
            yt.thumbnails().set(
                videoId=video_id,
                media_body=MediaIoBaseUpload(thumbnail_buffer(str(thumb)),
                                             mimetype="image/jpeg", resumable=False),
            ).execute()
            print("[youtube] thumbnail set")
        except Exception as exc:  # noqa: BLE001 - thumbnail is best effort
            print(f"[youtube] thumbnail failed: {exc}")

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps({
        "video_id": video_id, "url": url,
        "title": body["snippet"]["title"],
        "uploaded_at": time.time(),
    }, indent=2), encoding="utf-8")
    return True


if __name__ == "__main__":
    try:
        sys.exit(0 if upload() else 1)
    except Exception as exc:  # noqa: BLE001 - workflow boundary
        print(f"[youtube] failed: {exc}")
        sys.exit(1)
