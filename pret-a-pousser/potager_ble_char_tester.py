import argparse
import asyncio
import logging
from typing import Optional

from bleak import BleakClient, BleakScanner

DEFAULT_NAME = "Modulo2"
DEFAULT_SCAN_TIMEOUT = 20.0
DEFAULT_CONNECT_TIMEOUT = 15.0
DEFAULT_CHAR_1 = "c9d9bff5-324c-4b79-bbaf-8a473e6540ec"
DEFAULT_CHAR_2 = "c9d9bff6-324c-4b79-bbaf-8a473e6540ec"

LOGGER = logging.getLogger("potager_ble_char_tester")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Testeur BLE pour ecrire des valeurs custom sur les caracteristiques Modulo2."
    )

    parser.add_argument("--name", default=DEFAULT_NAME, help="Nom BLE de l'appareil")
    parser.add_argument("--address", help="Adresse MAC BLE cible (sinon scan par nom)")
    parser.add_argument("--adapter", default=None, help="Adaptateur BlueZ (ex: hci1)")
    parser.add_argument("--scan-timeout", type=float, default=DEFAULT_SCAN_TIMEOUT)
    parser.add_argument("--connect-timeout", type=float, default=DEFAULT_CONNECT_TIMEOUT)

    parser.add_argument("--char1-uuid", default=DEFAULT_CHAR_1)
    parser.add_argument("--char2-uuid", default=DEFAULT_CHAR_2)

    parser.add_argument(
        "--value1",
        required=True,
        help="Valeur a ecrire dans char1. Exemples: 64 | 0x64 | 64 00 ff",
    )
    parser.add_argument(
        "--value2",
        required=True,
        help="Valeur a ecrire dans char2. Exemples: 64 | 0x64 | 64 00 ff",
    )

    parser.add_argument(
        "--response",
        action="store_true",
        help="Utilise Write Request (response=True) au lieu de Write Command",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_byte_string(text: str) -> bytearray:
    raw = text.strip().replace(",", " ")
    if not raw:
        raise ValueError("Valeur vide")

    parts = raw.split()
    if len(parts) == 1:
        # Accepte un seul octet en decimal ou en hex.
        token = parts[0].lower()
        base = 16 if token.startswith("0x") else 10
        value = int(token, base)
        if not 0 <= value <= 255:
            raise ValueError(f"Octet hors plage 0..255: {value}")
        return bytearray([value])

    bytes_out = bytearray()
    for token in parts:
        t = token.lower()
        if t.startswith("0x"):
            value = int(t, 16)
        else:
            # Multi-octets interpretes en hex compact (64 00 ff)
            value = int(t, 16)
        if not 0 <= value <= 255:
            raise ValueError(f"Octet hors plage 0..255: {value}")
        bytes_out.append(value)
    return bytes_out


def bluez_kwargs(adapter: Optional[str]) -> dict:
    if adapter:
        return {"bluez": {"adapter": adapter}}
    return {}


async def resolve_address(name: str, address: Optional[str], scan_timeout: float, adapter: Optional[str]) -> str:
    if address:
        LOGGER.info("Adresse forcee: %s", address)
        return address

    LOGGER.info("Scan BLE %.1fs pour trouver %s", scan_timeout, name)
    devices = await BleakScanner.discover(timeout=scan_timeout, **bluez_kwargs(adapter))
    for dev in devices:
        if dev.name == name:
            LOGGER.info("Appareil trouve: %s (%s)", dev.name, dev.address)
            return dev.address

    raise RuntimeError(f"Appareil {name} introuvable")


async def write_chars(args: argparse.Namespace) -> None:
    target_address = await resolve_address(args.name, args.address, args.scan_timeout, args.adapter)
    value1 = parse_byte_string(args.value1)
    value2 = parse_byte_string(args.value2)

    client_kwargs = {"timeout": args.connect_timeout}
    client_kwargs.update(bluez_kwargs(args.adapter))

    LOGGER.info("Connexion a %s", target_address)
    async with BleakClient(target_address, **client_kwargs) as client:
        LOGGER.info("Ecriture char1 %s -> %s", args.char1_uuid, value1.hex(" "))
        await client.write_gatt_char(args.char1_uuid, value1, response=args.response)

        LOGGER.info("Ecriture char2 %s -> %s", args.char2_uuid, value2.hex(" "))
        await client.write_gatt_char(args.char2_uuid, value2, response=args.response)

    LOGGER.info("Ecritures terminees")


def main() -> int:
    args = parse_args()
    configure_logging(args.debug)

    try:
        asyncio.run(write_chars(args))
        return 0
    except KeyboardInterrupt:
        LOGGER.warning("Interruption utilisateur")
        return 130
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Echec test char: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
