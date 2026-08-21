from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime, timezone
import subprocess
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
        self.current_address = cfg.address.strip()
        self._bluetoothctl_available: bool | None = None
        self._startup_cleanup_done = False

    def _auto_state_path(self) -> Path:
        return Path(self.cfg.auto_state_file)

    def _bluez(self) -> dict[str, str] | None:
        LOGGER.info("Adapter BLE configure: %s", self.cfg.adapter)
        if self.cfg.adapter:
            return {"adapter": self.cfg.adapter}
        return None

    def _client_kwargs(self) -> dict[str, Any]:
        client_kwargs: dict[str, Any] = {"timeout": self.cfg.connect_timeout}
        bluez = self._bluez()
        if bluez is not None:
            client_kwargs["bluez"] = bluez
        return client_kwargs

    def _bluetoothctl_select_commands(self) -> list[str]:
        adapter = (self.cfg.adapter or "").strip()
        if adapter.lower().startswith("hci"):
            return [f"select {adapter}"]
        if adapter:
            LOGGER.warning(
                "Adapter '%s' n'est pas un nom d'interface bluetoothctl (attendu: hciX)",
                adapter,
            )
        return []

    def _run_bluetoothctl_action(self, action: str, address: str, source: str) -> subprocess.CompletedProcess[str]:
        commands = self._bluetoothctl_select_commands() + [f"{action} {address}", "quit"]
        script = "\n".join(commands) + "\n"
        return subprocess.run(
            ["bluetoothctl", "--timeout", "5"],
            input=script,
            check=False,
            capture_output=True,
            text=True,
            timeout=7,
        )

    def _bluez_disconnect_hint(self, address: str, source: str) -> None:
        """Ask BlueZ to drop any stale link for this MAC before reconnect attempts."""
        if self._bluetoothctl_available is False:
            LOGGER.debug("bluetoothctl unavailable, skip hint disconnect")
            return

        LOGGER.info("Hint disconnect BlueZ (%s) sur %s", source, address)
        try:
            result = self._run_bluetoothctl_action("disconnect", address, source)
            self._bluetoothctl_available = True
            if result.returncode == 0:
                LOGGER.info("Hint disconnect BlueZ OK (%s): %s", source, address)
            else:
                stderr = (result.stderr or "").strip()
                if stderr:
                    LOGGER.warning("Hint disconnect BlueZ rc=%s (%s): %s", result.returncode, source, stderr)
                else:
                    LOGGER.warning("Hint disconnect BlueZ rc=%s (%s)", result.returncode, source)
        except FileNotFoundError:
            self._bluetoothctl_available = False
            LOGGER.warning("bluetoothctl indisponible, skip hint disconnect")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Hint disconnect BlueZ ignore (%s): %r", source, exc)

    def _bluez_remove_hint(self, address: str, source: str) -> None:
        """Ask BlueZ to remove cached device object for this MAC."""
        if self._bluetoothctl_available is False:
            LOGGER.debug("bluetoothctl unavailable, skip hint remove")
            return

        LOGGER.info("Hint remove BlueZ (%s) sur %s", source, address)
        try:
            result = self._run_bluetoothctl_action("remove", address, source)
            self._bluetoothctl_available = True
            if result.returncode == 0:
                LOGGER.info("Hint remove BlueZ OK (%s): %s", source, address)
            else:
                stderr = (result.stderr or "").strip()
                if stderr:
                    LOGGER.warning("Hint remove BlueZ rc=%s (%s): %s", result.returncode, source, stderr)
                else:
                    LOGGER.warning("Hint remove BlueZ rc=%s (%s)", result.returncode, source)
        except FileNotFoundError:
            self._bluetoothctl_available = False
            LOGGER.warning("bluetoothctl indisponible, skip hint remove")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Hint remove BlueZ ignore (%s): %r", source, exc)

    def prepare_first_connection(self) -> None:
        """One-shot cleanup before first BLE connect attempt."""
        if self._startup_cleanup_done:
            return
        address = self.current_address or self.cfg.address.strip()
        if not address:
            return
        LOGGER.info("Pre-cleanup BLE startup sur %s", address)
        self._bluez_disconnect_hint(address, "startup")
        self._bluez_remove_hint(address, "startup")
        self._startup_cleanup_done = True

    def cleanup_on_shutdown(self) -> None:
        """Best-effort BLE cleanup when process is stopping."""
        address = self.current_address or self.cfg.address.strip()
        if not address:
            return
        LOGGER.info("Cleanup BLE shutdown sur %s", address)
        self._bluez_disconnect_hint(address, "shutdown")
        self._bluez_remove_hint(address, "shutdown")

    async def _open_client_with_hard_connect(self, address: str, label: str) -> BleakClient:
        client_kwargs = self._client_kwargs()

        # Fast path: direct connect to the known MAC.
        client = BleakClient(address, **client_kwargs)
        try:
            await client.connect()
            LOGGER.debug("Connexion directe OK (%s): %s", label, address)
            return client
        except Exception as direct_exc:  # noqa: BLE001
            with suppress(Exception):
                await client.disconnect()
            LOGGER.warning(
                "Connexion directe echec (%s) vers %s: %r",
                label,
                address,
                direct_exc,
            )
            self._bluez_disconnect_hint(address, f"direct-failed:{label}")
            await asyncio.sleep(0.4)

        # Hard-connect path: scan explicitly for this MAC to refresh BlueZ device state.
        scan_timeout = max(3.0, min(self.cfg.connect_timeout, 10.0))
        bluez = self._bluez()
        scan_kwargs: dict[str, Any] = {"timeout": scan_timeout}
        if bluez is not None:
            scan_kwargs["bluez"] = bluez

        LOGGER.info(
            "Hard-connect (%s): scan cible sur %s (%.1fs)",
            label,
            address,
            scan_timeout,
        )
        device = await BleakScanner.find_device_by_address(address, **scan_kwargs)
        if device is None:
            raise RuntimeError(
                f"Hard-connect impossible: appareil {address} introuvable pendant scan cible"
            )

        client = BleakClient(device, **client_kwargs)
        await client.connect()
        LOGGER.info("Hard-connect OK (%s): %s", label, address)
        return client

    async def test_connect(self, address: str) -> None:
        client = await self._open_client_with_hard_connect(address, "test")
        try:
            LOGGER.debug("Connexion test OK: %s", address)
        finally:
            with suppress(Exception):
                await client.disconnect()

    async def _connect_with_retry(self, address: str, label: str) -> None:
        attempts = max(1, self.cfg.retries + 1)
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                LOGGER.info(
                    "Connexion BLE %s vers %s (tentative %d/%d)",
                    label,
                    address,
                    attempt,
                    attempts,
                )
                await self.test_connect(address)
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                LOGGER.warning(
                    "Connexion BLE en echec %s vers %s (tentative %d/%d): %r",
                    label,
                    address,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    self._bluez_disconnect_hint(address, f"retry:{label}")
                    backoff_s = min(3.0, 0.5 * attempt)
                    LOGGER.info("Nouvelle tentative dans %.1fs", backoff_s)
                    await asyncio.sleep(backoff_s)

        if last_exc is not None:
            raise RuntimeError(
                f"Connexion BLE impossible vers {address} apres {attempts} tentative(s)"
            ) from last_exc
        raise RuntimeError(f"Connexion BLE impossible vers {address}")

    async def resolve_address(self) -> str:
        address = self.current_address or self.cfg.address.strip()
        if not address:
            raise ValueError("Aucune adresse MAC configuree")
        self.prepare_first_connection()
        await self._connect_with_retry(address, "resolve")
        self.current_address = address
        return address

    async def _write_once(self, address: str, writes: list[tuple[str, bytearray]]) -> None:
        client = await self._open_client_with_hard_connect(address, "write")
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
        address = self.current_address or self.cfg.address.strip()
        if not address:
            raise ValueError("Aucune adresse MAC configuree")

        for attempt in range(1, attempts + 1):
            try:
                LOGGER.info(
                    "Envoi %s vers %s (tentative %d/%d)",
                    label,
                    address,
                    attempt,
                    attempts,
                )
                await self._write_once(address, writes)
                self.current_address = address
                return
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Echec tentative %d/%d: %s", attempt, attempts, exc)
                if attempt < attempts:
                    await self._connect_with_retry(address, f"retry {label}")
                else:
                    raise

    async def read_channels(self, label: str, channel_keys: list[str]) -> dict[str, bytearray]:
        attempts = max(1, self.cfg.retries + 1)
        address = self.current_address or self.cfg.address.strip()
        if not address:
            raise ValueError("Aucune adresse MAC configuree")

        for attempt in range(1, attempts + 1):
            try:
                LOGGER.info(
                    "Lecture %s depuis %s (tentative %d/%d)",
                    label,
                    address,
                    attempt,
                    attempts,
                )
                client = await self._open_client_with_hard_connect(address, f"read {label}")
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
                self.current_address = address
                return values
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Echec lecture tentative %d/%d: %s", attempt, attempts, exc)
                if attempt < attempts:
                    await self._connect_with_retry(address, f"retry read {label}")
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
