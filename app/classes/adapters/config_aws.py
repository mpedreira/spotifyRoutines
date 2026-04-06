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

    def __init__(self):
        """Init method for ConfigAWS."""
        spotify_podcasts_raw = self.__get_parameter__('spotify_podcasts', [])
        self.spotify = {
            'client_id': self.__get_parameter__('spotify_client_id', ''),
            'client_secret': self.__get_parameter__('spotify_client_secret', ''),
            'refresh_token': self.__get_parameter__('spotify_refresh_token', ''),
            'device_id': self.__get_parameter__('spotify_device_id', ''),
            'queue_playlist_id': self.__get_parameter__(
                'spotify_queue_playlist_id', ''),
            'podcasts': spotify_podcasts_raw if isinstance(
                spotify_podcasts_raw, list) else json.loads(spotify_podcasts_raw),
            'queue_uris': self.__get_parameter__('spotify_queue_uris', []),
        }

    def set_spotify_queue(self, uris):
        """Persist the pre-built Spotify episode URIs for later playback."""
        self.__set_parameter__('spotify_queue_uris', uris, 'list')
        self.spotify['queue_uris'] = uris

    def __get_parameter__(self, parameter, default=''):
        if _ssm_available() and parameter in _SSM_PARAMETERS:
            try:
                ssm = _get_ssm_client()
                if ssm:
                    response = ssm.get_parameter(Name=parameter, WithDecryption=True)
                    raw = response['Parameter']['Value']
                    # Try to parse as JSON (covers lists and dicts stored as JSON strings)
                    try:
                        return json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        return raw
            except ssm.exceptions.ParameterNotFound:  # pylint: disable=no-member
                logger.warning("SSM parameter '%s' not found, falling back to local config", parameter)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("SSM get_parameter failed for '%s': %s. Falling back to local config", parameter, exc)

        _ensure_config()
        data = _load_json(CONFIGFILE)
        return data.get(parameter, default)

    def __set_parameter__(self, parameter, value, value_type):
        if _ssm_available() and parameter in _SSM_PARAMETERS:
            try:
                ssm = _get_ssm_client()
                if ssm:
                    ssm_value = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
                    ssm.put_parameter(
                        Name=parameter,
                        Value=ssm_value,
                        Type='String',
                        Overwrite=True,
                    )
                    return True
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("SSM put_parameter failed for '%s': %s. Falling back to local config", parameter, exc)

        _ensure_config()
        data = _load_json(CONFIGFILE)
        if value_type == "String":
            data[parameter] = str(value)
        else:
            data[parameter] = value
        with open(CONFIGFILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
