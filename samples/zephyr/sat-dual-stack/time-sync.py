#!/usr/bin/env python3
#
# Copyright (c) 2026 Hubble Network, Inc.
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import struct
import sys
import logging
import httpx
import os

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from dataclasses import dataclass
from datetime import datetime, UTC

log = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 30

HUBBLE_API_TOKEN = os.environ.get("HUBBLE_API_TOKEN")
if not HUBBLE_API_TOKEN:
    sys.exit("HUBBLE_API_TOKEN environment variable is required")
HUBBLE_EPP_URL = "https://api.hubble.com/api/satellite/ephemeris"

HUBBLE_TARGET_SATELLITE_IDS = [64562, 64565, 64592, 64840]

_SERVICE_UUID           = "0000fca7-0000-1000-8000-00805f9b34fb"
_CHARACTERISTIC_UUID    = "00000005-fca7-4000-8000-00805f9b34fb"

HUBBLE_BLE_UUID_SYNC    = "0000fca7"

@dataclass(slots=True)
class EppParams:
    """
    Satellite orbital parameters
    """

    t0: int  # uint64, unix epoch seconds
    n0: float
    ndot: float
    raan0: float
    raandot: float
    aop0: float
    aopdot: float
    inclination: float
    eccentricity: float
    satellite_id: int  # uint32

    def to_bytes(self) -> bytes:
        """
        Pack as little-endian struct:
        uint64 t0, 8x double, uint32 sat_id.
        """
        return struct.pack(
            "<Q8dI",
            self.t0,
            self.n0,
            self.ndot,
            self.raan0,
            self.raandot,
            self.aop0,
            self.aopdot,
            self.inclination,
            self.eccentricity,
            self.satellite_id,
        )


class HubbleClient:
    """Hubble cloud client for fetching satellite EPP data."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)
        log.info("Hubble client started")

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            log.info("Hubble client stopped")

    async def fetch_epp(self) -> list[EppParams]:
        """
        Fetch EPP params for target satellites.

        Returns:
            A list of EppParams for each target satellite that has EPP data.
        """
        if self._client is None:
            raise RuntimeError("HubbleClient.start() must be called first")

        try:
            response = await self._client.get(
                HUBBLE_EPP_URL,
                headers={"Authorization": f"Bearer {HUBBLE_API_TOKEN}"},
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("Failed to fetch ephemeris: %s", e)
            return []

        try:
            data = response.json()
        except ValueError:
            log.error("Invalid JSON from ephemeris endpoint")
            return []

        results = []
        for sat in data.get("satellites", []):
            sat_id = sat.get("satellite_id")
            if sat_id not in HUBBLE_TARGET_SATELLITE_IDS:
                continue

            epp = sat.get("orbital_params")
            if epp is None:
                log.debug("No Orbital params for satellite %d", sat_id)
                continue

            try:
                results.append(
                    EppParams(
                        t0=epp["t0"],
                        n0=epp["n0"],
                        ndot=epp["ndot"],
                        raan0=epp["raan0"],
                        raandot=epp["raandot"],
                        aop0=epp["aop0"],
                        aopdot=epp["aopdot"],
                        inclination=epp["inclination"],
                        eccentricity=epp["eccentricity"],
                        satellite_id=sat_id,
                    ),
                )
            except (KeyError, ValueError) as e:
                log.warning("Failed to parse EPP for satellite %d: %s", sat_id, e)

        log.info("Fetched EPP for %d satellites", len(results))
        return results


async def scan() -> None:
    hubble = HubbleClient()

    await hubble.start()
    try:
        epps = await hubble.fetch_epp()
    finally:
        await hubble.stop()

    def match_hubble_sync_uuid(device: BLEDevice, adv: AdvertisementData):
        for uuid in adv.service_uuids:
            if uuid.startswith(HUBBLE_BLE_UUID_SYNC):
                return True
        return False

    device = await BleakScanner.find_device_by_filter(match_hubble_sync_uuid)
    if device is not None:
        async with BleakClient(device) as client:
            data = bytearray([0x01, 0x02])
            data +=  bytearray(int(datetime.now(UTC).timestamp() * 1000).to_bytes(8, byteorder="little", signed=False))
            await client.write_gatt_char(_CHARACTERISTIC_UUID, data, response=True)

            for epp in epps:
                data = bytearray([0x01, 0x03])
                data.extend(epp.to_bytes())

                # Send new EPP notification
                await client.write_gatt_char(_CHARACTERISTIC_UUID, data, response=True)
        log.info(f"BLE provisioning done: {device}")
    else:
        log.warning("No BLE device found")
        return

def sync() -> None:
    asyncio.run(scan())


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    sync()

