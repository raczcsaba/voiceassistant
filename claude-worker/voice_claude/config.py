"""Configuration: config.json (deployment values) plus secret files in secrets_dir."""
import copy
import json
import os

DEFAULTS = {
    "listen": {"host": "0.0.0.0", "port": 8099},
    "secrets_dir": "/opt/voice/claude",
    "data_dir": "/opt/voice/claude/data",
    "timezone": "Europe/Budapest",
    "dry_run": False,
    "home_assistant": {
        "url": "http://homeassistant.local:8123",
        "token_file": "ha.token",
        "default_satellite": None,
        "jellyfin_play_path": "/api/jellyfin_panel/play",
        "jellyfin_play_device": "tv",
    },
    "music_assistant": {
        "url": "ws://homeassistant.local:8095/ws",
        "token_file": "ma.token",
        "playlist_provider": None,
        "default_player": None,
        "player_aliases": {},
        "player_hint": None,
    },
    "jellyfin": {
        "url": "http://jellyfin.local:8096",
        "key_file": "jellyfin.key",
        "user": None,
        "tv_device_name": "TV",
    },
    "anthropic": {
        "key_file": "anthropic.key",
        "model": "claude-sonnet-5-5",
        "allowed_models": ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"],
        "effort": "low",
        "max_tokens": 4096,
        "final_max_chars": 180,
        "web_search_tool": {"default": "web_search_20260209"},
        "max_web_searches": 3,
    },
    "limits": {"max_turns": 12, "max_seconds": 150, "max_task_usd": 0.60, "monthly_usd": 30.0},
    "status": {"min_gap_s": 6, "quiet_after_ack_s": 4, "max_per_task": 2, "max_words": 6, "idle_notice_s": 15,
               "idle_text": "Még dolgozom rajta."},
    "home_control": {"readable": {}, "actions": {}, "read_endpoints": {}, "weather_entity": None, "manual": []},
    "seerr": {"url": None, "key_file": "seerr.key", "user_id": None, "notify_service": None, "poll_minutes": 5,
              "pending_seconds": 180, "quiet_start": 22, "quiet_end": 8, "dry_run": False},
    "catalogue": {"refresh_hours": 6, "max_artists": 600, "max_tracks": 600},
    "pricing": {
        "web_search_per_1000": 10.0,
        "models": {},
    },
}


def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load(path):
    cfg = copy.deepcopy(DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            _merge(cfg, json.load(f))
    return cfg


def secret(cfg, filename):
    """Read a secret file from secrets_dir; None when missing or empty."""
    if not filename:
        return None
    path = filename if os.path.isabs(filename) else os.path.join(cfg["secrets_dir"], filename)
    try:
        with open(path, encoding="utf-8") as f:
            value = f.read().strip()
    except OSError:
        return None
    return value or None
