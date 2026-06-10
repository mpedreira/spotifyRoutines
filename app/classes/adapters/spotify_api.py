"""
Spotify API adapter for podcast queue management.
Refreshes the queue playlist with new/unplayed episodes and starts playback.
"""
# pylint: disable=E0401,R0801,R0903

from datetime import datetime, timedelta, timezone
from time import sleep
from zoneinfo import ZoneInfo
import random
import os
import requests as _req
import urllib3
from app.classes.spotify import Spotify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"
_DATE_FORMATS = {'day': '%Y-%m-%d', 'month': '%Y-%m', 'year': '%Y'}


def _parse_env_bool(env_var_name, default=True):
    """Parse an environment variable as bool with safe fallback."""
    raw = os.environ.get(env_var_name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in {'0', 'false', 'no', 'off'}:
        return False
    if value in {'1', 'true', 'yes', 'on'}:
        return True
    return default


def _parse_env_float(env_var_name, default, min_value=0.0):
    """Parse an environment variable as float with clamped minimum."""
    raw = os.environ.get(env_var_name)
    if raw is None:
        return default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(min_value, value)


class SpotifyAPI(Spotify):
    """Adapter that uses the Spotify Web API to build and play podcast queues."""

    def __init__(self, config):
        """
        Init method for SpotifyAPI.

        Args:
            config (class): Basic configuration with Spotify credentials
        """
        super().__init__(config)
        self._access_token = None
        self._http_timeout = _parse_env_float(
            'SPOTIFY_HTTP_TIMEOUT_SECONDS', default=10.0, min_value=0.0)
        self._transfer_wait = _parse_env_float(
            'SPOTIFY_TRANSFER_WAIT_SECONDS', default=3.0, min_value=0.0)
        self._device_retry_wait = _parse_env_float(
            'SPOTIFY_DEVICE_RETRY_WAIT_SECONDS', default=4.0, min_value=0.0)
        self._transient_retry_wait = _parse_env_float(
            'SPOTIFY_TRANSIENT_RETRY_WAIT_SECONDS', default=0.5, min_value=0.0)
        self._device_retry_enabled = _parse_env_bool(
            'SPOTIFY_DEVICE_RETRY_ENABLED', default=True)

    def _play_request(self, uris, device_id):
        """Issue the Spotify /me/player/play call for the given URIs."""
        return _req.put(
            f"{_API_BASE}/me/player/play",
            headers=self._headers(json_content=True),
            params={'device_id': device_id},
            json={'uris': uris},
            verify=False, timeout=self._http_timeout
        )

    def _refresh_token(self):
        """Exchange refresh_token for a fresh access_token."""
        resp = _req.post(_TOKEN_URL, data={
            'grant_type': 'refresh_token',
            'refresh_token': self.config.spotify['refresh_token'],
            'client_id': self.config.spotify['client_id'],
            'client_secret': self.config.spotify['client_secret'],
        }, verify=False, timeout=self._http_timeout)
        payload = resp.json() if resp.content else {}
        self._access_token = payload.get('access_token')
        if not self._access_token:
            error = (payload or {}).get('error_description') or (payload or {}).get('error') or 'Unable to refresh Spotify token'
            raise ValueError(error)

    @staticmethod
    def _response_detail(resp):
        """Return a readable error detail from a Spotify API response."""
        try:
            payload = resp.json()
        except ValueError:
            payload = {}

        if isinstance(payload, dict):
            spotify_error = payload.get('error')
            if isinstance(spotify_error, dict):
                return spotify_error.get('message') or str(spotify_error)
            if spotify_error:
                return str(spotify_error)

        return (resp.text or '').strip() or f"HTTP {resp.status_code}"

    def _sync_queue_playlist(self, playlist_id, uris):
        """Best-effort sync of generated queue into a Spotify playlist."""
        self._clear_playlist(playlist_id)
        return self._add_to_playlist(playlist_id, uris)

    def _headers(self, json_content=False):
        """Return auth headers, optionally with Content-Type: application/json."""
        headers = {'Authorization': f'Bearer {self._access_token}'}
        if json_content:
            headers['Content-Type'] = 'application/json'
        return headers

    @staticmethod
    def _parse_release_date(date_str, precision):
        """Parse a Spotify release_date string into a UTC-aware datetime."""
        fmt = _DATE_FORMATS.get(precision, '%Y-%m-%d')
        return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)

    def _get_episode_uri(self, show_id, window_hours):
        """
            Returns the URI of the first unplayed episode within the time window.

        Args:
            show_id (str): Spotify show ID
            window_hours (int|None): Only consider episodes released within this
                                     many hours. None means no time restriction.

        Returns:
            str|None: Spotify episode URI or None if no match found
        """
        resp = _req.get(
            f"{_API_BASE}/shows/{show_id}/episodes",
            headers=self._headers(),
            params={'market': 'ES', 'limit': 10},
            verify=False, timeout=self._http_timeout
        )
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=window_hours)
            if window_hours is not None else None
        )
        for episode in resp.json().get('items', []):
            if episode is None:
                continue
            if episode.get('resume_point', {}).get('fully_played'):
                continue
            if cutoff:
                precision = episode.get('release_date_precision', 'day')
                release = self._parse_release_date(
                    episode['release_date'], precision)
                if release < cutoff:
                    continue
            return f"spotify:episode:{episode['id']}"
        return None

    def _clear_playlist(self, playlist_id):
        """Replace all playlist tracks with an empty list."""
        _req.put(
            f"{_API_BASE}/playlists/{playlist_id}/tracks",
            headers=self._headers(json_content=True),
            json={'uris': []},
            verify=False, timeout=self._http_timeout
        )

    def _add_to_playlist(self, playlist_id, uris):
        """Add episode URIs to the playlist. Returns True if successful."""
        resp = _req.post(
            f"{_API_BASE}/playlists/{playlist_id}/tracks",
            headers=self._headers(json_content=True),
            json={'uris': uris},
            verify=False, timeout=self._http_timeout
        )
        return resp.ok

    def _get_playlist_track_uris(self, playlist_id, tracks_limit=None):
        """Return a list of track URIs from a Spotify playlist."""
        uris = []
        offset = 0
        limit = 50
        max_items = tracks_limit if isinstance(tracks_limit, int) and tracks_limit > 0 else None

        while True:
            page_limit = limit
            if max_items is not None:
                remaining = max_items - len(uris)
                if remaining <= 0:
                    break
                page_limit = min(limit, remaining)

            resp = _req.get(
                f"{_API_BASE}/playlists/{playlist_id}/tracks",
                headers=self._headers(),
                params={'market': 'ES', 'limit': page_limit, 'offset': offset},
                verify=False, timeout=self._http_timeout,
            )
            items = resp.json().get('items', [])
            if not items:
                break

            for item in items:
                track = (item or {}).get('track') or {}
                track_id = track.get('id')
                if track_id:
                    uris.append(f"spotify:track:{track_id}")
                if max_items is not None and len(uris) >= max_items:
                    break

            if max_items is not None and len(uris) >= max_items:
                break

            if not resp.json().get('next'):
                break
            offset += len(items)

        return uris

    def _find_party_scene(self, scene_id):
        """Return normalized party scene config by id, or None when not found."""
        target = str(scene_id or '').strip().lower()
        if not target:
            return None
        for scene in self.config.spotify.get('party_scenes', []):
            if not isinstance(scene, dict):
                continue
            if str(scene.get('id', '')).strip().lower() == target:
                return scene
        return None

    def list_available_devices(self):
        """List available Spotify Connect devices for current account."""
        try:
            self._refresh_token()
        except (ValueError, _req.RequestException) as exc:
            return {
                'is_ok': False,
                'status_code': 401,
                'devices': [],
                'response': f'Token refresh failed: {exc}',
            }

        try:
            resp = _req.get(
                f"{_API_BASE}/me/player/devices",
                headers=self._headers(),
                verify=False,
                timeout=self._http_timeout,
            )
        except _req.RequestException as exc:
            return {
                'is_ok': False,
                'status_code': 503,
                'devices': [],
                'response': f'Device query failed: {exc}',
            }

        payload = resp.json() if resp.content else {}
        devices = payload.get('devices', []) if isinstance(payload, dict) else []
        return {
            'is_ok': resp.ok,
            'status_code': resp.status_code,
            'devices': devices,
            'selected_device_id': self.config.spotify.get('device_id', ''),
            'response': 'Devices loaded' if resp.ok else f'Device query failed: {self._response_detail(resp)}',
        }

    def _play(self, uris, device_id, _retry=True):
        """Transfer playback to device and start playing the given episode URIs.

        Combines the transfer and play into a single call (play:true on transfer).
        If Spotify still reports device-not-found, retries once after a short wait.
        """
        # Ask Spotify to transfer AND start playing in one shot
        transfer_resp = _req.put(
            f"{_API_BASE}/me/player",
            headers=self._headers(json_content=True),
            json={'device_ids': [device_id], 'play': True},
            verify=False, timeout=self._http_timeout
        )
        # After transfer, issue explicit play with the desired URIs
        if self._transfer_wait > 0:
            sleep(self._transfer_wait)
        play_resp = self._play_request(uris, device_id)

        # Retry once for device-not-found or transient Spotify/API gateway failures.
        if self._device_retry_enabled and not play_resp.ok and _retry:
            detail = self._response_detail(play_resp).lower()
            status_code = play_resp.status_code
            should_retry = (
                (status_code == 404 and 'device' in detail)
                or status_code in {429, 500, 502, 503, 504}
            )
            if should_retry:
                is_device_retry = status_code == 404 and 'device' in detail
                retry_wait = self._device_retry_wait if is_device_retry else self._transient_retry_wait
                if retry_wait > 0:
                    sleep(retry_wait)
                if is_device_retry:
                    return self._play(uris, device_id, _retry=False)
                return self._play_request(uris, device_id)

        return play_resp

    def build_and_play_queue(self, play=True, scene=None):
        """
            Fetches new/unplayed episodes from configured podcasts
            and stores them. Optionally starts playback on the device.

        Args:
            play (bool): Whether to start playback after building the queue.
                         Requires an active Spotify session on the device.

        Returns:
            dict: Result with is_ok, status_code and episodes_added
        """
        try:
            self._refresh_token()
        except (ValueError, _req.RequestException) as exc:
            return {
                'is_ok': False,
                'episodes_added': 0,
                'response': f'Token refresh failed: {exc}',
            }

        sources = self.config.spotify.get('sources')
        if sources is None:
            sources = []
            for podcast in self.config.spotify.get('podcasts', []):
                source = dict(podcast)
                source['type'] = 'podcast'
                source.setdefault('active', True)
                sources.append(source)
        device_id = self.config.spotify['device_id']

        today = datetime.now(ZoneInfo('Europe/Madrid')
                             ).weekday()  # 0=Mon … 6=Sun

        uris = []
        attempted = []
        added = []

        if scene:
            party_scene = self._find_party_scene(scene)
            if not party_scene:
                return {
                    'is_ok': False,
                    'status_code': 404,
                    'episodes_added': 0,
                    'response': f"Scene '{scene}' not found",
                }
            if not party_scene.get('active', True):
                return {
                    'is_ok': False,
                    'status_code': 400,
                    'episodes_added': 0,
                    'response': f"Scene '{scene}' is inactive",
                }

            label = party_scene.get('name') or party_scene['id']
            attempted.append(label)
            if party_scene.get('device_id'):
                device_id = party_scene['device_id']
            playlist_uris = self._get_playlist_track_uris(
                party_scene['playlist_id'],
                tracks_limit=party_scene.get('tracks_limit'),
            )
            if party_scene.get('shuffle', False):
                random.shuffle(playlist_uris)
            if playlist_uris:
                uris.extend(playlist_uris)
                added.append(label)
        else:
            for source in sources:
                if not source.get('active', True):
                    continue

                source_type = str(source.get('type', 'podcast')).lower()
                source_id = source.get('id')
                if not source_id:
                    continue

                days = source.get('days')
                if days is not None and today not in days:
                    continue

                label = source.get('name') or source_id
                attempted.append(label)

                if source_type == 'playlist':
                    playlist_uris = self._get_playlist_track_uris(
                        source_id,
                        tracks_limit=source.get('tracks_limit'),
                    )
                    if source.get('shuffle', False):
                        random.shuffle(playlist_uris)
                    if playlist_uris:
                        uris.extend(playlist_uris)
                        added.append(label)
                    continue

                uri = self._get_episode_uri(source_id, source.get('window_hours'))
                if uri:
                    uris.append(uri)
                    added.append(label)

        if not uris:
            return {
                'is_ok': False,
                'episodes_added': 0,
                'attempted': attempted,
                'added': added,
                'response': 'No new unplayed episodes found',
            }

        # Persist URIs in config so the last generated queue is always available.
        self.config.set_spotify_queue(uris)
        queue_playlist_id = self.config.spotify.get('queue_playlist_id')

        if not play:
            return {
                'is_ok': True,
                'episodes_added': len(uris),
                'attempted': attempted,
                'added': added,
                'response': 'Queue built and saved. Call play_music?play=true to play.',
            }

        try:
            play_resp = self._play(uris, device_id)
        except _req.RequestException as exc:
            play_resp = None
            play_detail = str(exc)
        else:
            play_detail = self._response_detail(play_resp) if not play_resp.ok else ''

        # Detect device-offline scenarios: fall back to offline mode (queue ready, no play).
        device_offline = (
            play_resp is None
            or play_resp.status_code in (404, 403)
            and 'device' in play_detail.lower()
        )

        queue_synced = None
        if (play_resp is None or not play_resp.ok) and queue_playlist_id:
            try:
                queue_synced = self._sync_queue_playlist(queue_playlist_id, uris)
            except _req.RequestException:
                queue_synced = False

        if device_offline:
            return {
                'is_ok': True,
                'episodes_added': len(uris),
                'attempted': attempted,
                'added': added,
                'response': (
                    'Device offline: queue built and saved. '
                    'Open Spotify on the device and call play_music?play=true to play.'
                ),
                'queue_playlist_synced': queue_synced,
                'device_offline': True,
            }

        if play_resp is None:
            return {
                'is_ok': False,
                'status_code': 503,
                'episodes_added': len(uris),
                'attempted': attempted,
                'added': added,
                'response': f'Playback request failed: {play_detail}',
                'queue_playlist_synced': queue_synced,
            }

        return {
            'is_ok': play_resp.ok,
            'status_code': play_resp.status_code,
            'episodes_added': len(uris),
            'attempted': attempted,
            'added': added,
            'response': 'Playback started' if play_resp.ok else f'Playback failed: {play_detail}',
            'queue_playlist_synced': queue_synced,
        }
