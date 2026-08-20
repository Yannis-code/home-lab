from __future__ import annotations

import json
import logging
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bleak import BleakClient, BleakScanner

from src.config_models import AppConfig
from src.modulo2_protocol import (
    AUTO_RESTORE_KEYS,
    AUTO_SNAPSHOT_KEYS,
    CHAR_UUIDS,
    SetChannelsInput,
    action_to_intensity,
    build_set_writes,
    current_seconds_of_day,
    seconds_to_le32,
)

LOGGER = logging.getLogger("potager_ble")


class PotagerController:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.current_address = cfg.address

    def _state_path(self) -> Path:
        return Path(self.cfg.state_file)

    def _auto_state_path(self) -> Path:
        return Path(self.cfg.auto_state_file)

    def _bluez(self) -> dict[str, str] | None:
        if self.cfg.adapter:
            return {"adapter": self.cfg.adapter}
        return None

    def _client_kwargs(self) -> dict[str, Any]:
        client_kwargs: dict[str, Any] = {"timeout": self.cfg.connect_timeout}
        bluez = self._bluez()
        if bluez is not None:
            client_kwargs["bluez"] = bluez
        return client_kwargs

    def load_last_mac(self) -> str | None:
        path = self._state_path()
        try:
            if not path.exists():
                return None
            value = path.read_text(encoding="utf-8").strip()
            return value or None
        except OSError as exc:
            LOGGER.warning("Lecture cache MAC impossible (%s): %s", path, exc)
            return None

    def save_last_mac(self, address: str) -> None:
        path = self._state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(address, encoding="utf-8")
            LOGGER.debug("MAC sauvegardee: %s", address)
        except OSError as exc:
            LOGGER.warning("Sauvegarde cache MAC impossible (%s): %s", path, exc)

    async def scan_for_address(self) -> str:
        LOGGER.info(
            "Scan BLE en cours (%.1fs) pour trouver %s",
            self.cfg.scan_timeout,
            self.cfg.target_name,
        )
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
        client = BleakClient(address, **self._client_kwargs())
        try:
            await client.connect()
            LOGGER.debug("Connexion test OK: %s", address)
        finally:
            with suppress(Exception):
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

    async def _write_once(self, address: str, writes: list[tuple[str, bytearray]]) -> None:
        client = BleakClient(address, **self._client_kwargs())
        await client.connect()
        sent = False
        try:
            for uuid, payload in writes:
                LOGGER.info("Write %s <- %s", uuid, payload.hex(" "))
                await client.write_gatt_char(uuid, payload, response=True)
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

    async def send_writes(self, label: str, writes: list[tuple[str, bytearray]]) -> None:
        attempts = max(1, self.cfg.retries + 1)

        for attempt in range(1, attempts + 1):
            try:
                address = self.current_address or await self.resolve_address(force_scan=False)
                LOGGER.info(
                    "Envoi %s vers %s (tentative %d/%d)",
                    label,
                    address,
                    attempt,
                    attempts,
                )
                await self._write_once(address, writes)
                self.save_last_mac(address)
                return
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Echec tentative %d/%d: %s", attempt, attempts, exc)
                self.current_address = None
                if attempt < attempts:
                    await self.resolve_address(force_scan=True)
                else:
                    raise

    async def read_channels(self, label: str, channel_keys: list[str]) -> dict[str, bytearray]:
        attempts = max(1, self.cfg.retries + 1)

        for attempt in range(1, attempts + 1):
            try:
                address = self.current_address or await self.resolve_address(force_scan=False)
                LOGGER.info(
                    "Lecture %s depuis %s (tentative %d/%d)",
                    label,
                    address,
                    attempt,
                    attempts,
                )
                client = BleakClient(address, **self._client_kwargs())
                await client.connect()
                values: dict[str, bytearray] = {}
                try:
                    for key in channel_keys:
                        uuid = CHAR_UUIDS[key]
                        data = await client.read_gatt_char(uuid)
                        payload = bytearray(data)
                        LOGGER.info("Read %s (%s) -> %s", key, uuid, payload.hex(" "))
                        values[key] = payload
                finally:
                    with suppress(Exception):
                        await client.disconnect()
                self.save_last_mac(address)
                return values
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Echec lecture tentative %d/%d: %s", attempt, attempts, exc)
                self.current_address = None
                if attempt < attempts:
                    await self.resolve_address(force_scan=True)
                else:
                    raise

        # Defensive fallback for static type checkers: loop should never exit without
        # returning values or re-raising the last exception.
        raise RuntimeError("Lecture BLE terminee sans resultat")

    async def save_auto_state(self) -> None:
        values = await self.read_channels("auto state", list(AUTO_SNAPSHOT_KEYS))
        address = self.current_address or "unknown"
        payload = {
            "schema": 1,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "device_name": self.cfg.target_name,
            "device_address": address,
            "channels": {
                key: {
                    "uuid": CHAR_UUIDS[key],
                    "hex": values[key].hex(),
                }
                for key in AUTO_SNAPSHOT_KEYS
                if key in values
            },
        }

        path = self._auto_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        LOGGER.info("Etat auto sauvegarde dans %s", path)

    async def restore_auto_state(self) -> None:
        path = self._auto_state_path()
        if not path.exists():
            raise FileNotFoundError(f"Fichier auto-state introuvable: {path}")

        snapshot = json.loads(path.read_text(encoding="utf-8"))
        channels = snapshot.get("channels", {})
        writes: list[tuple[str, bytearray]] = []

        for key in AUTO_RESTORE_KEYS:
            node = channels.get(key)
            if not node:
                continue
            hex_value = str(node.get("hex", "")).strip()
            if not hex_value:
                continue
            writes.append((CHAR_UUIDS[key], bytearray.fromhex(hex_value)))

        if self.cfg.restore_use_saved_clock:
            node = channels.get("clock")
            if node and str(node.get("hex", "")).strip():
                writes.insert(0, (CHAR_UUIDS["clock"], bytearray.fromhex(node["hex"])))
        else:
            writes.insert(0, (CHAR_UUIDS["clock"], seconds_to_le32(current_seconds_of_day())))

        if not writes:
            raise ValueError(f"Aucune valeur restorable dans {path}")

        await self.send_writes("auto restore", writes)
        LOGGER.info("Etat auto restaure depuis %s", path)

    async def send_action(self, action: str) -> None:
        value = action_to_intensity(action)
        writes = [
            (CHAR_UUIDS["left_intensity"], bytearray([value])),
            (CHAR_UUIDS["right_intensity"], bytearray([value])),
        ]
        await self.send_writes(f"commande {action}", writes)

    async def send_set_channels(self) -> None:
        payload = SetChannelsInput(
            left_intensity=self.cfg.set_left_intensity,
            right_intensity=self.cfg.set_right_intensity,
            left_start=self.cfg.set_left_start,
            right_start=self.cfg.set_right_start,
            left_end=self.cfg.set_left_end,
            right_end=self.cfg.set_right_end,
            clock_now=self.cfg.set_clock_now,
            clock_seconds=self.cfg.set_clock_seconds,
            mirror_sides=self.cfg.set_mirror_sides,
        )
        writes = build_set_writes(payload)
        await self.send_writes("set channels", writes)

    async def send_raw_channels(
        self,
        channels: dict[str, bytearray],
        label: str = "raw channels",
    ) -> None:
        writes: list[tuple[str, bytearray]] = []
        for key, payload in channels.items():
            if key not in CHAR_UUIDS:
                raise ValueError(f"Canal inconnu: {key}")
            writes.append((CHAR_UUIDS[key], payload))
        if not writes:
            raise ValueError("Aucune ecriture brute a envoyer")
        await self.send_writes(label, writes)
