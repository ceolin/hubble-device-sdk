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
HUBBLE_EPHEMERIS_URL = "https://api.hubble.com/api/satellite/ephemeris"

HUBBLE_TARGET_SATELLITE_IDS = [64562, 64565, 64592, 64840]

_SERVICE_UUID           = "0000fca7-0000-1000-8000-00805f9b34fb"
_CHARACTERISTIC_UUID    = "00000005-fca7-4000-8000-00805f9b34fb"

HUBBLE_BLE_UUID_SYNC    = "0000fca7"

@dataclass(slots=True)
class OrbitalParams:
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

    async def fetch_ephemeris(self) -> list[OrbitalParams]:
        """
        Fetch Orbital params for target satellites.

        Returns:
            A list of OrbitalParams for each target satellite.
        """
        if self._client is None:
            raise RuntimeError("HubbleClient.start() must be called first")

        try:
            response = await self._client.get(
                HUBBLE_EPHEMERIS_URL,
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

            orbital_params = sat.get("orbital_params")
            if orbital_params is None:
                log.debug("No Orbital params for satellite %d", sat_id)
                continue

            try:
                results.append(
                    OrbitalParams(
                        t0=orbital_params["t0"],
                        n0=orbital_params["n0"],
                        ndot=orbital_params["ndot"],
                        raan0=orbital_params["raan0"],
                        raandot=orbital_params["raandot"],
                        aop0=orbital_params["aop0"],
                        aopdot=orbital_params["aopdot"],
                        inclination=orbital_params["inclination"],
                        eccentricity=orbital_params["eccentricity"],
                        satellite_id=sat_id,
                    ),
                )
            except (KeyError, ValueError) as e:
                log.warning("Failed to parse Orbital params for satellite %d: %s", sat_id, e)

        log.info("Fetched Orbital params for %d satellites", len(results))
        return results


async def scan(lat: float, lon: float) -> None:
    hubble = HubbleClient()

    await hubble.start()
    try:
        ephemeris = await hubble.fetch_ephemeris()
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

            data = bytearray([0x01, 0x04])
            data.extend(struct.pack("<d", lat))
            data.extend(struct.pack("<d", lon))
            await client.write_gatt_char(_CHARACTERISTIC_UUID, data, response=True)

            for orbital_params in ephemeris:
                data = bytearray([0x01, 0x03])
                data.extend(orbital_params.to_bytes())

                # Send new Orbital params notification
                await client.write_gatt_char(_CHARACTERISTIC_UUID, data, response=True)
        log.info(f"BLE provisioning done: {device}")
    else:
        log.warning("No BLE device found")
        return

def sync(lat: float, lon: float) -> None:
    asyncio.run(scan(lat, lon))


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = sys.argv[1:]

    if len(args) == 2:
        sync(float(args[0]), float(args[1]))
    else:
        # No lat/lon provided. Let's use Seattle
        sync(lat=47.614376, lon=-122.319323)

