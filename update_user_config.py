#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to update or create Spotify users in config.ini.
Reads client_id and client_secret from environment variables.
Automatically obtains refresh_token via OAuth using FastAPI endpoints.
"""

import os
import sys
import json
import time
import webbrowser
from pathlib import Path
import requests


# FastAPI OAuth endpoints
API_BASE = "http://127.0.0.1:8000/api/v1/oauth"
SCOPE = (
    "user-read-private "
    "user-read-email "
    "user-read-playback-state "
    "user-modify-playback-state "
    "playlist-read-private "
    "playlist-read-collaborative"
)


def validate_client_credentials(client_id, client_secret):
    """Validate Spotify client credentials before starting OAuth flow."""
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )
    if response.status_code != 200:
        detail = ""
        try:
            detail = response.json().get("error_description") or response.text
        except ValueError:
            detail = response.text
        raise ValueError(f"Spotify rejected client credentials: {detail}")


def get_refresh_token(client_id, client_secret):
    """Get refresh token via OAuth flow using FastAPI endpoints."""
    print("\n🔐 Starting Spotify OAuth flow...\n")

    try:
        # Step 1: Get authorization URL from FastAPI
        print("📍 Getting authorization URL from FastAPI...")
        auth_response = requests.get(
            f"{API_BASE}/authorize",
            params={
                "client_id": client_id,
                "scope": SCOPE,
                "redirect_uri": "http://127.0.0.1:8000/api/v1/oauth/callback",
                "show_dialog": "true",
            },
            timeout=10
        )
        auth_response.raise_for_status()
        auth_url = auth_response.json()["authorization_url"]

        # Step 2: Open authorization URL in browser
        print("📱 Opening Spotify authorization in your browser...")
        webbrowser.open(auth_url)

        # Step 3: Wait for user authorization (FastAPI will receive the callback)
        print("⏳ Waiting for authorization (checking every 2 seconds)...")
        max_wait = 120  # 2 minutes
        waited = 0

        while waited < max_wait:
            try:
                # Try to exchange code for refresh token
                token_response = requests.post(
                    f"{API_BASE}/get-refresh-token",
                    json={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": "http://127.0.0.1:8000/api/v1/oauth/callback"
                    },
                    timeout=10
                )

                if token_response.status_code == 200:
                    refresh_token = token_response.json()["refresh_token"]
                    print(f"✅ Authorization successful\n")
                    return refresh_token
                elif "No authorization code available" not in token_response.text:
                    # Error other than "code not yet received"
                    raise ValueError(token_response.json().get("detail", "Unknown error"))

            except requests.exceptions.ConnectionError:
                print("❌ Error: Cannot connect to FastAPI on http://127.0.0.1:8000")
                print("   Make sure FastAPI is running: uvicorn app.main:app --reload")
                sys.exit(1)

            time.sleep(2)
            waited += 2

        raise ValueError("Authorization timeout - user did not authorize within 2 minutes")

    except Exception as exc:
        raise ValueError(f"OAuth error: {str(exc)}") from exc


DEFAULT_SOURCES = [
    {
        "type": "podcast",
        "name": "CNN 5 Cosas",
        "id": "0vDgnorbpBr65YZzFVVouE",
        "window_hours": 24,
        "days": None,
        "active": True
    },
    {
        "type": "podcast",
        "name": "GMT",
        "id": "7t4spPIBRdzusl49RnUnhv",
        "window_hours": 24,
        "days": None,
        "active": True
    },
    {
        "type": "podcast",
        "name": "AM",
        "id": "2pXBpdfJoAo2iNz5G25nCP",
        "window_hours": 24,
        "days": None,
        "active": True
    },
    {
        "type": "podcast",
        "name": "Hora 25",
        "id": "3nOgEwq18rTrNnF3eaC9Mn",
        "window_hours": 24,
        "days": None,
        "active": True
    },
    {
        "type": "podcast",
        "name": "Noticias RTVE",
        "id": "0UgidTKsoaHiHDARuPQNW1",
        "window_hours": 24,
        "days": [2, 4, 5, 6],
        "active": True
    },
    {
        "type": "podcast",
        "name": "ITNIG",
        "id": "75ao7vbM0cH7SKIsyYN3iZ",
        "window_hours": 168,
        "days": [0, 1, 2, 5, 6],
        "active": True
    },
    {
        "type": "podcast",
        "name": "No es el fin del mundo",
        "id": "5dbvpKwtqz3X3hcX1BSEzf",
        "window_hours": 168,
        "days": [1, 2, 4],
        "active": True
    },
    {
        "type": "podcast",
        "name": "Mark Vidal",
        "id": "3w18J0O2X2VllIJ8fJWZAU",
        "window_hours": 168,
        "days": [1, 3],
        "active": True
    },
    {
        "type": "podcast",
        "name": "Quieto todo el mundo",
        "id": "7Iqj5ZMZLoUd4HRoCTGiG0",
        "window_hours": 720,
        "days": [1, 2, 3],
        "active": True
    },
    {
        "type": "podcast",
        "name": "CSMP",
        "id": "3Pe1GCKIsKNPaWLchXMwLL",
        "window_hours": 720,
        "days": None,
        "active": True
    },
    {
        "type": "podcast",
        "name": "La Ruina",
        "id": "2hH5wXIG5SCCSxbcbKsyg8",
        "window_hours": 720,
        "days": None,
        "active": True
    }
]

DEFAULT_QUEUE_URIS = [
    "spotify:episode:1QfdC0j9JdiO301Wpmjy1i",
    "spotify:episode:0M2obg1IVwodKX5FHhnUPl",
    "spotify:episode:7huXCIXkfRnGqR0hHQH9hk"
]


def _parse_bool_input(raw_value, default=False):
    """Parse y/n style input with fallback to default."""
    value = str(raw_value or "").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true", "si", "s"}


def _upsert_party_scene(user_dict, default_device_name):
    """Ask user for an optional party scene and upsert it into user config."""
    add_scene = input("Add or update a party scene now? [y/N]: ").strip()
    if not _parse_bool_input(add_scene, default=False):
        return

    scene_id = input("Scene id (example: fiesta_casa): ").strip()
    if not scene_id:
        print("⚠️ Scene skipped: id is required")
        return

    scene_name = input(f"Scene name [{scene_id}]: ").strip() or scene_id
    playlist_id = input("Scene playlist_id: ").strip()
    if not playlist_id:
        print("⚠️ Scene skipped: playlist_id is required")
        return

    default_label = default_device_name or "<user default>"
    scene_device_name = input(
        f"Scene device name [{default_label}] (optional): "
    ).strip()
    if not scene_device_name:
        scene_device_name = default_device_name or None

    tracks_limit_raw = input("Scene tracks limit (optional): ").strip()
    tracks_limit = None
    if tracks_limit_raw:
        try:
            parsed_limit = int(tracks_limit_raw)
            tracks_limit = parsed_limit if parsed_limit > 0 else None
        except ValueError:
            tracks_limit = None

    shuffle = _parse_bool_input(input("Shuffle scene playlist? [y/N]: ").strip(), default=False)
    active = _parse_bool_input(input("Scene active? [Y/n]: ").strip(), default=True)

    scene_payload = {
        "id": scene_id,
        "name": scene_name,
        "playlist_id": playlist_id,
        "device_name": scene_device_name,
        "active": active,
        "tracks_limit": tracks_limit,
        "shuffle": shuffle,
    }

    scenes = user_dict.get("party_scenes")
    if not isinstance(scenes, list):
        scenes = []
        user_dict["party_scenes"] = scenes

    for index, existing in enumerate(scenes):
        if isinstance(existing, dict) and str(existing.get("id") or "") == scene_id:
            scenes[index] = scene_payload
            print(f"✅ Scene '{scene_id}' updated")
            return

    scenes.append(scene_payload)
    print(f"✅ Scene '{scene_id}' added")


def main():
    # Get credentials from environment
    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("❌ Error: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set")
        sys.exit(1)

    try:
        validate_client_credentials(client_id, client_secret)
    except Exception as exc:
        print(f"❌ Error: {exc}")
        print("   Tip: verify client_id/client_secret in Spotify Dashboard and export them again.")
        sys.exit(1)

    # Get username from argument or prompt
    if len(sys.argv) < 2:
        username = input("Enter username: ").strip()
    else:
        username = sys.argv[1]

    if not username:
        print("❌ Error: username is required")
        sys.exit(1)

    # Get device_name from user
    device_name = input("Enter Spotify device name (e.g. Web Player (Chrome)): ").strip()
    if not device_name:
        print("❌ Error: device_name is required")
        sys.exit(1)

    # Get refresh_token via OAuth
    try:
        refresh_token = get_refresh_token(client_id, client_secret)
    except Exception as exc:
        print(f"❌ Error getting refresh token: {exc}")
        sys.exit(1)

    # Load config
    config_path = Path(__file__).parent / "config" / "config.ini"
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {"default_user": None, "users": []}
    except json.JSONDecodeError:
        print("❌ Error: config.ini is not valid JSON")
        sys.exit(1)

    # Find or create user
    user_dict = next((u for u in config['users'] if u['user'] == username), None)

    if user_dict:
        # Update existing user - preserve sources and playlist_id
        print(f"\n📝 Updating existing user '{username}'...")
        user_dict['spotify_client_id'] = client_id
        user_dict['spotify_client_secret'] = client_secret
        user_dict['spotify_refresh_token'] = refresh_token
        user_dict['spotify_device_name'] = device_name
        # Migrate to stable device selector by name.
        user_dict.pop('spotify_device_id', None)
        _upsert_party_scene(user_dict, device_name)
        print(f"✅ Updated credentials for '{username}'")
    else:
        # Create new user
        print(f"\n🆕 Creating new user '{username}'...")
        new_user = {
            "user": username,
            "spotify_client_id": client_id,
            "spotify_client_secret": client_secret,
            "spotify_refresh_token": refresh_token,
            "spotify_device_name": device_name,
            "spotify_queue_playlist_id": "5HdkTyc30uKBkIEGMI8ghI",
            "sources": DEFAULT_SOURCES,
            "party_scenes": [],
            "spotify_queue_uris": DEFAULT_QUEUE_URIS
        }
        new_user.pop('spotify_device_id', None)
        _upsert_party_scene(new_user, device_name)
        config['users'].append(new_user)

        # Set as default if first user
        if config['default_user'] is None:
            config['default_user'] = username
            print(f"✅ Set '{username}' as default user")
        print(f"✅ Created new user '{username}'")

    # Save config
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Config saved to {config_path}")


if __name__ == '__main__':
    main()
