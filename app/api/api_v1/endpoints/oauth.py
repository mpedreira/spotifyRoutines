"""
OAuth callback endpoint for Spotify authorization.
"""
# pylint: disable=E0401,E0611

from urllib.parse import urlencode
from fastapi import APIRouter, Query, HTTPException, Body
import requests

router = APIRouter()

# OAuth constants
TOKEN_URL = "https://accounts.spotify.com/api/token"

# Temporary storage for OAuth code (in-memory, resets on restart)
_oauth_state = {"code": None, "error": None}


@router.get("/callback")
def oauth_callback(code: str = Query(None), error: str = Query(None)):
    """
    OAuth callback endpoint for Spotify authorization.
    Receives the authorization code from Spotify.
    """
    if error:
        _oauth_state["error"] = error
        raise HTTPException(status_code=400, detail=f"Authorization error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    _oauth_state["code"] = code

    return {
        "status": "authorized",
        "message": "Authorization successful. You can close this window and return to the script."
    }


@router.post("/get-refresh-token")
def get_refresh_token(payload: dict = Body(...)):
    """
    Exchange the OAuth code for a refresh token.
    Call this after the user has authorized.
    """
    global _oauth_state

    if _oauth_state["error"]:
        raise HTTPException(status_code=400, detail=f"Authorization error: {_oauth_state['error']}")

    if not _oauth_state["code"]:
        raise HTTPException(status_code=400, detail="No authorization code available. Visit /oauth/authorize first.")

    code = _oauth_state["code"]
    client_id = str(payload.get("client_id") or "").strip()
    client_secret = str(payload.get("client_secret") or "").strip()
    redirect_uri = str(payload.get("redirect_uri") or "http://127.0.0.1:8000/api/v1/oauth/callback").strip()

    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="client_id and client_secret are required")

    # Exchange code for refresh token
    try:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        response = requests.post(TOKEN_URL, data=data, timeout=10)

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {response.text}")

        payload = response.json()
        refresh_token = payload.get("refresh_token")

        if not refresh_token:
            raise HTTPException(status_code=400, detail="No refresh token in response")

        # Reset state
        _oauth_state["code"] = None
        _oauth_state["error"] = None

        return {"refresh_token": refresh_token}

    except requests.RequestException as exc:
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {str(exc)}") from exc


@router.get("/authorize")
def authorize(
    client_id: str = Query(...),
    scope: str = Query(default="user-read-private user-read-email user-read-playback-state user-modify-playback-state playlist-read-private playlist-read-collaborative"),
    redirect_uri: str = Query(default="http://127.0.0.1:8000/api/v1/oauth/callback"),
    show_dialog: bool = Query(default=True),
):
    """
    Generate Spotify authorization URL.
    Returns the URL to redirect the user to for authorization.
    """
    auth_url = (
        "https://accounts.spotify.com/authorize?" + urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope,
            "show_dialog": "true" if show_dialog else "false",
        })
    )
    return {"authorization_url": auth_url}
