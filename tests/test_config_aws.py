"""Tests for ConfigAWS class."""
# pylint: disable=C0301,C0103

import json
from unittest.mock import MagicMock, patch

import app.classes.adapters.config_aws as config_module
from app.classes.adapters.config_aws import ConfigAWS

_SAMPLE_CONFIG = {
    "spotify_client_id": "client_id_123",
    "spotify_client_secret": "secret_abc",
    "spotify_refresh_token": "refresh_xyz",
    "spotify_device_id": "device_111",
    "spotify_queue_playlist_id": "playlist_222",
    "spotify_podcasts": [{"name": "Test Pod", "id": "pod_1", "window_hours": 24, "days": None}],
    "spotify_queue_uris": ["spotify:episode:aaa", "spotify:episode:bbb"],
}


def _write_config(tmp_path, data=None):
    cfg = tmp_path / "config.ini"
    cfg.write_text(json.dumps(
        data if data is not None else _SAMPLE_CONFIG), encoding="utf-8")
    return str(cfg)


class TestConfigAWSInit:
    def test_builds_spotify_dict_from_local_config(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()

        assert config.spotify['client_id'] == 'client_id_123'
        assert config.spotify['client_secret'] == 'secret_abc'
        assert config.spotify['refresh_token'] == 'refresh_xyz'
        assert config.spotify['device_id'] == 'device_111'
        assert config.spotify['queue_playlist_id'] == 'playlist_222'
        assert config.spotify['podcasts'] == _SAMPLE_CONFIG['spotify_podcasts']
        assert config.spotify['queue_uris'] == _SAMPLE_CONFIG['spotify_queue_uris']

    def test_uses_defaults_when_keys_missing(self, tmp_path):
        cfg_path = _write_config(tmp_path, data={})
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()

        assert config.spotify['client_id'] == ''
        assert config.spotify['client_secret'] == ''
        assert config.spotify['queue_uris'] == []
        assert config.spotify['podcasts'] == []

    def test_podcasts_as_json_string_is_parsed(self, tmp_path):
        data = {**_SAMPLE_CONFIG,
                'spotify_podcasts': json.dumps(_SAMPLE_CONFIG['spotify_podcasts'])}
        cfg_path = _write_config(tmp_path, data=data)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()

        assert isinstance(config.spotify['podcasts'], list)
        assert config.spotify['podcasts'][0]['name'] == 'Test Pod'


class TestSetSpotifyQueue:
    def test_updates_in_memory_and_persists(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        uris = ['spotify:episode:new1', 'spotify:episode:new2']
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()
            config.set_spotify_queue(uris)

        assert config.spotify['queue_uris'] == uris
        persisted = json.loads(
            (tmp_path / "config.ini").read_text(encoding="utf-8"))
        assert persisted['spotify_queue_uris'] == uris

    def test_empty_list_clears_queue(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=False):
            config = ConfigAWS()
            config.set_spotify_queue([])

        assert config.spotify['queue_uris'] == []


class TestGetParameterSSM:
    def test_falls_back_to_local_on_ssm_exception(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.side_effect = Exception("SSM unreachable")
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=True), \
                patch.object(config_module, '_get_ssm_client', return_value=mock_ssm):
            config = ConfigAWS()

        assert config.spotify['client_id'] == 'client_id_123'

    def test_reads_string_value_from_ssm(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': 'ssm_client_id'}}
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=True), \
                patch.object(config_module, '_get_ssm_client', return_value=mock_ssm):
            config = ConfigAWS()

        assert config.spotify['client_id'] == 'ssm_client_id'

    def test_reads_json_list_from_ssm(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        uris = ['spotify:episode:x', 'spotify:episode:y']
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': json.dumps(uris)}}
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=True), \
                patch.object(config_module, '_get_ssm_client', return_value=mock_ssm):
            config = ConfigAWS()

        assert config.spotify['queue_uris'] == uris


class TestSetParameterSSM:
    def test_writes_to_ssm_when_in_lambda(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': '[]'}}
        uris = ['spotify:episode:new']
        with patch.object(config_module, 'CONFIGFILE', cfg_path), \
                patch.object(config_module, '_ssm_available', return_value=True), \
                patch.object(config_module, '_get_ssm_client', return_value=mock_ssm):
            config = ConfigAWS()
            config.set_spotify_queue(uris)

        mock_ssm.put_parameter.assert_called_once()
        call_kwargs = mock_ssm.put_parameter.call_args[1]
        assert call_kwargs['Name'] == 'spotify_queue_uris'
        assert call_kwargs['Overwrite'] is True
        assert json.loads(call_kwargs['Value']) == uris

    def test_falls_back_to_file_on_ssm_put_failure(self, tmp_path):
        cfg_path = _write_config(tmp_path)
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': '[]'}}
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
        assert persisted['spotify_queue_uris'] == uris
