"""Tests for ConfigAWS class."""
# pylint: disable=C0301,C0103

import json
from unittest.mock import MagicMock, patch

import app.classes.adapters.config_aws as config_module
from app.classes.adapters.config_aws import ConfigAWS

_MULTIUSER_CONFIG = {
    "default_user": "Manuel",
    "users": [
        {
            "user": "Manuel",
            "spotify_client_id": "client_id_123",
            "spotify_client_secret": "secret_abc",
            "spotify_refresh_token": "refresh_xyz",
            "spotify_device_id": "device_111",
            "spotify_queue_playlist_id": "playlist_222",
            "sources": [
                {
                    "type": "podcast",
                    "name": "Test Pod",
                    "id": "pod_1",
                    "window_hours": 24,
                    "days": None,
                    "active": True,
                }
            ],
            "spotify_queue_uris": ["spotify:episode:aaa", "spotify:episode:bbb"],
        },
        {
            "user": "Juanito",
            "spotify_client_id": "client_id_j",
            "spotify_client_secret": "secret_j",
            "spotify_refresh_token": "refresh_j",
            "spotify_device_id": "device_j",
            "spotify_queue_playlist_id": "playlist_j",
            "sources": [],
            "spotify_queue_uris": [],
        },
    ],
}

_LEGACY_CONFIG = {
    "spotify_client_id": "legacy_client",
    "spotify_client_secret": "legacy_secret",
    "spotify_refresh_token": "legacy_refresh",
    "spotify_device_id": "legacy_device",
    "spotify_queue_playlist_id": "legacy_queue",
    "spotify_podcasts": [{"name": "Legacy Pod", "id": "legacy_1", "window_hours": 24, "days": None}],
    "spotify_queue_uris": ["spotify:episode:legacy"],
}


def _write_config(tmp_path, data=None):
    cfg = tmp_path / "config.ini"
    cfg.write_text(json.dumps(
        data if data is not None else _MULTIUSER_CONFIG), encoding="utf-8")
    return str(cfg)


class TestConfigAWSInit:
    def test_builds_spotify_dict_from_default_user(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()

        assert config.current_user == 'Manuel'
        assert config.spotify['client_id'] == 'client_id_123'
        assert config.spotify['client_secret'] == 'secret_abc'
        assert config.spotify['refresh_token'] == 'refresh_xyz'
        assert config.spotify['device_id'] == 'device_111'
        assert config.spotify['queue_playlist_id'] == 'playlist_222'
        assert config.spotify['podcasts'][0]['name'] == 'Test Pod'
        assert config.spotify['queue_uris'] == ['spotify:episode:aaa', 'spotify:episode:bbb']

    def test_loads_explicit_user(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS(user='Juanito')

        assert config.current_user == 'Juanito'
        assert config.spotify['client_id'] == 'client_id_j'
        assert config.spotify['podcasts'] == []

    def test_raises_when_user_not_found(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            try:
                ConfigAWS(user='Missing')
                assert False, "Expected ValueError"
            except ValueError as exc:
                assert "Missing" in str(exc)

    def test_uses_legacy_shape_when_old_config_is_provided(self, tmp_path):
        cfg_path = _write_config(tmp_path, data=_LEGACY_CONFIG)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()

        assert config.current_user == 'default'
        assert config.spotify['client_id'] == 'legacy_client'
        assert config.spotify['podcasts'][0]['id'] == 'legacy_1'

    def test_sources_json_string_is_parsed(self, tmp_path):
        data = dict(_MULTIUSER_CONFIG)
        data['users'] = [dict(_MULTIUSER_CONFIG['users'][0])]
        data['users'][0]['sources'] = json.dumps(_MULTIUSER_CONFIG['users'][0]['sources'])
        cfg_path = _write_config(tmp_path, data=data)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()

        assert isinstance(config.spotify['podcasts'], list)
        assert config.spotify['podcasts'][0]['name'] == 'Test Pod'


class TestSetSpotifyQueue:
    def test_updates_in_memory_and_persists_for_selected_user(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        uris = ['spotify:episode:new1', 'spotify:episode:new2']
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS(user='Juanito')
            config.set_spotify_queue(uris)

        assert config.spotify['queue_uris'] == uris
        persisted = json.loads(
            (tmp_path / "config.ini").read_text(encoding="utf-8"))
        juanito = [user for user in persisted['users'] if user['user'] == 'Juanito'][0]
        assert juanito['spotify_queue_uris'] == uris

    def test_legacy_mode_still_persists_root_queue_uris(self, tmp_path):
        cfg_path = _write_config(tmp_path, data=_LEGACY_CONFIG)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()
            config.set_spotify_queue([])

        persisted = json.loads((tmp_path / "config.ini").read_text(encoding="utf-8"))
        assert persisted['spotify_queue_uris'] == []


class TestGetParameterSSM:
    def test_falls_back_to_local_on_ssm_exception(self, tmp_path):
        cfg_path = _write_config(tmp_path, data=_MULTIUSER_CONFIG)
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.side_effect = Exception("SSM unreachable")
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=True), \
                patch.object(config_module, '_get_ssm_client', return_value=mock_ssm):
            config = ConfigAWS()

        assert config.spotify['client_id'] == 'client_id_123'

    def test_reads_root_users_config_from_ssm_json(self, tmp_path):
        cfg_path = _write_config(tmp_path, data={})
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': json.dumps(_MULTIUSER_CONFIG)}}
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=True), \
                patch.object(config_module, '_get_ssm_client', return_value=mock_ssm):
            config = ConfigAWS()

        assert config.current_user == 'Manuel'
        assert config.spotify['client_id'] == 'client_id_123'


class TestSetParameterSSM:
    def test_writes_root_users_config_to_ssm_when_in_lambda(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': json.dumps(_MULTIUSER_CONFIG)}}
        uris = ['spotify:episode:new']
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=True), \
                patch.object(config_module, '_get_ssm_client', return_value=mock_ssm):
            config = ConfigAWS(user='Manuel')
            config.set_spotify_queue(uris)

        assert mock_ssm.put_parameter.call_count >= 1
        call_kwargs = mock_ssm.put_parameter.call_args_list[-1][1]
        assert call_kwargs['Name'] == 'spotify_users_config'
        persisted = json.loads(call_kwargs['Value'])
        assert persisted['default_user'] == 'Manuel'

    def test_falls_back_to_file_on_ssm_put_failure(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': json.dumps(_MULTIUSER_CONFIG)}}
        mock_ssm.put_parameter.side_effect = Exception("SSM write error")
        uris = ['spotify:episode:fallback']
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=True), \
                patch.object(config_module, '_get_ssm_client', return_value=mock_ssm):
            config = ConfigAWS()
            config.set_spotify_queue(uris)

        assert config.spotify['queue_uris'] == uris
        persisted = json.loads(
            (tmp_path / "config.ini").read_text(encoding="utf-8"))
        manuel = [user for user in persisted['users'] if user['user'] == 'Manuel'][0]
        assert manuel['spotify_queue_uris'] == uris
