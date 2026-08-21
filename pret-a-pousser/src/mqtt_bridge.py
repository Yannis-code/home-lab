from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

from src.ble_controller import PotagerController
from src.config_models import AppConfig
from src.modulo2_protocol import (
    SetChannelsInput,
    build_preconfigured_state_writes,
    build_set_writes,
    decode_intensity_value,
    le32_to_seconds,
    seconds_to_hhmmss,
)

LOGGER = logging.getLogger("potager_ble")


class MqttBridge:
    PROFILE_STATES = ("auto", "manuel")
    ACTION_STATES = ("off", "faible", "printemps", "ete", "photo")
    PROFILE_FIELDS = (
        "left_intensity",
        "right_intensity",
        "left_start",
        "right_start",
        "left_end",
        "right_end",
    )

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
        self.client.on_disconnect = self.on_disconnect
        self._is_connected = False
        self._last_connect_log_ts = 0.0
        self._connect_log_interval_s = 60.0
        self._profiles_initialized_on_connect = False

        p = cfg.topic_prefix
        self.topic_state_set = f"{p}/state/set"
        self.topic_save = f"{p}/save"
        self.topic_clock = f"{p}/clock"
        self.topic_status_write = f"{p}/status/device-write"
        self.topic_status_profile = f"{p}/status/active-profile"
        self.topic_status_last_command = f"{p}/status/last-command"
        self.topic_profile_state = {
            state: f"{p}/{state}" for state in self.PROFILE_STATES
        }

        self.model = self._default_model()

        self._handlers: dict[str, Callable[[str, Any], None]] = {
            self.topic_state_set: self._handle_state_set,
            self.topic_save: self._handle_save,
        }
        for state in self.PROFILE_STATES:
            self._handlers[self.topic_profile_state[state]] = self._build_profile_set_handler(state)

    def publish(self, topic: str, payload: str, retain: bool = True) -> None:
        result = self.client.publish(topic, payload=payload, qos=1, retain=retain)
        if result.rc != self._mqtt.MQTT_ERR_SUCCESS:
            LOGGER.warning("Publication MQTT echouee sur %s (rc=%s)", topic, result.rc)

    def _new_null_profile(self) -> dict[str, str | None]:
        return {field: None for field in self.PROFILE_FIELDS}

    def _default_model(self) -> dict[str, Any]:
        return {
            "clock": None,
            "state": None,
            "profiles": {
                state: self._new_null_profile() for state in self.PROFILE_STATES
            },
        }

    @staticmethod
    def _new_printemps_profile() -> dict[str, str | None]:
        return {
            "left_intensity": "printemps",
            "right_intensity": "printemps",
            "left_start": "08:00",
            "right_start": "08:00",
            "left_end": "22:00",
            "right_end": "22:00",
        }

    def _initialize_default_profiles_on_first_connect(self) -> None:
        if self._profiles_initialized_on_connect:
            return

        auto_profile = self.model["profiles"]["auto"]
        manuel_profile = self.model["profiles"]["manuel"]

        if not self._profile_complete(auto_profile):
            self.model["profiles"]["auto"] = self._new_null_profile()

        if not self._profile_complete(manuel_profile):
            self.model["profiles"]["manuel"] = self._new_printemps_profile()

        self._profiles_initialized_on_connect = True

    def _publish_model_topics(self) -> None:
        clock_value = self.model.get("clock")
        state_value = self.model.get("state")
        self.publish(self.topic_clock, self._clock_topic_payload(clock_value))
        self.publish(self.cfg.topic_state, "null" if state_value is None else str(state_value))
        for state in self.PROFILE_STATES:
            self.publish(self.topic_profile_state[state], json.dumps(self.model["profiles"][state]))

    def _clock_topic_payload(self, value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, int):
            return seconds_to_hhmmss(value)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return "null"
            if stripped.isdigit():
                return seconds_to_hhmmss(int(stripped))
            return stripped
        return str(value)

    def _publish_status(self, topic: str, payload: dict[str, Any]) -> None:
        self.publish(topic, json.dumps(payload), retain=False)

    def _send_profile(self, state: str, profile: dict[str, str | None], source: str) -> None:
        cfg = SetChannelsInput(
            left_intensity=str(profile["left_intensity"]),
            right_intensity=str(profile["right_intensity"]),
            left_start=str(profile["left_start"]),
            right_start=str(profile["right_start"]),
            left_end=str(profile["left_end"]),
            right_end=str(profile["right_end"]),
        )
        writes = build_set_writes(cfg)
        asyncio.run(self.controller.send_writes(f"mqtt profile/{state}", writes))
        self._publish_status(
            self.topic_status_write,
            {
                "result": "sent",
                "state": state,
                "source": source,
            },
        )

    def _perform_save_fetch(self, source: str) -> dict[str, str | None]:
        profile = self._fetch_profile_from_device()
        self.model["profiles"]["auto"] = profile
        self.publish(self.topic_profile_state["auto"], json.dumps(profile))
        self._publish_status(
            self.topic_status_last_command,
            {"type": source, "value": "trigger"},
        )
        self._publish_status(
            self.topic_status_write,
            {"result": "sent", "source": source, "target": "topic"},
        )
        self._clear_error()
        return profile

    def _fetch_profile_from_device(self) -> dict[str, str | None]:
        channel_keys = list(self.PROFILE_FIELDS) + ["clock"]
        values = asyncio.run(self.controller.read_channels("mqtt save", channel_keys))

        clock_raw = values.get("clock")
        if clock_raw is not None:
            clock_value = le32_to_seconds(clock_raw)
            self.model["clock"] = clock_value
            self.publish(self.topic_clock, self._clock_topic_payload(clock_value))

        profile = self._new_null_profile()
        for key in self.PROFILE_FIELDS:
            raw = values.get(key)
            if raw is None:
                continue
            if key.endswith("_intensity"):
                profile[key] = decode_intensity_value(raw[0])
            else:
                profile[key] = seconds_to_hhmmss(le32_to_seconds(raw))
        return profile

    def _profile_complete(self, profile: dict[str, Any]) -> bool:
        for field in self.PROFILE_FIELDS:
            value = profile.get(field)
            if value is None:
                return False
            if isinstance(value, str) and value.strip() == "":
                return False
        return True

    def _send_state_profile_if_complete(self, state: str, source: str) -> None:
        profile = self.model["profiles"][state]
        complete = self._profile_complete(profile)
        self._publish_status(
            self.topic_status_profile,
            {
                "state": state,
                "complete": complete,
                "source": source,
            },
        )
        if not complete:
            self._publish_status(
                self.topic_status_write,
                {
                    "result": "skipped",
                    "reason": "profile contains null field(s)",
                    "state": state,
                    "source": source,
                },
            )
            return

        try:
            self._send_profile(state, profile, source)
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt profile/{state}: {exc}")
            self._publish_status(
                self.topic_status_write,
                {
                    "result": "error",
                    "state": state,
                    "source": source,
                    "error": str(exc),
                },
            )

    def on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any):
        if reason_code != 0:
            LOGGER.error("Connexion MQTT echouee rc=%s", reason_code)
            return

        now = time.monotonic()
        if (not self._is_connected) or (now - self._last_connect_log_ts >= self._connect_log_interval_s):
            LOGGER.info("Connecte a MQTT %s:%d", self.cfg.mqtt_host, self.cfg.mqtt_port)
            self._last_connect_log_ts = now
        else:
            LOGGER.debug("Reconnect MQTT rapide (log info supprime)")

        self._is_connected = True
        for topic in self._handlers:
            self.client.subscribe(topic, qos=1)
        self._initialize_default_profiles_on_first_connect()
        self.publish(self.cfg.topic_availability, "online")

    def on_disconnect(self, client: Any, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any):
        self._is_connected = False
        if reason_code != 0:
            LOGGER.warning("Deconnexion MQTT rc=%s", reason_code)
        else:
            LOGGER.info("Deconnexion MQTT propre")

    @staticmethod
    def _decode_payload(message: Any) -> str:
        return message.payload.decode("utf-8", errors="ignore").strip()

    def _clear_error(self) -> None:
        self._publish_status(
            self.topic_status_write,
            {
                "result": "ok",
                "source": "bridge",
            },
        )

    def _publish_error(self, text: str, state: str | None = None, source: str = "bridge") -> None:
        LOGGER.error(text)
        payload: dict[str, Any] = {
            "result": "error",
            "source": source,
            "error": text,
        }
        if state is not None:
            payload["state"] = state
        self._publish_status(self.topic_status_write, payload)

    def _handle_state_set(self, payload: str, message: Any) -> None:
        value = payload.strip().lower()
        if value == "null":
            self.model["state"] = None
            self.publish(self.cfg.topic_state, "null")
            return

        if value == "été":
            value = "ete"
        if value == "manual":
            value = "manuel"

        if value in self.ACTION_STATES:
            try:
                writes = build_preconfigured_state_writes(value)
                asyncio.run(self.controller.send_writes(f"mqtt preconfigured/{value}", writes))
                self.model["state"] = value
                self.publish(self.cfg.topic_state, value)
                self._publish_status(
                    self.topic_status_last_command,
                    {"type": "state/set", "value": value},
                )
                self._publish_status(
                    self.topic_status_write,
                    {"result": "sent", "state": value, "source": "state/set"},
                )
                self._clear_error()
            except Exception as exc:  # noqa: BLE001
                self._publish_error(f"Echec BLE pour state={value}: {exc}", state=value, source="state/set")
                self._publish_status(
                    self.topic_status_write,
                    {
                        "result": "error",
                        "state": value,
                        "source": "state/set",
                        "error": str(exc),
                    },
                )
            return

        if value not in self.PROFILE_STATES:
            err = f"Etat invalide sur {self.topic_state_set}: {payload}"
            LOGGER.warning(err)
            self._publish_error(err, source="state/set")
            return

        if not self._profile_complete(self.model["profiles"][value]):
            err = f"Profil incomplet pour state={value}"
            self._publish_error(err, state=value, source="state/set")
            self._publish_status(
                self.topic_status_write,
                {
                    "result": "error",
                    "state": value,
                    "source": "state/set",
                    "reason": "profile contains null field(s) in MQTT",
                },
            )
            return

        self.model["state"] = value
        self.publish(self.cfg.topic_state, value)
        self._publish_status(
            self.topic_status_last_command,
            {"type": "state/set", "value": value},
        )
        self._clear_error()

        self._send_state_profile_if_complete(value, "state/set")

    def _build_profile_set_handler(self, state: str) -> Callable[[str, Any], None]:
        def _handler(payload: str, message: Any) -> None:
            self._handle_profile_set(state, message)

        return _handler

    def _handle_profile_set(self, state: str, message: Any) -> None:
        try:
            data = json.loads(message.payload.decode("utf-8", errors="ignore") or "{}")
            if not isinstance(data, dict):
                raise ValueError("Payload JSON objet attendu")

            profile = self.model["profiles"][state]
            for field in self.PROFILE_FIELDS:
                if field not in data:
                    continue
                value = data[field]
                profile[field] = None if value is None else str(value)
            self._publish_status(
                self.topic_status_last_command,
                {"type": state, "payload": data},
            )

            if self.model.get("state") == state:
                self._send_state_profile_if_complete(state, f"{state}/set")
            self._clear_error()
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec mqtt {state}: {exc}", state=state, source=state)

    def _handle_save(self, payload: str, message: Any) -> None:
        if payload.strip().lower() != "trigger":
            err = f"Commande invalide sur {self.topic_save}: {payload}"
            LOGGER.warning(err)
            self._publish_error(err, source="save")
            return

        try:
            self._perform_save_fetch("save")
            LOGGER.info("Save trigger execute: profil auto publie sur MQTT")
        except Exception as exc:  # noqa: BLE001
            self._publish_error(f"Echec save trigger: {exc}", source="save")

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
                    asyncio.run(self.controller.resolve_address())
                except Exception as ble_exc:  # noqa: BLE001
                    LOGGER.warning(
                        "Initialisation BLE differee (%r). Le bridge MQTT continue.",
                        ble_exc,
                    )

                self.client.connect(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=60)
                rc = self.client.loop_forever(retry_first_connection=True)
                LOGGER.warning("Boucle MQTT interrompue (rc=%s)", rc)
            except KeyboardInterrupt:
                self.controller.cleanup_on_shutdown()
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

            time.sleep(self.cfg.loop_retry_delay)
