"""
Spotify API adapter for podcast queue management.
Refreshes the queue playlist with new/unplayed episodes and starts playback.
"""
# pylint: disable=E0401,R0801,R0903

from datetime import datetime, timedelta, timezone
from time import sleep
from zoneinfo import ZoneInfo
import random
import requests as _req
import urllib3
from app.classes.spotify import Spotify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"
_DATE_FORMATS = {'day': '%Y-%m-%d', 'month': '%Y-%m', 'year': '%Y'}


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

    def _refresh_token(self):
        """Exchange refresh_token for a fresh access_token."""
        resp = _req.post(_TOKEN_URL, data={
            'grant_type': 'refresh_token',
            'refresh_token': self.config.spotify['refresh_token'],
            'client_id': self.config.spotify['client_id'],
            'client_secret': self.config.spotify['client_secret'],
        }, verify=False, timeout=10)
        self._access_token = resp.json()['access_token']

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
            verify=False, timeout=10
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
            verify=False, timeout=10
        )

    def _add_to_playlist(self, playlist_id, uris):
        """Add episode URIs to the playlist. Returns True if successful."""
        resp = _req.post(
            f"{_API_BASE}/playlists/{playlist_id}/tracks",
            headers=self._headers(json_content=True),
            json={'uris': uris},
            verify=False, timeout=10
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
                verify=False, timeout=10,
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

    def _play(self, uris, device_id):
        """Transfer playback to device and start playing the given episode URIs."""
        # Transfer playback to device first (wakes it up if inactive)
        _req.put(
            f"{_API_BASE}/me/player",
            headers=self._headers(json_content=True),
            json={'device_ids': [device_id], 'play': False},
            verify=False, timeout=10
        )
        sleep(2)
        return _req.put(
            f"{_API_BASE}/me/player/play",
            headers=self._headers(json_content=True),
            params={'device_id': device_id},
            json={'uris': uris},
            verify=False, timeout=10
        )

    def build_and_play_queue(self, play=True):
        """
            Fetches new/unplayed episodes from configured podcasts
            and stores them. Optionally starts playback on the device.

        Args:
            play (bool): Whether to start playback after building the queue.
                         Requires an active Spotify session on the device.

        Returns:
            dict: Result with is_ok, status_code and episodes_added
        """
        self._refresh_token()
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

        # Persist URIs so play_stored_queue can play them later without rebuilding
        self.config.set_spotify_queue(uris)

        if not play:
            return {
                'is_ok': True,
                'episodes_added': len(uris),
                'attempted': attempted,
                'added': added,
                'response': 'Queue built and saved. Call play_music?play=true to play.',
            }

        play_resp = self._play(uris, device_id)
        return {
            'is_ok': play_resp.ok,
            'status_code': play_resp.status_code,
            'episodes_added': len(uris),
            'attempted': attempted,
            'added': added,
        }
