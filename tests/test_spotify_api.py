"""Tests for SpotifyAPI class."""
# pylint: disable=C0301,C0103

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.classes.adapters.spotify_api import SpotifyAPI


def _make_config(podcasts=None, queue_uris=None):
    config = MagicMock()
    config.spotify = {
        'client_id': 'cid',
        'client_secret': 'csecret',
        'refresh_token': 'rtoken',
        'device_id': 'dev1',
        'queue_playlist_id': 'pl1',
        'podcasts': podcasts if podcasts is not None else [],
        'queue_uris': queue_uris if queue_uris is not None else [],
    }
    return config


def _make_api(podcasts=None):
    api = SpotifyAPI(_make_config(podcasts=podcasts))
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
    def test_returns_no_episodes_when_podcasts_empty(self):
        api = _make_api(podcasts=[])
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
        api = _make_api(
            podcasts=[{'id': 'pod1', 'name': 'Pod', 'window_hours': 24, 'days': None}])
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', return_value=None):
            result = api.build_and_play_queue(play=True)

        assert result['is_ok'] is False
        assert result['attempted'] == ['Pod']
        assert result['added'] == []


class TestBuildAndPlayQueueWithEpisodes:
    def test_play_false_builds_without_playing(self):
        api = _make_api(
            podcasts=[{'id': 'pod1', 'name': 'Pod', 'window_hours': 24, 'days': None}])
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
        api = _make_api(
            podcasts=[{'id': 'pod1', 'name': 'Pod', 'window_hours': 24, 'days': None}])
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', return_value='spotify:episode:xyz'), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['is_ok'] is True
        assert result['status_code'] == 204
        assert result['episodes_added'] == 1
        assert result['added'] == ['Pod']

    def test_multiple_podcasts_all_active_today(self):
        podcasts = [
            {'id': 'p1', 'name': 'Pod A', 'window_hours': 24, 'days': None},
            {'id': 'p2', 'name': 'Pod B', 'window_hours': 24, 'days': None},
        ]
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 204
        api = _make_api(podcasts=podcasts)
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', side_effect=['spotify:episode:a', 'spotify:episode:b']), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['episodes_added'] == 2
        assert result['added'] == ['Pod A', 'Pod B']

    def test_partial_episodes_when_some_return_none(self):
        podcasts = [
            {'id': 'p1', 'name': 'Pod A', 'window_hours': 24, 'days': None},
            {'id': 'p2', 'name': 'Pod B', 'window_hours': 24, 'days': None},
        ]
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 204
        api = _make_api(podcasts=podcasts)
        with patch.object(api, '_refresh_token'), \
                patch.object(api, '_get_episode_uri', side_effect=['spotify:episode:a', None]), \
                patch.object(api, '_play', return_value=mock_resp):
            result = api.build_and_play_queue(play=True)

        assert result['episodes_added'] == 1
        assert result['attempted'] == ['Pod A', 'Pod B']
        assert result['added'] == ['Pod A']
