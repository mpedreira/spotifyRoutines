"""Tests for play_music endpoints."""
# pylint: disable=C0103

from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.api_v1.endpoints.play_music import (
    play_music,
    play_music_by_user,
    debug_effective_config,
    list_devices,
    list_devices_by_user,
)



class TestPlayMusicEndpoint:
    def test_default_endpoint_uses_default_user_config(self):
        response_payload = {'is_ok': True, 'episodes_added': 1}
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS') as config_cls, \
                patch('app.api.api_v1.endpoints.play_music.SpotifyAPI') as spotify_cls:
            config_instance = MagicMock()
            config_cls.return_value = config_instance
            spotify_cls.return_value.build_and_play_queue.return_value = response_payload

            response = play_music(play=False)

        assert response == response_payload
        config_cls.assert_called_once_with()
        spotify_cls.return_value.build_and_play_queue.assert_called_once_with(play=False, scene=None)

    def test_default_endpoint_passes_scene_when_provided(self):
        response_payload = {'is_ok': True, 'episodes_added': 4}
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS') as config_cls, \
                patch('app.api.api_v1.endpoints.play_music.SpotifyAPI') as spotify_cls:
            config_instance = MagicMock()
            config_cls.return_value = config_instance
            spotify_cls.return_value.build_and_play_queue.return_value = response_payload

            response = play_music(play=True, scene='fiesta_casa')

        assert response == response_payload
        spotify_cls.return_value.build_and_play_queue.assert_called_once_with(play=True, scene='fiesta_casa')

    def test_user_endpoint_passes_user_to_config(self):
        response_payload = {'is_ok': True, 'episodes_added': 2}
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS') as config_cls, \
                patch('app.api.api_v1.endpoints.play_music.SpotifyAPI') as spotify_cls:
            config_instance = MagicMock()
            config_cls.return_value = config_instance
            spotify_cls.return_value.build_and_play_queue.return_value = response_payload

            response = play_music_by_user(user='Juanito', play=True)

        assert response == response_payload
        config_cls.assert_called_once_with(user='Juanito')
        spotify_cls.return_value.build_and_play_queue.assert_called_once_with(play=True, scene=None)

    def test_user_endpoint_passes_scene_to_service(self):
        response_payload = {'is_ok': True, 'episodes_added': 2}
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS') as config_cls, \
                patch('app.api.api_v1.endpoints.play_music.SpotifyAPI') as spotify_cls:
            config_instance = MagicMock()
            config_cls.return_value = config_instance
            spotify_cls.return_value.build_and_play_queue.return_value = response_payload

            response = play_music_by_user(user='Mireia', play=True, scene='fiesta_casa')

        assert response == response_payload
        spotify_cls.return_value.build_and_play_queue.assert_called_once_with(play=True, scene='fiesta_casa')

    def test_user_endpoint_returns_404_when_user_not_found(self):
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS', side_effect=ValueError("User 'Missing' not found in config")):
            try:
                play_music_by_user(user='Missing', play=True)
                assert False, 'Expected HTTPException'
            except HTTPException as exc:
                assert exc.status_code == 404
                assert 'Missing' in exc.detail

    def test_debug_effective_config_returns_runtime_summary(self):
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS') as config_cls, \
                patch('app.api.api_v1.endpoints.play_music._ssm_available', return_value=False):
            config_instance = MagicMock()
            config_instance.current_user = 'Manuel'
            config_instance.default_user = 'Manuel'
            config_instance.spotify = {
                'sources': [
                    {'name': 'AM', 'id': 'am_id'},
                    {'id': 'rtve_id'},
                ],
                'device_id': 'device_1111',
                'queue_playlist_id': 'playlist_2222',
            }
            config_cls.return_value = config_instance

            response = debug_effective_config()

        assert response['selected_user'] == 'Manuel'
        assert response['default_user'] == 'Manuel'
        assert response['ssm_enabled'] is False
        assert response['sources_count'] == 2
        assert response['sources'] == ['AM', 'rtve_id']
        assert response['device_id_masked'].startswith('de')
        assert response['queue_playlist_id_masked'].startswith('pl')

    def test_debug_effective_config_with_user_passes_user_to_config(self):
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS') as config_cls, \
                patch('app.api.api_v1.endpoints.play_music._ssm_available', return_value=True):
            config_instance = MagicMock()
            config_instance.current_user = 'Juanito'
            config_instance.default_user = 'Manuel'
            config_instance.spotify = {
                'sources': [],
                'device_id': 'dev',
                'queue_playlist_id': 'pl',
            }
            config_cls.return_value = config_instance

            response = debug_effective_config(user='Juanito')

        config_cls.assert_called_once_with(user='Juanito')
        assert response['selected_user'] == 'Juanito'
        assert response['ssm_enabled'] is True

    def test_list_devices_uses_default_user(self):
        payload = {'is_ok': True, 'devices': []}
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS') as config_cls, \
                patch('app.api.api_v1.endpoints.play_music.SpotifyAPI') as spotify_cls:
            config_instance = MagicMock()
            config_cls.return_value = config_instance
            spotify_cls.return_value.list_available_devices.return_value = payload

            response = list_devices()

        assert response == payload
        config_cls.assert_called_once_with()
        spotify_cls.return_value.list_available_devices.assert_called_once_with()

    def test_list_devices_by_user_uses_selected_user(self):
        payload = {'is_ok': True, 'devices': [{'id': 'dev1'}]}
        with patch('app.api.api_v1.endpoints.play_music.ConfigAWS') as config_cls, \
                patch('app.api.api_v1.endpoints.play_music.SpotifyAPI') as spotify_cls:
            config_instance = MagicMock()
            config_cls.return_value = config_instance
            spotify_cls.return_value.list_available_devices.return_value = payload

            response = list_devices_by_user('Mireia')

        assert response == payload
        config_cls.assert_called_once_with(user='Mireia')
        spotify_cls.return_value.list_available_devices.assert_called_once_with()

