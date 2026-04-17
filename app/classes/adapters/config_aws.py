#!/usr/bin/env python3
# pylint: disable=C0301
# -*- coding: utf-8 -*-
"""Module for configuration of the application"""

import os
import shutil
import json
import logging
from app.classes.config import Config

logger = logging.getLogger(__name__)

# Bundled read-only copy (inside the zip in Lambda, or repo root locally)
_BASE_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_BUNDLED_CONFIG = os.path.join(_BASE_DIR, "config", "config.ini")

# Runtime writable copy: /tmp in Lambda (writable), same file locally
_TMP_CONFIG = "/tmp/config.ini" if os.path.exists(
    "/var/task") else _BUNDLED_CONFIG
CONFIGFILE = _TMP_CONFIG

# Parameters that can be read/written via SSM Parameter Store.
# List-type values are stored as JSON strings in SSM.
_SSM_PARAMETERS = {
    'spotify_client_id',
    'spotify_client_secret',
    'spotify_refresh_token',
    'spotify_device_id',
    'spotify_queue_playlist_id',
    'spotify_podcasts',
    'spotify_queue_uris',
    'spotify_users_config',
}


def _get_ssm_client():
    """Return a boto3 SSM client, or None if boto3 is not available."""
    try:
        import boto3  # pylint: disable=import-outside-toplevel
        return boto3.client('ssm', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    except Exception:  # pylint: disable=broad-except
        return None


def _ssm_available():
    """Return True when running inside Lambda (SSM should be reachable)."""
    return os.path.exists("/var/task")


def _strip_comments(text):
    """Strip # comments from JSON-like text, respecting quoted strings."""
    lines = []
    for line in text.splitlines():
        cleaned = []
        in_string = False
        i = 0
        while i < len(line):
            c = line[i]
            if c == '\\' and in_string:
                cleaned.append(c)
                if i + 1 < len(line):
                    i += 1
                    cleaned.append(line[i])
            elif c == '"':
                in_string = not in_string
                cleaned.append(c)
            elif c == '#' and not in_string:
                break  # rest of line is a comment
            else:
                cleaned.append(c)
            i += 1
        lines.append(''.join(cleaned))
    return '\n'.join(lines)


def _load_json(file_path):
    """Load JSON from a file that may contain # comments."""
    with open(file_path, "r", encoding="utf-8") as file:
        raw = file.read()
    return json.loads(_strip_comments(raw))


def _ensure_config():
    """Copy the bundled config to /tmp on first Lambda invocation."""
    if CONFIGFILE == _BUNDLED_CONFIG:
        return  # local dev: CONFIGFILE is the source, nothing to copy
    if not os.path.exists(CONFIGFILE):
        if os.path.exists(_BUNDLED_CONFIG):
            shutil.copy2(_BUNDLED_CONFIG, CONFIGFILE)
        else:
            # config/config.ini not bundled in the zip (e.g. gitignored) – start fresh
            with open(CONFIGFILE, "w", encoding="utf-8") as _f:
                json.dump({}, _f)


class ConfigAWS (Config):  # pylint: disable=too-many-instance-attributes
    """Module for configuration of the application"""

    def __init__(self, user=None):
        """Init method for ConfigAWS."""
        raw_config = self._load_root_config()
        normalized, self._legacy_mode = self._normalize_root_config(raw_config)

        self.default_user = normalized['default_user']
        self.users = normalized['users']
        self._users_by_name = {item['user']: item for item in self.users}

        selected_user = user or self.default_user
        if selected_user not in self._users_by_name:
            raise ValueError(f"User '{selected_user}' not found in config")

        self.current_user = selected_user
        self.spotify = self._build_spotify_dict(self._users_by_name[selected_user])

    @staticmethod
    def _parse_json_string(value, default):
        """Return parsed JSON when value is a string, otherwise return value/default."""
        if value is None:
            return default
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return default
            try:
                return json.loads(stripped)
            except (json.JSONDecodeError, TypeError, ValueError):
                return default
        return value

    @classmethod
    def _normalize_source(cls, source):
        """Normalize source entries ensuring type and active defaults are present."""
        if not isinstance(source, dict):
            return None
        item = dict(source)
        item['type'] = str(item.get('type', 'podcast')).lower()
        item['active'] = item.get('active', True)
        if item['type'] == 'podcast':
            item.setdefault('window_hours', None)
            item.setdefault('days', None)
        return item

    @classmethod
    def _normalize_user_entry(cls, raw_user):
        """Normalize one user record to the internal schema."""
        if not isinstance(raw_user, dict):
            return None

        user_name = raw_user.get('user')
        if not user_name:
            return None

        podcasts_raw = cls._parse_json_string(raw_user.get('spotify_podcasts', []), [])
        if not isinstance(podcasts_raw, list):
            podcasts_raw = []

        sources_raw = raw_user.get('sources')
        if sources_raw is None:
            sources = []
            for podcast in podcasts_raw:
                if not isinstance(podcast, dict):
                    continue
                entry = dict(podcast)
                entry['type'] = 'podcast'
                entry.setdefault('active', True)
                entry.setdefault('window_hours', None)
                entry.setdefault('days', None)
                sources.append(entry)
        else:
            sources_raw = cls._parse_json_string(sources_raw, [])
            sources = []
            if isinstance(sources_raw, list):
                for source in sources_raw:
                    normalized = cls._normalize_source(source)
                    if normalized:
                        sources.append(normalized)

        queue_uris = cls._parse_json_string(raw_user.get('spotify_queue_uris', []), [])
        if not isinstance(queue_uris, list):
            queue_uris = []

        return {
            'user': user_name,
            'spotify_client_id': raw_user.get('spotify_client_id', ''),
            'spotify_client_secret': raw_user.get('spotify_client_secret', ''),
            'spotify_refresh_token': raw_user.get('spotify_refresh_token', ''),
            'spotify_device_id': raw_user.get('spotify_device_id', ''),
            'spotify_queue_playlist_id': raw_user.get('spotify_queue_playlist_id', ''),
            'sources': sources,
            'spotify_queue_uris': queue_uris,
        }

    @classmethod
    def _normalize_root_config(cls, raw_config):
        """Normalize root config supporting legacy and multiuser schemas."""
        if not isinstance(raw_config, dict):
            raw_config = {}

        users_raw = raw_config.get('users')
        if isinstance(users_raw, list):
            users = []
            for user in users_raw:
                normalized = cls._normalize_user_entry(user)
                if normalized:
                    users.append(normalized)

            if not users:
                raise ValueError("Config must contain at least one valid user")

            default_user = raw_config.get('default_user') or users[0]['user']
            users_set = {item['user'] for item in users}
            if default_user not in users_set:
                raise ValueError("default_user must match one of the configured users")

            return {
                'default_user': default_user,
                'users': users,
            }, False

        legacy_user = cls._normalize_user_entry({
            'user': 'default',
            'spotify_client_id': raw_config.get('spotify_client_id', ''),
            'spotify_client_secret': raw_config.get('spotify_client_secret', ''),
            'spotify_refresh_token': raw_config.get('spotify_refresh_token', ''),
            'spotify_device_id': raw_config.get('spotify_device_id', ''),
            'spotify_queue_playlist_id': raw_config.get('spotify_queue_playlist_id', ''),
            'spotify_podcasts': raw_config.get('spotify_podcasts', []),
            'spotify_queue_uris': raw_config.get('spotify_queue_uris', []),
        })
        return {
            'default_user': 'default',
            'users': [legacy_user],
        }, True

    @staticmethod
    def _build_spotify_dict(user_data):
        """Build the Spotify config dictionary consumed by SpotifyAPI."""
        podcasts = [
            source for source in user_data.get('sources', [])
            if source.get('type', 'podcast') == 'podcast'
        ]
        return {
            'client_id': user_data.get('spotify_client_id', ''),
            'client_secret': user_data.get('spotify_client_secret', ''),
            'refresh_token': user_data.get('spotify_refresh_token', ''),
            'device_id': user_data.get('spotify_device_id', ''),
            'queue_playlist_id': user_data.get('spotify_queue_playlist_id', ''),
            'podcasts': podcasts,
            'sources': user_data.get('sources', []),
            'queue_uris': user_data.get('spotify_queue_uris', []),
        }

    def _load_root_config(self):
        """Load root config from SSM (if configured) or local config file."""
        users_config = self.__get_parameter__('spotify_users_config', None)
        users_config = self._parse_json_string(users_config, users_config)
        if isinstance(users_config, dict) and users_config:
            return users_config

        _ensure_config()
        data = _load_json(CONFIGFILE)
        return data if isinstance(data, dict) else {}

    def _save_root_config(self, data):
        """Persist root config to local file and SSM (best effort)."""
        if _ssm_available():
            try:
                ssm = _get_ssm_client()
                if ssm:
                    ssm.put_parameter(
                        Name='spotify_users_config',
                        Value=json.dumps(data, ensure_ascii=False),
                        Type='String',
                        Overwrite=True,
                    )
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "SSM put_parameter failed for 'spotify_users_config': %s", exc)

        _ensure_config()
        with open(CONFIGFILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

    def set_spotify_queue(self, uris):
        """Persist the pre-built Spotify episode URIs for later playback."""
        self.spotify['queue_uris'] = uris
        self._users_by_name[self.current_user]['spotify_queue_uris'] = uris

        if self._legacy_mode:
            self.__set_parameter__('spotify_queue_uris', uris, 'list')
            return

        payload = {
            'default_user': self.default_user,
            'users': list(self._users_by_name.values()),
        }
        self._save_root_config(payload)

    def __get_parameter__(self, parameter, default=''):
        if _ssm_available() and parameter in _SSM_PARAMETERS:
            try:
                ssm = _get_ssm_client()
                if ssm:
                    response = ssm.get_parameter(
                        Name=parameter, WithDecryption=True)
                    raw = response['Parameter']['Value']
                    # Try to parse as JSON (covers lists and dicts stored as JSON strings)
                    try:
                        return json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        return raw
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "SSM get_parameter failed for '%s': %s. Falling back to local config", parameter, exc)

        _ensure_config()
        data = _load_json(CONFIGFILE)
        return data.get(parameter, default)

    def __set_parameter__(self, parameter, value, value_type):
        if _ssm_available() and parameter in _SSM_PARAMETERS:
            try:
                ssm = _get_ssm_client()
                if ssm:
                    ssm_value = json.dumps(value, ensure_ascii=False) if not isinstance(
                        value, str) else value
                    ssm.put_parameter(
                        Name=parameter,
                        Value=ssm_value,
                        Type='String',
                        Overwrite=True,
                    )
                    return True
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "SSM put_parameter failed for '%s': %s. Falling back to local config", parameter, exc)

        _ensure_config()
        data = _load_json(CONFIGFILE)
        if value_type == "String":
            data[parameter] = str(value)
        else:
            data[parameter] = value
        with open(CONFIGFILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
