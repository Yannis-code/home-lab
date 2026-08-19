import argparse
import asyncio
import logging
import os
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import paho.mqtt.client as mqtt
from bleak import BleakClient, BleakScanner

DEFAULT_TARGET_NAME = "Modulo2"
DEFAULT_SCAN_TIMEOUT = 15.0
DEFAULT_CONNECT_TIMEOUT = 15.0
DEFAULT_RETRIES = 2
DEFAULT_LOOP_RETRY_DELAY = 5.0
DEFAULT_STATE_FILE = "./.cache/last_mac.txt"
DEFAULT_MQTT_PREFIX = "potager/modulo2"
CHAR_1 = "c9d9bff5-324c-4b79-bbaf-8a473e6540ec"
CHAR_2 = "c9d9bff6-324c-4b79-bbaf-8a473e6540ec"
LOGGER = logging.getLogger("potager_ble")


@dataclass
class AppConfig:
    command: str
    action: str | None
    target_name: str
    address: str | None
    adapter: str | None
    scan_timeout: float
    connect_timeout: float
    retries: int
    state_file: str
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    mqtt_client_id: str
    topic_set: str
    topic_state: str
    topic_availability: str
    topic_error: str
    loop_retry_delay: float
    debug: bool


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Controle BLE du potager Modulo (Raspberry Pi)."
    )
    parser.add_argument("--name", default=env("POTAGER_NAME", DEFAULT_TARGET_NAME))
    parser.add_argument("--address", default=os.getenv("POTAGER_ADDRESS"))
    parser.add_argument("--adapter", default=os.getenv("POTAGER_ADAPTER"))
    parser.add_argument(
        "--scan-timeout",
        type=float,
        default=float(env("POTAGER_SCAN_TIMEOUT", str(DEFAULT_SCAN_TIMEOUT))),
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=float(env("POTAGER_CONNECT_TIMEOUT", str(DEFAULT_CONNECT_TIMEOUT))),
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=int(env("POTAGER_RETRIES", str(DEFAULT_RETRIES))),
    )
    parser.add_argument(
        "--state-file",
        default=env("POTAGER_STATE_FILE", DEFAULT_STATE_FILE),
    )
    parser.add_argument("--mqtt-host", default=env("MQTT_HOST", "localhost"))
    parser.add_argument("--mqtt-port", type=int, default=int(env("MQTT_PORT", "1883")))
    parser.add_argument("--mqtt-username", default=os.getenv("MQTT_USERNAME"))
    parser.add_argument("--mqtt-password", default=os.getenv("MQTT_PASSWORD"))
    parser.add_argument(
        "--mqtt-client-id",
        default=env("MQTT_CLIENT_ID", "potager-ble-bridge"),
    )
    parser.add_argument(
        "--mqtt-topic-prefix",
        default=env("POTAGER_TOPIC_PREFIX", DEFAULT_MQTT_PREFIX),
    )
    parser.add_argument(
        "--loop-retry-delay",
        type=float,
        default=float(env("POTAGER_LOOP_RETRY_DELAY", str(DEFAULT_LOOP_RETRY_DELAY))),
    )
    parser.add_argument("--debug", action="store_true", default=env("POTAGER_DEBUG", "0") == "1")

    subparsers = parser.add_subparsers(dest="command")
    send_parser = subparsers.add_parser("send", help="Envoi BLE one-shot")
    send_parser.add_argument("action", choices=["on", "off"])
    subparsers.add_parser("daemon", help="Bridge MQTT continu")

    args = parser.parse_args()
    if args.command is None:
        args.command = "daemon"
        args.action = None

    return args


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def to_config(args: argparse.Namespace) -> AppConfig:
    prefix = args.mqtt_topic_prefix.rstrip("/")
    return AppConfig(
        command=args.command,
        action=getattr(args, "action", None),
        target_name=args.name,
        address=args.address,
        adapter=args.adapter,
        scan_timeout=args.scan_timeout,
        connect_timeout=args.connect_timeout,
        retries=args.retries,
        state_file=args.state_file,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_username=args.mqtt_username,
        mqtt_password=args.mqtt_password,
        mqtt_client_id=args.mqtt_client_id,
        topic_set=f"{prefix}/set",
        topic_state=f"{prefix}/state",
        topic_availability=f"{prefix}/availability",
        topic_error=f"{prefix}/error",
        loop_retry_delay=args.loop_retry_delay,
        debug=args.debug,
    )


def action_to_value(action: str) -> int:
    return 0x64 if action == "on" else 0x00


class PotagerController:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.current_address = cfg.address

    def _state_path(self) -> Path:
        return Path(self.cfg.state_file)

    def _bluez(self) -> dict[str, str] | None:
        if self.cfg.adapter:
            return {"adapter": self.cfg.adapter}
        return None

    def load_last_mac(self) -> str | None:
        path = self._state_path()
        try:
            if not path.exists():
                return None
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            LOGGER.warning("Lecture cache MAC impossible (%s): %s", path, exc)
            return None
        if not value:
            return None
        LOGGER.info("Dernier MAC connu charge: %s", value)
        return value

    def save_last_mac(self, address: str) -> None:
        path = self._state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(address, encoding="utf-8")
            LOGGER.debug("MAC sauvegarde: %s", address)
        except OSError as exc:
            LOGGER.warning("Sauvegarde cache MAC impossible (%s): %s", path, exc)

    async def scan_for_address(self) -> str:
        LOGGER.info("Scan BLE en cours (%.1fs) pour trouver %s", self.cfg.scan_timeout, self.cfg.target_name)
        bluez = self._bluez()
        if bluez is None:
            devices = await BleakScanner.discover(timeout=self.cfg.scan_timeout)
        else:
            devices = await BleakScanner.discover(
                timeout=self.cfg.scan_timeout,
                bluez=bluez,
            )
        for device in devices:
            if device.name == self.cfg.target_name:
                LOGGER.info("Appareil trouve: %s (%s)", device.name, device.address)
                return device.address
        raise RuntimeError(f"Appareil {self.cfg.target_name} introuvable apres scan")

    async def test_connect(self, address: str) -> None:
        client_kwargs = {"timeout": self.cfg.connect_timeout}
        bluez = self._bluez()
        if bluez is not None:
            client_kwargs["bluez"] = bluez
        client = BleakClient(address, **client_kwargs)
        try:
            await client.connect()
            LOGGER.debug("Connexion test OK: %s", address)
        finally:
            with suppress(Exception):  # BLE/DBus peut lever EOFError au disconnect
                await client.disconnect()

    async def resolve_address(self, force_scan: bool = False) -> str:
        if not force_scan:
            candidates = [self.current_address, self.cfg.address, self.load_last_mac()]
            seen: set[str] = set()
            for candidate in candidates:
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                try:
                    LOGGER.info("Test connexion BLE sur MAC connu %s", candidate)
                    await self.test_connect(candidate)
                    self.current_address = candidate
                    self.save_last_mac(candidate)
                    return candidate
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("MAC connu invalide %s: %r", candidate, exc)

        scanned = await self.scan_for_address()
        await self.test_connect(scanned)
        self.current_address = scanned
        self.save_last_mac(scanned)
        return scanned

    async def send_action(self, action: str) -> None:
        value = action_to_value(action)
        attempts = max(1, self.cfg.retries + 1)

        for attempt in range(1, attempts + 1):
            try:
                address = self.current_address or await self.resolve_address(force_scan=False)
                LOGGER.info("Envoi commande %s vers %s (tentative %d/%d)", action, address, attempt, attempts)
                client_kwargs = {"timeout": self.cfg.connect_timeout}
                bluez = self._bluez()
                if bluez is not None:
                    client_kwargs["bluez"] = bluez
                client = BleakClient(address, **client_kwargs)
                await client.connect()
                sent = False
                try:
                    await client.write_gatt_char(CHAR_1, bytearray([value]), response=True)
                    await client.write_gatt_char(CHAR_2, bytearray([value]), response=True)
                    sent = True
                finally:
                    try:
                        await client.disconnect()
                    except Exception as disconnect_exc:  # noqa: BLE001
                        if sent:
                            LOGGER.warning(
                                "Disconnect BLE en erreur apres envoi (ignore): %r",
                                disconnect_exc,
                            )
                        else:
                            raise
                self.save_last_mac(address)
                return
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Echec tentative %d/%d: %s", attempt, attempts, exc)
                self.current_address = None
                if attempt < attempts:
                    await self.resolve_address(force_scan=True)
                else:
                    raise


class MqttBridge:
    def __init__(self, cfg: AppConfig, controller: PotagerController):
        self.cfg = cfg
        self.controller = controller
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=cfg.mqtt_client_id,
        )

        if cfg.mqtt_username:
            self.client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)

        self.client.will_set(cfg.topic_availability, payload="offline", qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def publish(self, topic: str, payload: str, retain: bool = True) -> None:
        result = self.client.publish(topic, payload=payload, qos=1, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.warning("Publication MQTT echouee sur %s (rc=%s)", topic, result.rc)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            LOGGER.error("Connexion MQTT echouee rc=%s", reason_code)
            return
        LOGGER.info("Connecte a MQTT %s:%d", self.cfg.mqtt_host, self.cfg.mqtt_port)
        self.client.subscribe(self.cfg.topic_set, qos=1)
        self.publish(self.cfg.topic_availability, "online")

    def on_message(self, client, userdata, message):
        payload = message.payload.decode("utf-8", errors="ignore").strip().upper()
        LOGGER.info("Commande MQTT recue: %s", payload)

        if payload not in ("ON", "OFF"):
            err = f"Commande invalide: {payload}"
            LOGGER.warning(err)
            self.publish(self.cfg.topic_error, err)
            return

        action = payload.lower()
        try:
            asyncio.run(self.controller.send_action(action))
            self.publish(self.cfg.topic_state, payload)
            self.publish(self.cfg.topic_error, "")
            LOGGER.info("Commande %s executee", payload)
        except Exception as exc:  # noqa: BLE001
            err = f"Echec BLE pour {payload}: {exc}"
            LOGGER.error(err)
            self.publish(self.cfg.topic_error, err)

    def run(self) -> None:
        LOGGER.info("Demarrage bridge MQTT continu")

        while True:
            try:
                # Tentative initiale non bloquante: le bridge MQTT doit rester disponible
                # meme si l'appareil BLE est temporairement indisponible.
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
            except Exception as exc:  # noqa: BLE001
                LOGGER.error(
                    "Boucle bridge en erreur (%r). Nouvelle tentative dans %.1fs",
                    exc,
                    self.cfg.loop_retry_delay,
                )
            finally:
                try:
                    self.client.disconnect()
                except Exception:  # noqa: BLE001
                    pass

            time.sleep(self.cfg.loop_retry_delay)


def validate_config(cfg: AppConfig) -> None:
    if cfg.scan_timeout <= 0:
        raise ValueError("--scan-timeout doit etre > 0")
    if cfg.connect_timeout <= 0:
        raise ValueError("--connect-timeout doit etre > 0")
    if cfg.retries < 0:
        raise ValueError("--retries doit etre >= 0")
    if cfg.mqtt_port <= 0 or cfg.mqtt_port > 65535:
        raise ValueError("--mqtt-port invalide")
    if cfg.loop_retry_delay <= 0:
        raise ValueError("--loop-retry-delay doit etre > 0")


def main() -> int:
    args = parse_args()
    cfg = to_config(args)
    configure_logging(cfg.debug)

    try:
        validate_config(cfg)
        controller = PotagerController(cfg)

        if cfg.command == "send":
            if cfg.action is None:
                raise ValueError("action requise en mode send")
            asyncio.run(controller.send_action(cfg.action))
            LOGGER.info("Commande one-shot %s envoyee", cfg.action)
            return 0

        bridge = MqttBridge(cfg, controller)
        bridge.run()
        return 0
    except KeyboardInterrupt:
        LOGGER.info("Arret demande par utilisateur")
        return 130
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Erreur fatale: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())