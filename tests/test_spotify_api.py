"""Tests for SpotifyAPI class."""
# pylint: disable=C0301,C0103

from datetime import datetime, timezone
import random
from unittest.mock import MagicMock, patch

from app.classes.adapters.spotify_api import SpotifyAPI


def _make_config(podcasts=None, sources=None, queue_uris=None):
    if sources is None:
        sources = []
        for podcast in podcasts if podcasts is not None else []:
            source = dict(podcast)
            source['type'] = 'podcast'
            source.setdefault('active', True)
            sources.append(source)

    config = MagicMock()
    config.spotify = {
        'client_id': 'cid',
        'client_secret': 'csecret',
        'refresh_token': 'rtoken',
        'device_id': 'dev1',
        'queue_playlist_id': 'pl1',
        'podcasts': podcasts if podcasts is not None else [],
        'sources': sources,
        'queue_uris': queue_uris if queue_uris is not None else [],
    }
    return config


def _make_api(podcasts=None, sources=None):
    api = SpotifyAPI(_make_config(podcasts=podcasts, sources=sources))
    api._access_token = 'fake_token'
    return api


class TestParseReleaseDate:
    def test_day_precision(self):
        result = SpotifyAPI._parse_release_date('2024-03-15', 'day')
        assert result == datetime(2024, 3, 15, tzinfo=timezone.utc)

    def test_month_precision(self):
        result = SpotifyAPI._parse_release_date('2024-03', 'month')
        assert result == datetime(2024, 3, 1, tzinfo=timezone.utc)

    def test_year_precision(self):
        result = SpotifyAPI._parse_release_date('2024', 'year')
        assert result == datetime(2024, 1, 1, tzinfo=timezone.utc)

    def test_defaults_to_day_format_on_unknown_precision(self):
        result = SpotifyAPI._parse_release_date('2024-06-01', 'unknown')
        assert result == datetime(2024, 6, 1, tzinfo=timezone.utc)


class TestBuildAndPlayQueueNoEpisodes:
    def test_returns_no_episodes_when_sources_empty(self):
        api = _make_api(sources=[])
        with patch.object(api, '_refresh_token'):
            result = api.build_and_play_queue(play=True)

        assert result['is_ok'] is False
        assert result['episodes_added'] == 0

    def test_skips_podcast_not_scheduled_today(self):
        api = _make_api(
            podcasts=[{'id': 'pod1', 'name': 'Pod', 'window_hours': 24, 'days': [99]}])
        with patch.object(api, '_refresh_token'):
            result = api.build_and_play_queue(play=True)

        assert result['is_ok'] is False
        assert result['attempted'] == []

    def test_returns_no_episodes_when_get_episode_uri_returns_none(self):
        api = _make_api(sources=[
            {'type': 'podcast', 'id': 'pod1', 'name': 'Pod', 'window_hours': 24, 'days': None, 'active': True}
        ])
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', return_value=None):
            result = api.build_and_play_queue(play=True)

        assert result['is_ok'] is False
        assert result['attempted'] == ['Pod']
        assert result['added'] == []


class TestBuildAndPlayQueueWithEpisodes:
    def test_play_false_builds_without_playing(self):
        api = _make_api(sources=[
            {'type': 'podcast', 'id': 'pod1', 'name': 'Pod', 'window_hours': 24, 'days': None, 'active': True}
        ])
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', return_value='spotify:episode:xyz'), \
                patch.object(api, '_play') as mock_play:
            result = api.build_and_play_queue(play=False)

        assert result['is_ok'] is True
        assert result['episodes_added'] == 1
        assert 'Queue built' in result['response']
        mock_play.assert_not_called()
        api.config.set_spotify_queue.assert_called_once_with(
            ['spotify:episode:xyz'])

    def test_play_true_calls_play_and_returns_status(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 204
        api = _make_api(sources=[
            {'type': 'podcast', 'id': 'pod1', 'name': 'Pod', 'window_hours': 24, 'days': None, 'active': True}
        ])
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', return_value='spotify:episode:xyz'), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['is_ok'] is True
        assert result['status_code'] == 204
        assert result['episodes_added'] == 1
        assert result['added'] == ['Pod']

    def test_multiple_podcasts_all_active_today(self):
        sources = [
            {'type': 'podcast', 'id': 'p1', 'name': 'Pod A', 'window_hours': 24, 'days': None, 'active': True},
            {'type': 'podcast', 'id': 'p2', 'name': 'Pod B', 'window_hours': 24, 'days': None, 'active': True},
        ]
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 204
        api = _make_api(sources=sources)
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', side_effect=['spotify:episode:a', 'spotify:episode:b']), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['episodes_added'] == 2
        assert result['added'] == ['Pod A', 'Pod B']

    def test_partial_episodes_when_some_return_none(self):
        sources = [
            {'type': 'podcast', 'id': 'p1', 'name': 'Pod A', 'window_hours': 24, 'days': None, 'active': True},
            {'type': 'podcast', 'id': 'p2', 'name': 'Pod B', 'window_hours': 24, 'days': None, 'active': True},
        ]
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 204
        api = _make_api(sources=sources)
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', side_effect=['spotify:episode:a', None]), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['episodes_added'] == 1
        assert result['attempted'] == ['Pod A', 'Pod B']
        assert result['added'] == ['Pod A']

    def test_skips_inactive_sources(self):
        sources = [
            {'type': 'podcast', 'id': 'p1', 'name': 'Pod A', 'window_hours': 24, 'days': None, 'active': False},
            {'type': 'podcast', 'id': 'p2', 'name': 'Pod B', 'window_hours': 24, 'days': None, 'active': True},
        ]
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 204
        api = _make_api(sources=sources)
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', return_value='spotify:episode:b'), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['attempted'] == ['Pod B']
        assert result['added'] == ['Pod B']

    def test_active_defaults_to_true_when_missing(self):
        sources = [
            {'type': 'podcast', 'id': 'p1', 'name': 'Pod A', 'window_hours': 24, 'days': None},
        ]
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 204
        api = _make_api(sources=sources)
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', return_value='spotify:episode:a'), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['episodes_added'] == 1
        assert result['added'] == ['Pod A']

    def test_playlist_sources_are_added_to_queue(self):
        sources = [
            {
                'type': 'playlist',
                'id': 'pl_1',
                'name': 'Music Mix',
                'tracks_limit': 2,
                'shuffle': False,
                'active': True,
            }
        ]
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 204
        api = _make_api(sources=sources)
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_playlist_track_uris', return_value=['spotify:track:1', 'spotify:track:2']), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['episodes_added'] == 2
        assert result['attempted'] == ['Music Mix']
        assert result['added'] == ['Music Mix']
        api.config.set_spotify_queue.assert_called_once_with(['spotify:track:1', 'spotify:track:2'])


class TestPlaylistUris:
    def test_get_playlist_track_uris_reads_paginated_results(self):
        api = _make_api(sources=[])
        first = MagicMock()
        first.json.return_value = {
            'items': [{'track': {'id': 't1'}}, {'track': {'id': 't2'}}],
            'next': 'next-url',
        }
        second = MagicMock()
        second.json.return_value = {
            'items': [{'track': {'id': 't3'}}],
            'next': None,
        }
        with patch('app.classes.adapters.spotify_api._req.get', side_effect=[first, second]):
            uris = api._get_playlist_track_uris('pl1')

        assert uris == ['spotify:track:t1', 'spotify:track:t2', 'spotify:track:t3']

    def test_get_playlist_track_uris_respects_limit(self):
        api = _make_api(sources=[])
        resp = MagicMock()
        resp.json.return_value = {
            'items': [{'track': {'id': 't1'}}, {'track': {'id': 't2'}}, {'track': {'id': 't3'}}],
            'next': None,
        }
        with patch('app.classes.adapters.spotify_api._req.get', return_value=resp):
            uris = api._get_playlist_track_uris('pl1', tracks_limit=2)

        assert uris == ['spotify:track:t1', 'spotify:track:t2']
