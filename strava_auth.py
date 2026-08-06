import time
import httpx
import os
import json

from pathlib import Path
from dotenv import load_dotenv

load_dotenv("./.env")

# Create reference for Env variables to authenticate Strava
TOKEN_FILE = Path(os.environ.get("STRAVA_TOKEN_PATH", "./strava_tokens.json"))
CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]

async def get_valid_access_token():
    tokens = json.loads(TOKEN_FILE.read_text())

    # Check token expiry and use if not expired
    if tokens["expires_at"] > time.time() + 60:
        return tokens["access_token"]
    
    # Re-authenticate if expired
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.strava.com/oauth/token",
            data= {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"]
            }
        )
    response.raise_for_status()
    new_tokens = response.json()

    # Write tokens out to env 
    TOKEN_FILE.write_text(json.dumps({
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens["refresh_token"],
        "expires_at": new_tokens["expires_at"]
    }))

    return new_tokens["access_token"]