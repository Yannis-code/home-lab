from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.ble_controller import PotagerController
from src.config_models import AppConfig
from src.modulo2_protocol import (
    CHAR_UUIDS,
    SetChannelsInput,
    build_set_writes,
    current_seconds_of_day,
    parse_hhmm_to_seconds,
    seconds_to_le32,
)

LOGGER = logging.getLogger("potager_ble")


class MqttBridge:
    def __init__(self, cfg: AppConfig, controller: PotagerController):
        try:
            import paho.mqtt.client as mqtt  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Le mode daemon MQTT requiert paho-mqtt (pip install paho-mqtt)"
            ) from exc

        self.cfg = cfg
        self.controller = controller
        self._mqtt = mqtt
        callback_api = getattr(mqtt, "CallbackAPIVersion", None)
        if callback_api is not None:
            self.client = mqtt.Client(
                callback_api_version=callback_api.VERSION2,
                client_id=cfg.mqtt_client_id,
            )
        else:
            self.client = mqtt.Client(client_id=cfg.mqtt_client_id)

        if cfg.mqtt_username:
            self.client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)

        self.client.will_set(cfg.topic_availability, payload="offline", qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        p = cfg.topic_prefix
        self.topic_channels_set = f"{p}/channels/set"
        self.topic_left_intensity_set = f"{p}/left/intensity/set"
        self.topic_right_intensity_set = f"{p}/right/intensity/set"
        self.topic_left_start_set = f"{p}/left/start/set"
        self.topic_right_start_set = f"{p}/right/start/set"
        self.topic_left_end_set = f"{p}/left/end/set"
        self.topic_right_end_set = f"{p}/right/end/set"
        self.topic_clock_set = f"{p}/clock/set"
        self.topic_left_profile_param_set = f"{p}/left/profile-param/set"
        self.topic_right_profile_param_set = f"{p}/right/profile-param/set"
        self.topic_reserved_set = f"{p}/reserved/set"

        self._handlers: dict[str, Callable[[str, Any], None]] = {
            self.cfg.topic_set: self._handle_set,
            self.topic_channels_set: self._handle_channels_set,
            self.topic_left_intensity_set: self._handle_left_intensity,
            self.topic_right_intensity_set: self._handle_right_intensity,
            self.topic_left_start_set: self._handle_left_start,
            self.topic_right_start_set: self._handle_right_start,
            self.topic_left_end_set: self._handle_left_end,
            self.topic_right_end_set: self._handle_right_end,
            self.topic_clock_set: self._handle_clock_set,
            self.topic_left_profile_param_set: self._handle_left_profile_param,
            self.topic_right_profile_param_set: self._handle_right_profile_param,
            self.topic_reserved_set: self._handle_reserved,
            self.cfg.topic_auto_save_set: self._handle_auto_save,
            self.cfg.topic_auto_restore_set: self._handle_auto_restore,
        }

    def publish(self, topic: str, payload: str, retain: bool = True) -> None:
        result = self.client.publish(topic, payload=payload, qos=1, retain=retain)
        if result.rc != self._mqtt.MQTT_ERR_SUCCESS:
            LOGGER.warning("Publication MQTT echouee sur %s (rc=%s)", topic, result.rc)

    def on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any):
        if reason_code != 0:
            LOGGER.error("Connexion MQTT echouee rc=%s", reason_code)
            return

        LOGGER.info("Connecte a MQTT %s:%d", self.cfg.mqtt_host, self.cfg.mqtt_port)
        for topic in self._handlers:
            self.client.subscribe(topic, qos=1)
        self.publish(self.cfg.topic_availability, "online")

    @staticmethod
    def _parse_raw_byte_payload(raw: str) -> bytearray:
        text = raw.strip().lower().replace(",", " ")
        if not text:
            raise ValueError("Payload vide")
        if " " in text:
            out = bytearray()
            for token in text.split():
                t = token[2:] if token.startswith("0x") else token
                out.append(int(t, 16))
            return out
        if text.startswith("0x"):
            text = text[2:]
            if len(text) % 2 == 1:
                text = "0" + text
            return bytearray.fromhex(text)
        if all(ch in "0123456789abcdef" for ch in text) and len(text) > 2:
            if len(text) % 2 == 1:
                text = "0" + text
            return bytearray.fromhex(text)
        value = int(text, 10)
        if not 0 <= value <= 255:
            raise ValueError(f"Octet hors plage: {value}")
        return bytearray([value])

    @staticmethod
    def _decode_payload(message: Any) -> str:
        return message.payload.decode("utf-8", errors="ignore").strip().upper()

    def _clear_error(self) -> None:
        self.publish(self.cfg.topic_error, "")

    def _publish_error(self, text: str) -> None:
        LOGGER.error(text)
        self.publish(self.cfg.topic_error, text)

    def _apply_set_input(self, cfg: SetChannelsInput, label: str) -> None:
        writes = build_set_writes(cfg)
        asyncio.run(self.controller.send_writes(label, writes))

    def _publish_auto_saved_status(self) -> None:
        path = Path(self.controller.cfg.auto_state_file)
        if not path.exists():
            self.publish(self.cfg.topic_auto_saved, "")
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            saved_at = str(data.get("saved_at", ""))
            payload = json.dumps({"saved_at": saved_at, "file": str(path)})
        except Exception:  # noqa: BLE001
            payload = json.dumps({"file": str(path)})
        self.publish(self.cfg.topic_auto_saved, payload)

    def _handle_set(self, payload: str, message: Any) -> None:
        if payload not in ("ON", "OFF"):
            err = f"Commande invalide sur {self.cfg.topic_set}: {payload}"
            LOGGER.warning(err)
            self.publish(self.cfg.topic_error, err)
            return

        action = payload.lower()
        try:
            asyncio.run(self.controller.send_action(action))
            self.publish(self.cfg.topic_state, payload)
            self._clear_error()
            LOGGER.info("Commande %s executee", payload)
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec BLE pour {payload}: {exc}")

    def _handle_channels_set(self, payload: str, message: Any) -> None:
        try:
            data = json.loads(message.payload.decode("utf-8", errors="ignore") or "{}")
            cfg = SetChannelsInput(
                left_intensity=data.get("left_intensity"),
                right_intensity=data.get("right_intensity"),
                left_start=data.get("left_start"),
                right_start=data.get("right_start"),
                left_end=data.get("left_end"),
                right_end=data.get("right_end"),
                clock_now=bool(data.get("clock_now", False)),
                clock_seconds=data.get("clock_seconds"),
                mirror_sides=bool(data.get("mirror_sides", False)),
            )

            writes = build_set_writes(cfg)
            for key in ("left_profile_param", "right_profile_param", "reserved"):
                if key in data and data[key] is not None:
                    writes.append(
                        (CHAR_UUIDS[key], self._parse_raw_byte_payload(str(data[key])))
                    )

            asyncio.run(self.controller.send_writes("mqtt channels/set", writes))
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt channels/set: {exc}")

    def _handle_left_intensity(self, payload: str, message: Any) -> None:
        try:
            self._apply_set_input(
                SetChannelsInput(left_intensity=payload.lower()),
                "mqtt left intensity",
            )
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt left intensity: {exc}")

    def _handle_right_intensity(self, payload: str, message: Any) -> None:
        try:
            self._apply_set_input(
                SetChannelsInput(right_intensity=payload.lower()),
                "mqtt right intensity",
            )
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt right intensity: {exc}")

    def _handle_left_start(self, payload: str, message: Any) -> None:
        try:
            self._apply_set_input(SetChannelsInput(left_start=payload), "mqtt left start")
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt left start: {exc}")

    def _handle_right_start(self, payload: str, message: Any) -> None:
        try:
            self._apply_set_input(SetChannelsInput(right_start=payload), "mqtt right start")
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt right start: {exc}")

    def _handle_left_end(self, payload: str, message: Any) -> None:
        try:
            self._apply_set_input(SetChannelsInput(left_end=payload), "mqtt left end")
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt left end: {exc}")

    def _handle_right_end(self, payload: str, message: Any) -> None:
        try:
            self._apply_set_input(SetChannelsInput(right_end=payload), "mqtt right end")
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt right end: {exc}")

    def _handle_clock_set(self, payload: str, message: Any) -> None:
        try:
            if payload in ("", "NOW"):
                clock_payload = seconds_to_le32(current_seconds_of_day())
            elif ":" in payload:
                clock_payload = seconds_to_le32(parse_hhmm_to_seconds(payload))
            else:
                clock_payload = seconds_to_le32(int(payload, 10))
            asyncio.run(
                self.controller.send_raw_channels(
                    {"clock": clock_payload},
                    "mqtt clock set",
                )
            )
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt clock set: {exc}")

    def _handle_left_profile_param(self, payload: str, message: Any) -> None:
        try:
            payload_bytes = self._parse_raw_byte_payload(payload)
            asyncio.run(
                self.controller.send_raw_channels(
                    {"left_profile_param": payload_bytes},
                    "mqtt left profile",
                )
            )
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt left profile param: {exc}")

    def _handle_right_profile_param(self, payload: str, message: Any) -> None:
        try:
            payload_bytes = self._parse_raw_byte_payload(payload)
            asyncio.run(
                self.controller.send_raw_channels(
                    {"right_profile_param": payload_bytes},
                    "mqtt right profile",
                )
            )
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt right profile param: {exc}")

    def _handle_reserved(self, payload: str, message: Any) -> None:
        try:
            payload_bytes = self._parse_raw_byte_payload(payload)
            asyncio.run(
                self.controller.send_raw_channels(
                    {"reserved": payload_bytes},
                    "mqtt reserved",
                )
            )
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt reserved: {exc}")

    def _handle_auto_save(self, payload: str, message: Any) -> None:
        if payload not in ("", "1", "ON", "SAVE"):
            err = f"Commande invalide sur {self.cfg.topic_auto_save_set}: {payload}"
            LOGGER.warning(err)
            self.publish(self.cfg.topic_error, err)
            return

        try:
            asyncio.run(self.controller.save_auto_state())
            self._publish_auto_saved_status()
            self._clear_error()
            LOGGER.info("Auto-save execute via MQTT")
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec auto-save BLE: {exc}")

    def _handle_auto_restore(self, payload: str, message: Any) -> None:
        if payload not in ("", "1", "ON", "RESTORE"):
            err = f"Commande invalide sur {self.cfg.topic_auto_restore_set}: {payload}"
            LOGGER.warning(err)
            self.publish(self.cfg.topic_error, err)
            return

        try:
            asyncio.run(self.controller.restore_auto_state())
            self.publish(
                self.cfg.topic_auto_restored,
                json.dumps(
                    {
                        "restored_at": datetime.now(timezone.utc).isoformat(),
                        "file": self.cfg.auto_state_file,
                        "use_saved_clock": self.cfg.restore_use_saved_clock,
                    }
                ),
            )
            self._clear_error()
            LOGGER.info("Auto-restore execute via MQTT")
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec auto-restore BLE: {exc}")

    def on_message(self, client: Any, userdata: Any, message: Any):
        payload = self._decode_payload(message)
        topic = message.topic
        LOGGER.info("Commande MQTT recue topic=%s payload=%s", topic, payload)

        handler = self._handlers.get(topic)
        if handler is None:
            LOGGER.debug("Message MQTT ignore sur topic non gere: %s", topic)
            return
        handler(payload, message)

    def run(self) -> None:
        LOGGER.info("Demarrage bridge MQTT continu")

        while True:
            try:
                try:
                    asyncio.run(self.controller.resolve_address(force_scan=False))
                except Exception as ble_exc:  # noqa: BLE001
                    LOGGER.warning(
                        "Initialisation BLE differee (%r). Le bridge MQTT continue.",
                        ble_exc,
                    )

                self.client.connect(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=60)
                self.client.loop_forever(retry_first_connection=True)
            except KeyboardInterrupt:
                raise
            except Exception:
                LOGGER.exception(
                    "Boucle bridge en erreur. Nouvelle tentative dans %.1fs",
                    self.cfg.loop_retry_delay,
                )
            finally:
                try:
                    self.client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
