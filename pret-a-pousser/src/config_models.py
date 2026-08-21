from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DEFAULTS_PATH = Path(__file__).with_name("config") / "app_defaults.json"


def load_defaults(path: str | None = None) -> dict:
    defaults_path = Path(path) if path else _DEFAULTS_PATH
    return json.loads(defaults_path.read_text(encoding="utf-8"))


DEFAULTS = load_defaults()


@dataclass
class AppConfig:
    command: str
    action: str | None
    set_left_intensity: str | None
    set_right_intensity: str | None
    set_left_start: str | None
    set_right_start: str | None
    set_left_end: str | None
    set_right_end: str | None
    set_clock_now: bool
    set_clock_seconds: int | None
    set_mirror_sides: bool
    auto_state_file: str
    restore_use_saved_clock: bool
    address: str
    adapter: str | None
    connect_timeout: float
    retries: int
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    mqtt_client_id: str
    topic_prefix: str
    topic_state: str
    topic_availability: str
    loop_retry_delay: float
    debug: bool
