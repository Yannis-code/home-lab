from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from src.ble_controller import PotagerController
from src.config_models import AppConfig, DEFAULTS
from src.mqtt_bridge import MqttBridge

LOGGER = logging.getLogger("potager_ble")


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Controle BLE du potager Modulo (Raspberry Pi)."
    )
    parser.add_argument("--name", default=env("POTAGER_NAME", DEFAULTS["target_name"]))
    parser.add_argument("--address", default=os.getenv("POTAGER_ADDRESS"))
    parser.add_argument("--adapter", default=os.getenv("POTAGER_ADAPTER"))
    parser.add_argument(
        "--scan-timeout",
        type=float,
        default=float(env("POTAGER_SCAN_TIMEOUT", str(DEFAULTS["scan_timeout"]))),
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=float(env("POTAGER_CONNECT_TIMEOUT", str(DEFAULTS["connect_timeout"]))),
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=int(env("POTAGER_RETRIES", str(DEFAULTS["retries"]))),
    )
    parser.add_argument(
        "--state-file",
        default=env("POTAGER_STATE_FILE", DEFAULTS["state_file"]),
    )
    parser.add_argument("--mqtt-host", default=env("MQTT_HOST", "localhost"))
    parser.add_argument("--mqtt-port", type=int, default=int(env("MQTT_PORT", "1883")))
    parser.add_argument("--mqtt-username", default=os.getenv("MQTT_USERNAME"))
    parser.add_argument("--mqtt-password", default=os.getenv("MQTT_PASSWORD"))
    parser.add_argument(
        "--mqtt-client-id",
        default=env("MQTT_CLIENT_ID", DEFAULTS["mqtt_client_id"]),
    )
    parser.add_argument(
        "--mqtt-topic-prefix",
        default=env("POTAGER_TOPIC_PREFIX", DEFAULTS["mqtt_topic_prefix"]),
    )
    parser.add_argument(
        "--loop-retry-delay",
        type=float,
        default=float(env("POTAGER_LOOP_RETRY_DELAY", str(DEFAULTS["loop_retry_delay"]))),
    )
    parser.add_argument("--debug", action="store_true", default=env("POTAGER_DEBUG", "0") == "1")

    subparsers = parser.add_subparsers(dest="command")
    send_parser = subparsers.add_parser("send", help="Envoi BLE one-shot")
    send_parser.add_argument("action", choices=["on", "off"])

    set_parser = subparsers.add_parser("set", help="Ecriture BLE des canaux (intensite/horaires/clock)")
    set_parser.add_argument("--left-intensity", help="Intensite gauche: off|photo|faible|printemps|ete|0..255")
    set_parser.add_argument("--right-intensity", help="Intensite droite: off|photo|faible|printemps|ete|0..255")
    set_parser.add_argument("--left-start", help="Debut cycle gauche (HH:MM ou HH:MM:SS)")
    set_parser.add_argument("--right-start", help="Debut cycle droit (HH:MM ou HH:MM:SS)")
    set_parser.add_argument("--left-end", help="Fin cycle gauche (HH:MM ou HH:MM:SS)")
    set_parser.add_argument("--right-end", help="Fin cycle droit (HH:MM ou HH:MM:SS)")
    set_parser.add_argument("--clock-now", action="store_true", help="Met l'horloge interne a l'heure locale")
    set_parser.add_argument("--clock-seconds", type=int, help="Met l'horloge interne (secondes depuis minuit)")
    set_parser.add_argument("--mirror-sides", action="store_true", help="Copie les champs gauche vers droite si la droite est omise")

    save_auto_parser = subparsers.add_parser("auto-save", help="Sauvegarde l'etat BLE courant du mode auto")
    save_auto_parser.add_argument(
        "--auto-state-file",
        default=env("POTAGER_AUTO_STATE_FILE", DEFAULTS["auto_state_file"]),
        help="Fichier JSON de sauvegarde de l'etat auto",
    )

    restore_auto_parser = subparsers.add_parser("auto-restore", help="Restaure l'etat auto depuis un JSON")
    restore_auto_parser.add_argument(
        "--auto-state-file",
        default=env("POTAGER_AUTO_STATE_FILE", DEFAULTS["auto_state_file"]),
        help="Fichier JSON de sauvegarde de l'etat auto",
    )
    restore_auto_parser.add_argument(
        "--use-saved-clock",
        action="store_true",
        help="Restaure aussi l'horloge snapshot (par defaut: horloge locale actuelle)",
    )

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
        set_left_intensity=getattr(args, "left_intensity", None),
        set_right_intensity=getattr(args, "right_intensity", None),
        set_left_start=getattr(args, "left_start", None),
        set_right_start=getattr(args, "right_start", None),
        set_left_end=getattr(args, "left_end", None),
        set_right_end=getattr(args, "right_end", None),
        set_clock_now=getattr(args, "clock_now", False),
        set_clock_seconds=getattr(args, "clock_seconds", None),
        set_mirror_sides=getattr(args, "mirror_sides", False),
        auto_state_file=getattr(args, "auto_state_file", env("POTAGER_AUTO_STATE_FILE", DEFAULTS["auto_state_file"])),
        restore_use_saved_clock=getattr(args, "use_saved_clock", False),
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
        topic_prefix=prefix,
        topic_set=f"{prefix}/set",
        topic_state=f"{prefix}/state",
        topic_availability=f"{prefix}/availability",
        topic_error=f"{prefix}/error",
        topic_auto_save_set=f"{prefix}/auto/save/set",
        topic_auto_restore_set=f"{prefix}/auto/restore/set",
        topic_auto_saved=f"{prefix}/auto/saved",
        topic_auto_restored=f"{prefix}/auto/restored",
        loop_retry_delay=args.loop_retry_delay,
        debug=args.debug,
    )


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
    if cfg.set_clock_seconds is not None and not (0 <= cfg.set_clock_seconds <= 86399):
        raise ValueError("--clock-seconds doit etre entre 0 et 86399")
    if cfg.set_clock_now and cfg.set_clock_seconds is not None:
        raise ValueError("--clock-now et --clock-seconds sont exclusifs")
    if not cfg.auto_state_file.strip():
        raise ValueError("--auto-state-file ne peut pas etre vide")


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

        if cfg.command == "set":
            asyncio.run(controller.send_set_channels())
            LOGGER.info("Commande one-shot set envoyee")
            return 0

        if cfg.command == "auto-save":
            asyncio.run(controller.save_auto_state())
            LOGGER.info("Snapshot auto sauvegarde")
            return 0

        if cfg.command == "auto-restore":
            asyncio.run(controller.restore_auto_state())
            LOGGER.info("Snapshot auto restaure")
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
