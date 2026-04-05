#!/usr/bin/env python3
# pylint: disable=C0301
# -*- coding: utf-8 -*-
"""Module for configuration of the application"""

import os
import shutil
import json
from app.classes.config import Config

# Bundled read-only copy (inside the zip in Lambda, or repo root locally)
_BASE_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_BUNDLED_CONFIG = os.path.join(_BASE_DIR, "config", "config.ini")

# Runtime writable copy: /tmp in Lambda (writable), same file locally
_TMP_CONFIG = "/tmp/config.ini" if os.path.exists(
    "/var/task") else _BUNDLED_CONFIG
CONFIGFILE = _TMP_CONFIG


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
        _ensure_config()
        data = _load_json(CONFIGFILE)
        return data.get(parameter, default)

    def __set_parameter__(self, parameter, value, value_type):
        _ensure_config()
        data = _load_json(CONFIGFILE)
        if value_type == "String":
            data[parameter] = str(value)
        else:
            data[parameter] = value
        with open(CONFIGFILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
