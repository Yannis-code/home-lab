from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_MAPPING_PATH = Path(__file__).with_name("modulo2_mapping.json")


def load_mapping_json(path: str | None = None) -> dict:
    mapping_path = Path(path) if path else _MAPPING_PATH
    return json.loads(mapping_path.read_text(encoding="utf-8"))


MAPPING = load_mapping_json()
SERVICE_UUID = MAPPING["device"]["service_uuid"]
CHAR_UUIDS = MAPPING["characteristics"]
INTENSITY_PRESETS = {
    key: int(value)
    for key, value in MAPPING["intensity_presets"].items()
}
CHANNEL_GROUPS = MAPPING.get("groups", {})
AUTO_SNAPSHOT_KEYS = CHANNEL_GROUPS.get(
    "auto_snapshot",
    [
        "clock",
        "left_profile_param",
        "right_profile_param",
        "left_intensity",
        "right_intensity",
        "left_start",
        "right_start",
        "left_end",
        "right_end",
        "flags",
        "reserved",
    ],
)
AUTO_RESTORE_KEYS = CHANNEL_GROUPS.get(
    "auto_restore",
    [
        "left_profile_param",
        "right_profile_param",
        "left_intensity",
        "right_intensity",
        "left_start",
        "right_start",
        "left_end",
        "right_end",
        "reserved",
    ],
)


def action_to_intensity(action: str) -> int:
    value = INTENSITY_PRESETS.get(action.lower())
    if value is None:
        raise ValueError(f"Action inconnue: {action}")
    return value


def resolve_intensity_value(raw: str) -> int:
    lowered = raw.strip().lower()
    if lowered in INTENSITY_PRESETS:
        return INTENSITY_PRESETS[lowered]

    base = 16 if lowered.startswith("0x") else 10
    value = int(lowered, base)
    if not 0 <= value <= 255:
        raise ValueError(f"Intensite hors plage 0..255: {value}")
    return value


def parse_hhmm_to_seconds(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"Heure invalide: {value} (attendu HH:MM ou HH:MM:SS)")

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2]) if len(parts) == 3 else 0

    if not 0 <= hours <= 23:
        raise ValueError(f"Heure invalide: {hours}")
    if not 0 <= minutes <= 59:
        raise ValueError(f"Minutes invalides: {minutes}")
    if not 0 <= seconds <= 59:
        raise ValueError(f"Secondes invalides: {seconds}")

    return hours * 3600 + minutes * 60 + seconds


def seconds_to_le32(seconds: int) -> bytearray:
    if not 0 <= seconds <= 86399:
        raise ValueError(f"Secondes depuis minuit hors plage: {seconds}")
    return bytearray(seconds.to_bytes(4, "little", signed=False))


def hhmm_to_le32(value: str) -> bytearray:
    return seconds_to_le32(parse_hhmm_to_seconds(value))


def current_seconds_of_day() -> int:
    now = datetime.now()
    return now.hour * 3600 + now.minute * 60 + now.second


@dataclass
class SetChannelsInput:
    left_intensity: str | None = None
    right_intensity: str | None = None
    left_start: str | None = None
    right_start: str | None = None
    left_end: str | None = None
    right_end: str | None = None
    clock_now: bool = False
    clock_seconds: int | None = None
    mirror_sides: bool = False


def _mirror_right(left: str | None, right: str | None, mirror: bool) -> str | None:
    if mirror and right is None:
        return left
    return right


def _append_optional_write(
    writes: list[tuple[str, bytearray]],
    char_key: str,
    value: str | None,
    encoder,
) -> None:
    if value is None:
        return
    writes.append((CHAR_UUIDS[char_key], encoder(value)))


def build_set_writes(cfg: SetChannelsInput) -> list[tuple[str, bytearray]]:
    left_intensity = cfg.left_intensity
    right_intensity = _mirror_right(cfg.left_intensity, cfg.right_intensity, cfg.mirror_sides)
    left_start = cfg.left_start
    right_start = _mirror_right(cfg.left_start, cfg.right_start, cfg.mirror_sides)
    left_end = cfg.left_end
    right_end = _mirror_right(cfg.left_end, cfg.right_end, cfg.mirror_sides)

    writes: list[tuple[str, bytearray]] = []

    if cfg.clock_now and cfg.clock_seconds is not None:
        raise ValueError("Utiliser soit clock-now, soit clock-seconds, pas les deux")
    if cfg.clock_now:
        writes.append((CHAR_UUIDS["clock"], seconds_to_le32(current_seconds_of_day())))
    elif cfg.clock_seconds is not None:
        writes.append((CHAR_UUIDS["clock"], seconds_to_le32(cfg.clock_seconds)))

    _append_optional_write(
        writes,
        "left_intensity",
        left_intensity,
        lambda raw: bytearray([resolve_intensity_value(raw)]),
    )
    _append_optional_write(
        writes,
        "right_intensity",
        right_intensity,
        lambda raw: bytearray([resolve_intensity_value(raw)]),
    )

    for char_key, value in (
        ("left_start", left_start),
        ("right_start", right_start),
        ("left_end", left_end),
        ("right_end", right_end),
    ):
        _append_optional_write(writes, char_key, value, hhmm_to_le32)

    if not writes:
        raise ValueError("Aucune valeur a ecrire. Fournir au moins un parametre --left-*/--right-* ou clock")

    return writes
