"""
Push channel branding to YouTube.

Sets:
  - channel description  (brandingSettings.channel.description)
  - channel keywords     (brandingSettings.channel.keywords)
  - channel banner       (channelBanners.insert -> bannerExternalUrl)

Does NOT set the profile picture: the YouTube Data API has no endpoint for the channel
avatar. Upload brand/avatar_1024.png manually in YouTube Studio.

    python setup_channel.py            # dry run, prints what would change
    python setup_channel.py --apply    # actually writes

Credentials, in order of preference:
  1. YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN in the environment
  2. the token json at TOKEN_JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

BASE = Path(__file__).resolve().parent
TOKEN_JSON = Path(os.getenv("YT_TOKEN_JSON",
                            r"D:\E agy cli\E api tokens\.WardRounds\token_WardRounds.json"))
BANNER = BASE / "brand" / "banner_2560x1440.png"
DESCRIPTION = BASE / "brand" / "channel_description.txt"
KEYWORDS = BASE / "brand" / "keywords.txt"

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def credentials() -> Credentials:
    cid = os.getenv("YT_CLIENT_ID")
    secret = os.getenv("YT_CLIENT_SECRET")
    refresh = os.getenv("YT_REFRESH_TOKEN")

    if not all([cid, secret, refresh]) and TOKEN_JSON.exists():
        data = json.loads(TOKEN_JSON.read_text(encoding="utf-8"))
        cid = cid or data.get("client_id")
        secret = secret or data.get("client_secret")
        refresh = refresh or data.get("refresh_token")
        print(f"  using token file: {TOKEN_JSON.name} ({data.get('nickname', '?')})")

    if not all([cid, secret, refresh]):
        raise SystemExit("missing YouTube credentials")

    creds = Credentials(
        None,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid,
        client_secret=secret,
    )
    creds.refresh(Request())
    return creds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes")
    args = ap.parse_args()

    description = DESCRIPTION.read_text(encoding="utf-8").strip()
    keywords = " ".join(f'"{k.strip()}"' for k in
                        KEYWORDS.read_text(encoding="utf-8").replace("\n", ",").split(",")
                        if k.strip())

    print(f"  description : {len(description)} chars")
    print(f"  keywords    : {len(keywords)} chars")
    print(f"  banner      : {BANNER.name} ({BANNER.stat().st_size // 1024} KB)")

    yt = build("youtube", "v3", credentials=credentials())

    current = yt.channels().list(part="snippet,brandingSettings", mine=True).execute()
    if not current.get("items"):
        raise SystemExit("no channel on this account")
    channel = current["items"][0]
    channel_id = channel["id"]
    title = channel["snippet"]["title"]
    print(f"  channel     : {title}  ({channel_id})")

    if not args.apply:
        print("\n  dry run - pass --apply to write")
        return 0

    banner_url = None
    if BANNER.exists():
        print("  uploading banner...")
        up = yt.channelBanners().insert(
            media_body=MediaFileUpload(str(BANNER), mimetype="image/png",
                                       resumable=False)
        ).execute()
        banner_url = up["url"]
        print(f"  banner url  : {banner_url[:80]}...")

    branding = channel.get("brandingSettings", {})
    branding.setdefault("channel", {})
    branding["channel"]["description"] = description
    branding["channel"]["keywords"] = keywords
    branding["channel"].setdefault("country", "IN")
    if banner_url:
        branding.setdefault("image", {})
        branding["image"]["bannerExternalUrl"] = banner_url

    body = {
        "id": channel_id,
        "brandingSettings": branding,
    }
    try:
        yt.channels().update(part="brandingSettings", body=body).execute()
        print("  updated     : description, keywords" + (", banner" if banner_url else ""))
    except HttpError as exc:
        print(f"  update failed: {exc}")
        print("  (the refresh token may lack the 'youtube' or 'youtube.force-ssl' scope)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
