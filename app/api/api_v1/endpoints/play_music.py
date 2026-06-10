"""
This file contains the endpoint to build and play the podcast queue via Spotify.
"""
# pylint: disable=E0401,R0801,E0611

from fastapi import APIRouter, HTTPException
from app.classes.adapters.config_aws import ConfigAWS, _ssm_available
from app.classes.adapters.spotify_api import SpotifyAPI

router = APIRouter()


def _mask_value(raw_value):
    """Mask sensitive values keeping only the first and last 2 chars."""
    value = str(raw_value or "")
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def _source_labels(sources):
    """Return readable source labels for diagnostics."""
    labels = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        labels.append(source.get('name') or source.get('id') or 'unknown')
    return labels


@router.post("")
def play_music(play: bool = True, scene: str | None = None):
    """
        Clears the queue playlist and refills it with new/unplayed podcast
        episodes based on the configured shows and time windows.

        When play=true (default), also starts playback on the configured
        Spotify device (requires an active Spotify session on the device).

        When play=false, only prepares the playlist so it can be played
        manually from the Spotify app at any time.

    Args:
        play (bool): Whether to start playback immediately. Defaults to True.

    Returns:
        dict: Result with is_ok, episodes_added and status_code
    """
    try:
        config_instance = ConfigAWS()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SpotifyAPI(config_instance).build_and_play_queue(play=play, scene=scene)


@router.post("/{user}")
def play_music_by_user(user: str, play: bool = True, scene: str | None = None):
    """Build and optionally play queue for the provided user profile."""
    try:
        config_instance = ConfigAWS(user=user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SpotifyAPI(config_instance).build_and_play_queue(play=play, scene=scene)


@router.get("/devices")
def list_devices():
    """List available Spotify Connect devices for default user."""
    try:
        config_instance = ConfigAWS()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SpotifyAPI(config_instance).list_available_devices()


@router.get("/devices/{user}")
def list_devices_by_user(user: str):
    """List available Spotify Connect devices for a specific user profile."""
    try:
        config_instance = ConfigAWS(user=user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SpotifyAPI(config_instance).list_available_devices()


@router.get("/debug/config")
def debug_effective_config(user: str | None = None):
    """Return the effective runtime config used by this deployment."""
    try:
        config_instance = ConfigAWS(user=user) if user else ConfigAWS()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    sources = config_instance.spotify.get('sources') or []
    return {
        'selected_user': config_instance.current_user,
        'default_user': config_instance.default_user,
        'ssm_enabled': _ssm_available(),
        'sources_count': len(sources),
        'sources': _source_labels(sources),
        'device_id_masked': _mask_value(config_instance.spotify.get('device_id', '')),
        'queue_playlist_id_masked': _mask_value(config_instance.spotify.get('queue_playlist_id', '')),
    }
